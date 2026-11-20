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


class SparseIndexProfile(Contract):
    """Candidate index identity; declaring a profile does not activate an index.

    BM25 statistics and defaults belong to the pinned extension, not a domain's
    filtered subset. Changing this profile never changes source/embedding identity.
    The result identity is returned alongside the BM25 score but is not itself an
    indexed text field in pg_textsearch.
    """

    extension: Literal["pg_textsearch"] = "pg_textsearch"
    extension_version: Literal["1.5.1"] = "1.5.1"
    result_identity_field: Literal["chunk_id"] = "chunk_id"
    text_field: Literal["search_text"] = "search_text"
    indexed_fields: tuple[Literal["search_text"]] = ("search_text",)
    text_config: Literal["public.chinese"] = "public.chinese"
    tokenizer: Literal["zhparser"] = "zhparser"
    tokenizer_version: Literal["2.4"] = "2.4"
    dictionary_version: Literal["scws-1.2.3"] = "scws-1.2.3"
    bm25_parameters: Literal["extension_defaults"] = "extension_defaults"
    score_order: Literal["ascending_negative"] = "ascending_negative"
    input_format: Literal["title-section-content-v1"] = "title-section-content-v1"

    @property
    def key(self) -> str:
        return canonical(self.model_dump())


class RetrievalProfile(Contract):
    """Hybrid configuration identity, instantiated only with verified model revisions."""

    embedding_profile: str
    sparse_profile: str
    dense_candidates: Literal[10] = 10
    sparse_candidates: Literal[10] = 10
    fused_candidates: Literal[10] = 10
    rrf_constant: Literal[60] = 60
    rrf_weights: tuple[Literal[1], Literal[1]] = (1, 1)
    reranker_model: Literal["BAAI/bge-reranker-base"] = "BAAI/bge-reranker-base"
    reranker_revision: str
    reranker_tokenizer_revision: str
    reranker_input_format: Literal["query-title-section-content-v1"] = (
        "query-title-section-content-v1"
    )
    reranker_score: Literal["raw_logit"] = "raw_logit"
    reranker_order: Literal["rrf-top3-bge-local-v1"] = "rrf-top3-bge-local-v1"
    reranker_max_tokens: Literal[512] = 512
    context_policy: Literal["complete-chunks-2400tokens-24kib-v1"] = (
        "complete-chunks-2400tokens-24kib-v1"
    )

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


class RankedScore(Contract):
    """One route's one-based rank and native score; never a probability."""

    rank: int = Field(strict=True, ge=1, le=10)
    score: float = Field(allow_inf_nan=False)


class RetrievalCandidate(EvidenceReference):
    """Diagnostic identity and distinct score spaces, without copying source text."""

    dense: RankedScore | None = None
    sparse: RankedScore | None = None
    rrf_score: float = Field(allow_inf_nan=False)
    reranker_score: float | None = Field(default=None, allow_inf_nan=False)


class HybridCandidate(Contract):
    """Unbound retrieval candidate for the later reranking step."""

    evidence: EvidenceChunk
    scores: RetrievalCandidate


class HybridCandidates(Contract):
    status: Literal["found", "empty"]
    embedding_profile: str
    sparse_profile: str
    index_watermark: int = Field(strict=True, ge=1)
    candidates: tuple[HybridCandidate, ...]


class HybridSearchResult(SearchResult):
    """V2 wire contract. Required discriminators prevent accepting V1 cached results.

    EvidenceChunk.retrieval_score is the raw reranker logit, not a sort key for
    the whole result: only the RRF top three are reordered by that score.
    Route-native scores remain separate in candidates.
    V1 tools/Graph continue to parse SearchResult until the separately authorized
    integration Task switches the tool version and parser together.
    """

    contract_version: Literal[2]
    mode: Literal["hybrid"]
    retrieval_profile: str
    sparse_profile: str
    index_watermark: int = Field(strict=True, ge=1)
    candidates: tuple[RetrievalCandidate, ...]


class KnowledgeError(RuntimeError):
    """Safe knowledge resource failure code, without raw model/DB configuration."""
