"""One CPU model, one worker, with capacity retained after caller cancellation."""

import asyncio
import math
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from langchain_core.embeddings import Embeddings

from app.core.config import Settings
from app.knowledge.models import EmbeddingProfile, KnowledgeError, digest

QUERY_PROMPT = (
    "Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:"
)


def validate_vectors(vectors, count: int) -> list[list[float]]:
    if len(vectors) != count:
        raise KnowledgeError("embedding_invalid_vectors")
    result = []
    for vector in vectors:
        values = [float(value) for value in vector]
        if (
            len(values) != 1024
            or not all(math.isfinite(v) for v in values)
            or sum(v * v for v in values) <= 0
        ):
            raise KnowledgeError("embedding_invalid_vectors")
        result.append(values)
    return result


class QwenLocalEmbeddings(Embeddings):
    """LangChain interface. Async calls never enqueue behind a timed-out kernel.

    A timed-out/cancelled caller leaves its worker future owning the sole slot.
    Shutdown drains that future before deleting weights, all outside the event loop.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="qwen-embedding")
        self._lock = Lock()
        self._busy = False
        self._closed = False
        self._model = None
        self._future = None
        self._close_future = None
        self.profile: EmbeddingProfile | None = None

    def _load(self):
        import torch
        from sentence_transformers import SentenceTransformer

        if self._model is not None:
            return
        path = self.settings.embedding_model_path
        revision_path = path / "REVISION"
        if not revision_path.is_file():
            raise KnowledgeError("embedding_missing_revision")
        from app.knowledge.chunking import context_tokenizer

        context_tokenizer()
        torch.set_num_threads(self.settings.embedding_cpu_threads)
        model = SentenceTransformer(
            str(path),
            device="cpu",
            local_files_only=True,
            model_kwargs={
                "dtype": getattr(torch, self.settings.embedding_dtype),
                "attn_implementation": "sdpa",
            },
            tokenizer_kwargs={"padding_side": "left"},
            trust_remote_code=False,
        )
        model.max_seq_length = self.settings.embedding_max_input_tokens
        self._model = model
        self.profile = EmbeddingProfile(
            revision=self.settings.embedding_profile_revision,
            weights_revision=revision_path.read_text(encoding="utf-8").strip(),
            query_prompt=QUERY_PROMPT,
            dtype=self.settings.embedding_dtype,
            tokenizer="Qwen3:" + digest((path / "tokenizer.json").read_text(encoding="utf-8")),
        )

    def _submit(self, function, *args):
        with self._lock:
            if self._closed:
                raise KnowledgeError("embedding_unavailable")
            if self._busy:
                raise KnowledgeError("embedding_busy")
            self._busy = True
            future = self._executor.submit(function, *args)
            self._future = future

        def settled(_):
            with self._lock:
                self._busy = False

        future.add_done_callback(settled)
        return future

    async def _async_call(self, function, *args, timeout=None):
        future = self._submit(function, *args)
        wrapped = asyncio.wrap_future(future)
        # Retrieve late exceptions even if the original request has left.
        wrapped.add_done_callback(lambda done: done.exception() if not done.cancelled() else None)
        try:
            async with asyncio.timeout(timeout or self.settings.embedding_timeout_seconds):
                return await asyncio.shield(wrapped)
        except TimeoutError:
            raise KnowledgeError("embedding_timeout") from None

    async def initialize(self):
        try:
            await self._async_call(
                self._load, timeout=self.settings.embedding_startup_timeout_seconds
            )
        except (OSError, ImportError, RuntimeError, ValueError):
            raise KnowledgeError("embedding_unavailable") from None

    def _encode(self, texts: list[str], query: bool):
        if self._model is None:
            raise KnowledgeError("embedding_unavailable")
        if not texts:
            raise ValueError("Embedding input cannot be empty")
        prompt = QUERY_PROMPT if query else ""
        for text in texts:
            if not text.strip():
                raise ValueError("Embedding input cannot be blank")
            # Check actual model tokenizer including instruction and special tokens before encode.
            tokens = self._model.tokenizer(prompt + text, truncation=False)["input_ids"]
            if len(tokens) > self.settings.embedding_max_input_tokens:
                raise ValueError("Embedding input exceeds configured model token limit")
        try:
            vectors = self._model.encode(
                texts,
                prompt=prompt,
                batch_size=self.settings.embedding_batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
        except (OSError, RuntimeError):
            raise KnowledgeError("embedding_unavailable") from None
        return validate_vectors(vectors, len(texts))

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._submit(self._encode, texts, False).result()

    def embed_query(self, text: str) -> list[float]:
        return self._submit(self._encode, [text], True).result()[0]

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._async_call(self._encode, texts, False)

    async def aembed_query(self, text: str) -> list[float]:
        return (await self._async_call(self._encode, [text], True))[0]

    async def aclose(self):
        with self._lock:
            self._closed = True
            if self._close_future is None:
                self._close_future = self._executor.submit(self._release)
        # Queue disposal behind the active kernel so freeing tensors also stays off-loop.
        await asyncio.shield(asyncio.wrap_future(self._close_future))
        await asyncio.to_thread(self._executor.shutdown, wait=True, cancel_futures=False)

    def _release(self):
        self._model = None


def create_embeddings(settings: Settings) -> QwenLocalEmbeddings:
    if settings.embedding_provider != "qwen_local":
        raise ValueError("Unsupported embedding provider")
    return QwenLocalEmbeddings(settings)
