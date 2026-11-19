import asyncio
from threading import Event
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.knowledge.embedding import QwenLocalEmbeddings
from app.knowledge.models import EvidenceChunk, KnowledgeError
from app.knowledge.reranker import BGEReranker


def chunk(content):
    return EvidenceChunk(
        document_id="d",
        document_version="v",
        chunk_id=content,
        content_hash="h",
        evidence_id="e",
        source_title="title",
        public_source_key="source",
        section="section",
        line_start=1,
        line_end=1,
        content=content,
        retrieval_score=0,
        domain="platform_help",
    )


async def test_complete_pairs_are_checked_before_inference_and_logits_are_raw():
    import torch

    class Tokenizer:
        def __call__(self, query, passage, **kwargs):
            assert query == "question"
            assert passage.startswith("title\nsection\n")
            assert kwargs == {"add_special_tokens": True, "truncation": False}
            return {"input_ids": [1] * (513 if passage.endswith("long") else 512)}

        def pad(self, values, **kwargs):
            return {"input_ids": torch.tensor([value["input_ids"] for value in values])}

    class Model:
        calls = 0

        def __call__(self, input_ids):
            self.calls += 1
            assert input_ids.shape[1] == 512
            return SimpleNamespace(logits=torch.tensor([[-2.0]] * len(input_ids)))

    reranker = BGEReranker(Settings(_env_file=None))
    model = Model()
    reranker._model = SimpleNamespace(tokenizer=Tokenizer(), model=model)
    try:
        with pytest.raises(KnowledgeError, match="rerank_input_too_long"):
            await reranker.score("question", [chunk("short"), chunk("long")])
        assert model.calls == 0
        assert await reranker.score("question", [chunk("short")]) == [-2.0]
    finally:
        await reranker.aclose()


async def test_shared_capacity_retained_after_timeout_cancel_and_close():
    settings = Settings(_env_file=None, reranker_timeout_seconds=0.02)
    reranker = BGEReranker(settings)
    embedding = QwenLocalEmbeddings(settings)
    entered, release = Event(), Event()

    def blocked(*args):
        entered.set()
        release.wait()
        return []

    reranker._score = blocked
    embedding._encode = lambda *args: [[1.0] * 1024]
    try:
        with pytest.raises(KnowledgeError, match="rerank_timeout"):
            await reranker.score("q", [])
        assert entered.is_set()
        with pytest.raises(KnowledgeError, match="embedding_busy"):
            await embedding.aembed_query("q")
        close = asyncio.create_task(reranker.aclose())
        await asyncio.sleep(0.01)
        assert not close.done()
        release.set()
        await close
        assert len(await embedding.aembed_query("q")) == 1024
    finally:
        release.set()
        await reranker.aclose()
        await embedding.aclose()

    reranker = BGEReranker(settings)
    embedding = QwenLocalEmbeddings(settings)
    entered.clear()
    release.clear()
    reranker._score = blocked
    try:
        call = asyncio.create_task(reranker.score("q", []))
        await asyncio.to_thread(entered.wait)
        call.cancel()
        with pytest.raises(asyncio.CancelledError):
            await call
        with pytest.raises(KnowledgeError, match="embedding_busy"):
            await embedding.aembed_query("q")
    finally:
        release.set()
        await reranker.aclose()
        await embedding.aclose()
