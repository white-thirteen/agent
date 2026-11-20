"""Pinned local BGE reranking with full-pair validation and raw logits."""

import asyncio
import math
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from app.core.config import Settings
from app.knowledge.cpu_capacity import cpu_capacity
from app.knowledge.models import EvidenceChunk, KnowledgeError
from app.knowledge.sparse import search_text

BGE_REVISION = "2cfc18c9415c912f9d8155881c133215df768a70"
BGE_MAX_TOKENS = 512


class BGEReranker:
    """One local CrossEncoder; requests never wait in an unbounded inference queue."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bge-reranker")
        self._lock = Lock()
        self._busy = False
        self._closed = False
        self._model = None
        self._close_future = None

    def _submit(self, function, *args):
        with self._lock:
            if self._closed:
                raise KnowledgeError("rerank_unavailable")
            if self._busy or not cpu_capacity.acquire(blocking=False):
                raise KnowledgeError("rerank_busy")
            self._busy = True
            try:
                future = self._executor.submit(function, *args)
            except BaseException:
                self._busy = False
                cpu_capacity.release()
                raise

        def settled(_):
            with self._lock:
                self._busy = False
                cpu_capacity.release()

        future.add_done_callback(settled)
        return future

    async def _call(self, function, *args, timeout):
        wrapped = asyncio.wrap_future(self._submit(function, *args))
        wrapped.add_done_callback(lambda done: done.exception() if not done.cancelled() else None)
        try:
            async with asyncio.timeout(timeout):
                return await asyncio.shield(wrapped)
        except TimeoutError:
            raise KnowledgeError("rerank_timeout") from None

    def _load(self):
        import torch
        from sentence_transformers import CrossEncoder

        if self._model is not None:
            return
        path = self.settings.reranker_model_path
        if path.name != BGE_REVISION:
            raise KnowledgeError("rerank_unavailable")
        torch.set_num_threads(self.settings.embedding_cpu_threads)
        self._model = CrossEncoder(
            str(path),
            device="cpu",
            local_files_only=True,
            trust_remote_code=False,
            model_kwargs={"use_safetensors": True, "low_cpu_mem_usage": True},
        )
        self._model.model.eval()

    async def initialize(self):
        try:
            await self._call(self._load, timeout=self.settings.reranker_startup_timeout_seconds)
        except KnowledgeError:
            raise
        except (OSError, ImportError, RuntimeError, ValueError):
            raise KnowledgeError("rerank_unavailable") from None

    def _score(self, query: str, candidates: list[EvidenceChunk]) -> list[float]:
        import torch

        if self._model is None:
            raise KnowledgeError("rerank_unavailable")
        tokenizer = self._model.tokenizer
        # Retain the exact validated encodings; no model library can truncate them later.
        encoded = [
            tokenizer(
                query,
                search_text(c.source_title, c.section, c.content),
                add_special_tokens=True,
                truncation=False,
            )
            for c in candidates
        ]
        if any(len(item["input_ids"]) > BGE_MAX_TOKENS for item in encoded):
            raise KnowledgeError("rerank_input_too_long")
        scores = []
        try:
            with torch.inference_mode():
                for start in range(0, len(encoded), self.settings.reranker_batch_size):
                    batch = tokenizer.pad(
                        encoded[start : start + self.settings.reranker_batch_size],
                        padding=True,
                        return_tensors="pt",
                    )
                    logits = self._model.model(**batch).logits.reshape(-1).tolist()
                    scores.extend(float(value) for value in logits)
        except (OSError, RuntimeError):
            raise KnowledgeError("rerank_unavailable") from None
        if len(scores) != len(candidates) or not all(math.isfinite(value) for value in scores):
            raise KnowledgeError("rerank_invalid_scores")
        return scores

    async def score(self, query: str, candidates: list[EvidenceChunk]) -> list[float]:
        return await self._call(
            self._score, query, candidates, timeout=self.settings.reranker_timeout_seconds
        )

    async def aclose(self):
        with self._lock:
            self._closed = True
            if self._close_future is None:
                self._close_future = self._executor.submit(self._release)
        await asyncio.shield(asyncio.wrap_future(self._close_future))
        await asyncio.to_thread(self._executor.shutdown, wait=True, cancel_futures=False)

    def _release(self):
        self._model = None
