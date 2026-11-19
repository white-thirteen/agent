"""Fuse route rankings without mixing their native score scales."""

from app.knowledge.models import HybridCandidate, RankedScore, RetrievalCandidate


def fuse(dense, sparse):
    entries = {}
    for route, rows in (("dense", dense), ("sparse", sparse)):
        for rank, evidence in enumerate(rows, 1):
            key = (
                evidence.document_id,
                evidence.document_version,
                evidence.chunk_id,
                evidence.content_hash,
            )
            if key not in entries:
                entries[key] = {"evidence": evidence, "dense": None, "sparse": None}
            entries[key][route] = RankedScore(rank=rank, score=evidence.retrieval_score)
    result = []
    for key, entry in entries.items():
        score = sum(1 / (60 + item.rank) for item in (entry["dense"], entry["sparse"]) if item)
        result.append(
            (
                key,
                HybridCandidate(
                    evidence=entry["evidence"],
                    scores=RetrievalCandidate(
                        document_id=key[0],
                        document_version=key[1],
                        chunk_id=key[2],
                        content_hash=key[3],
                        dense=entry["dense"],
                        sparse=entry["sparse"],
                        rrf_score=score,
                    ),
                ),
            )
        )
    result.sort(key=lambda item: (-item[1].scores.rrf_score, item[0]))
    return tuple(item[1] for item in result[:10])
