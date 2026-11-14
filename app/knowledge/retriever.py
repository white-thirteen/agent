"""Public evidence retrieval; identity and scopes are supplied only by trusted callers."""

import asyncio
from time import perf_counter

from app.knowledge.chunking import token_count
from app.knowledge.models import KnowledgeError, SearchQuery, SearchResult, canonical, digest
from app.runtime.context import DemoIdentity


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
