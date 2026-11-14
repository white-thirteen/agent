"""Stable ingestion and evidence contracts; no user identity comes from search args."""

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EmbeddingProfile(Contract):
    provider: str = "qwen_local"
    model: str = "Qwen/Qwen3-Embedding-0.6B"
    dimensions: int = 1024
    tokenizer: str = "Qwen3"
    revision: str
    weights_revision: str
    normalization: str = "l2"
    dtype: str = "float32"
    query_prompt: str

    @property
    def key(self) -> str:
        return canonical(self.model_dump())


class ManifestEntry(Contract):
    document_id: str = Field(min_length=1, max_length=128)
    filename: str
    source_title: str = Field(min_length=1, max_length=200)
    domain: Literal["platform_help", "after_sales_help"]
    public_source_key: str = Field(pattern=r"^[a-zA-Z0-9_-]+$", max_length=128)


class Chunk(Contract):
    chunk_id: str
    document_id: str
    document_version: str
    ordinal: int
    section: str | None
    page: None = None
    line_start: int
    line_end: int
    content: str
    content_hash: str
    token_count: int
    embedding_text: str


class Document(Contract):
    entry: ManifestEntry
    document_version: str
    content_hash: str
    embedding_profile: str
    chunks: tuple[Chunk, ...]


class SearchQuery(Contract):
    query: str = Field(min_length=1, max_length=2000)
    domain: Literal["platform_help", "after_sales_help"] | None = None
    top_k: int = Field(default=3, strict=True, ge=1, le=5)


class EvidenceReference(Contract):
    document_id: str
    document_version: str
    chunk_id: str
    content_hash: str


class EvidenceChunk(EvidenceReference):
    evidence_id: str
    source_title: str
    public_source_key: str
    section: str | None
    page: None = None
    line_start: int
    line_end: int
    content: str
    retrieval_score: float
    domain: str
    is_current_version: bool = True


class SearchResult(Contract):
    status: Literal["found", "empty"]
    evidence: tuple[EvidenceChunk, ...]
    embedding_profile: str
    query_fingerprint: str
    context_tokens: int
    truncated: bool
    embedding_request_attempts: int
    candidate_count: int
    elapsed_ms: float
    context: str


class KnowledgeError(RuntimeError):
    """Safe knowledge resource failure code, without raw model/DB configuration."""
