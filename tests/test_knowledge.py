"""Controlled tests of cancellation capacity, source integrity and retrieval boundaries."""

import asyncio
import json
from threading import Event
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.knowledge.chunking import prepare_document, read_manifest
from app.knowledge.embedding import QwenLocalEmbeddings
from app.knowledge.ingest import KnowledgeIngestor
from app.knowledge.models import EvidenceChunk, KnowledgeError, ManifestEntry, SearchQuery, digest
from app.knowledge.retriever import VectorRetriever
from app.runtime.context import DemoIdentity


def entry(**updates):
    return ManifestEntry(
        document_id="demo",
        filename="demo.md",
        source_title="Demo",
        domain="platform_help",
        public_source_key="demo",
        **updates,
    )


async def test_timeout_and_cancel_keep_capacity_and_close_drains():
    embeddings = QwenLocalEmbeddings(Settings(_env_file=None, embedding_timeout_seconds=0.02))
    entered, release = Event(), Event()

    def blocked(*args):
        entered.set()
        release.wait()
        return [[1.0] * 1024]

    embeddings._encode = blocked
    try:
        with pytest.raises(KnowledgeError, match="embedding_timeout"):
            await embeddings.aembed_query("query")
        assert entered.is_set()
        with pytest.raises(KnowledgeError, match="embedding_busy"):
            await embeddings.aembed_query("second")
        close = asyncio.create_task(embeddings.aclose())
        await asyncio.sleep(0.01)
        assert not close.done()
        release.set()
        await close
        with pytest.raises(KnowledgeError, match="embedding_unavailable"):
            await embeddings.aembed_query("third")
    finally:
        release.set()
        await embeddings.aclose()

    embeddings = QwenLocalEmbeddings(Settings(_env_file=None))
    release.clear()
    entered.clear()
    embeddings._encode = blocked
    call = asyncio.create_task(embeddings.aembed_query("query"))
    try:
        await asyncio.to_thread(entered.wait)
        call.cancel()
        with pytest.raises(asyncio.CancelledError):
            await call
        with pytest.raises(KnowledgeError, match="embedding_busy"):
            await embeddings.aembed_query("second")
    finally:
        release.set()
        await embeddings.aclose()


def test_source_lines_unicode_stable_versions_and_unsafe_manifest(tmp_path):
    body = "中文🙂段落" * 600
    (tmp_path / "demo.md").write_text("# 帮助\n\n" + body + "\n", "utf-8")
    document = prepare_document(tmp_path, entry(), "profile")
    assert "".join(chunk.content for chunk in document.chunks) == body
    assert all(chunk.token_count <= 500 for chunk in document.chunks)
    assert all(chunk.line_start == chunk.line_end == 3 for chunk in document.chunks)
    assert prepare_document(tmp_path, entry(), "profile") == document
    assert (
        prepare_document(tmp_path, entry(), "new-profile").document_version
        != document.document_version
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([entry().model_dump() | {"filename": "../outside.md"}]))
    with pytest.raises(ValueError, match="inside"):
        read_manifest(tmp_path, manifest)
    (tmp_path / "demo.md").write_text("\n", "utf-8")
    with pytest.raises(ValueError, match="Empty"):
        prepare_document(tmp_path, entry(), "profile")


async def test_unchanged_import_does_not_embed_or_write(tmp_path):
    (tmp_path / "demo.md").write_text("# Demo\n\nSelf authored Demo text.", "utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([entry().model_dump()]))

    async def complete(document):
        return True

    result = await KnowledgeIngestor(
        SimpleNamespace(is_complete=complete), object(), "profile"
    ).ingest(tmp_path, manifest)
    assert result == {"published": [], "unchanged": ["demo"], "embedding_batches": 0}


async def test_retrieval_denies_before_embedding_and_packs_metadata_budget():
    calls = []

    async def embed(query):
        calls.append(query)
        return [1.0] * 1024

    candidate = EvidenceChunk(
        document_id="demo",
        document_version="v1",
        chunk_id="chunk",
        content_hash=digest("body"),
        evidence_id="e",
        source_title="Demo",
        public_source_key="demo",
        section=None,
        line_start=1,
        line_end=1,
        content="中文" * 2000,
        retrieval_score=0.8,
        domain="platform_help",
    )

    async def search(*args):
        return (candidate,)

    retriever = VectorRetriever(
        SimpleNamespace(search=search), SimpleNamespace(aembed_query=embed), "profile"
    )
    with pytest.raises(KnowledgeError, match="policy_denied"):
        await retriever.search(SearchQuery(query="query"), identity=DemoIdentity("a", frozenset()))
    assert calls == []
    result = await retriever.search(
        SearchQuery(query="query"), identity=DemoIdentity("b", frozenset({"knowledge:read"}))
    )
    assert result.context_tokens <= 2400
    assert len(result.context.encode()) <= 24 * 1024
    assert result.truncated and result.status == "empty"


async def test_missing_model_is_unavailable_without_blocking_other_lifespan_resources(monkeypatch):
    from fastapi.testclient import TestClient

    import app.main as module

    closed = []

    class FailedEmbedding:
        async def initialize(self):
            raise KnowledgeError("embedding_unavailable")

        async def aclose(self):
            closed.append(True)

    monkeypatch.setattr(module, "create_embeddings", lambda settings: FailedEmbedding())
    settings = Settings(_env_file=None, embedding_enabled=True)
    with TestClient(module.create_app(settings)) as client:
        health = client.get("/health").json()
        assert health["status"] == "ok"
        assert health["embedding_status"] == "unavailable"
        assert health["knowledge_ready"] is False
    assert closed == [True]


def test_disabled_startup_and_missing_tokenizer_never_fetch_from_network(tmp_path):
    import os
    import subprocess
    import sys

    environment = os.environ.copy()
    environment["TIKTOKEN_CACHE_DIR"] = str(tmp_path)
    code = """
import requests
from fastapi.testclient import TestClient

def forbidden(*args, **kwargs):
    raise AssertionError("Unexpected implicit network call")
requests.get = forbidden
from app.core.config import Settings
from app.main import create_app
from app.knowledge.chunking import context_tokenizer
from app.knowledge.models import KnowledgeError
with TestClient(create_app(Settings(_env_file=None, model_name=None, database_url=None,
                                    embedding_enabled=False))) as client:
    assert client.get('/health').json()['embedding_status'] == 'disabled'
try:
    context_tokenizer()
except KnowledgeError as error:
    assert str(error) == 'knowledge_tokenizer_unavailable'
else:
    raise AssertionError('Missing local tokenizer cache was accepted')
"""
    subprocess.run(
        [sys.executable, "-c", code], env=environment, check=True, capture_output=True, text=True
    )
