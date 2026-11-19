"""Public evidence retrieval; identity and scopes are supplied only by trusted callers."""

import asyncio
from collections.abc import Sequence
from time import perf_counter

from app.knowledge.chunking import token_count
from app.knowledge.fusion import fuse
from app.knowledge.models import (
    HybridCandidates,
    HybridSearchResult,
    KnowledgeError,
    RetrievalProfile,
    SearchQuery,
    SearchResult,
    SparseIndexProfile,
    canonical,
    digest,
)
from app.runtime.context import DemoIdentity


def local_rerank_order(
    scores: Sequence[float], identities: Sequence[tuple[str, str, str, str]]
) -> tuple[int, ...]:
    """Return RRF indices with only its first three ordered by raw BGE score."""
    pairs = list(zip(scores, identities, strict=True))
    prefix = sorted(range(min(3, len(pairs))), key=lambda i: (-pairs[i][0], pairs[i][1]))
    return tuple(prefix) + tuple(range(3, len(pairs)))


class VectorRetriever:
    def __init__(self, repository, embeddings, profile: str):
        self.repository = repository
        self.embeddings = embeddings
        self.profile = profile

    async def search(self, query: SearchQuery, *, identity: DemoIdentity) -> SearchResult:
        if "knowledge:read" not in identity.permission_scopes:
            raise KnowledgeError("policy_denied")
        if not query.query.strip() or token_count(query.query) > 512:
            raise ValueError("Query must contain 1..512 cl100k_base tokens")
        started = perf_counter()
        try:
            async with asyncio.timeout(15):
                vector = await self.embeddings.aembed_query(query.query)
                candidates = await self.repository.search(vector, self.profile, query.domain)
        except TimeoutError:
            raise KnowledgeError("retrieval_timeout") from None
        selected = []
        context = "[]"
        truncated = False
        for candidate in candidates[: query.top_k]:
            packed = canonical([item.model_dump() for item in [*selected, candidate]])
            if token_count(packed) > 2400 or len(packed.encode("utf-8")) > 24 * 1024:
                truncated = True
                continue
            selected.append(candidate)
            context = packed
        return SearchResult(
            status="found" if selected else "empty",
            evidence=tuple(selected),
            embedding_profile=self.profile,
            query_fingerprint=digest(query.query),
            context_tokens=token_count(context),
            truncated=truncated,
            embedding_request_attempts=1,
            candidate_count=len(candidates),
            elapsed_ms=(perf_counter() - started) * 1000,
            context=context,
        )

    async def validate_evidence(self, refs, *, identity: DemoIdentity):
        if "knowledge:read" not in identity.permission_scopes:
            raise KnowledgeError("policy_denied")
        return await self.repository.validate_evidence(refs)


class HybridCandidateRetriever:
    """Retrieve candidates only; reranking and public Graph wiring are separate tasks."""

    def __init__(self, repository, embeddings, profile: str):
        self.repository = repository
        self.embeddings = embeddings
        self.profile = profile

    async def search(self, query: SearchQuery, *, identity: DemoIdentity) -> HybridCandidates:
        if "knowledge:read" not in identity.permission_scopes:
            raise KnowledgeError("policy_denied")
        if not query.query.strip() or token_count(query.query) > 512:
            raise ValueError("Query must contain 1..512 cl100k_base tokens")
        vector = await self.embeddings.aembed_query(query.query)
        watermark, dense, sparse = await self.repository.hybrid_candidates(
            vector, query.query, self.profile, query.domain
        )
        candidates = fuse(dense, sparse)
        return HybridCandidates(
            status="found" if candidates else "empty",
            embedding_profile=self.profile,
            sparse_profile=SparseIndexProfile().key,
            index_watermark=watermark,
            candidates=candidates,
        )


class HybridRetriever:
    """Fuse, rerank and pack complete evidence under one retrieval deadline."""

    def __init__(self, repository, embeddings, reranker, profile: str, timeout: float):
        from app.knowledge.reranker import BGE_REVISION

        self.candidate_retriever = HybridCandidateRetriever(repository, embeddings, profile)
        self.repository = repository
        self.reranker = reranker
        self.profile = profile
        self.retrieval_profile = RetrievalProfile(
            embedding_profile=profile,
            sparse_profile=SparseIndexProfile().key,
            reranker_revision=BGE_REVISION,
            reranker_tokenizer_revision=BGE_REVISION,
        ).key
        self.timeout = timeout

    async def search(self, query: SearchQuery, *, identity: DemoIdentity) -> HybridSearchResult:
        started = perf_counter()
        try:
            async with asyncio.timeout(self.timeout):
                found = await self.candidate_retriever.search(query, identity=identity)
                candidates = found.candidates
                scores = (
                    await self.reranker.score(query.query, [c.evidence for c in candidates])
                    if candidates
                    else []
                )
                order = local_rerank_order(
                    scores,
                    [
                        (
                            c.scores.document_id,
                            c.scores.document_version,
                            c.scores.chunk_id,
                            c.scores.content_hash,
                        )
                        for c in candidates
                    ],
                )
                selected = []
                context = "[]"
                truncated = False
                diagnostics = []
                for index in order:
                    candidate, score = candidates[index], scores[index]
                    diagnostics.append(
                        candidate.scores.model_copy(update={"reranker_score": score})
                    )
                    if len(selected) >= query.top_k:
                        continue
                    evidence = candidate.evidence.model_copy(update={"retrieval_score": score})
                    packed = canonical([item.model_dump() for item in [*selected, evidence]])
                    if token_count(packed) > 2400 or len(packed.encode("utf-8")) > 24 * 1024:
                        truncated = True
                        continue
                    selected.append(evidence)
                    context = packed
                if candidates and not selected:
                    raise KnowledgeError("retrieval_context_budget_exceeded")
                return HybridSearchResult(
                    contract_version=2,
                    mode="hybrid",
                    retrieval_profile=self.retrieval_profile,
                    sparse_profile=found.sparse_profile,
                    index_watermark=found.index_watermark,
                    candidates=tuple(diagnostics),
                    status="found" if selected else "empty",
                    evidence=tuple(selected),
                    embedding_profile=self.profile,
                    query_fingerprint=digest(query.query),
                    context_tokens=token_count(context),
                    truncated=truncated,
                    embedding_request_attempts=1,
                    candidate_count=len(candidates),
                    elapsed_ms=(perf_counter() - started) * 1000,
                    context=context,
                )
        except TimeoutError:
            raise KnowledgeError("retrieval_timeout") from None

    async def validate_evidence(self, refs, *, identity: DemoIdentity):
        if "knowledge:read" not in identity.permission_scopes:
            raise KnowledgeError("policy_denied")
        return await self.repository.validate_evidence(refs)
