"""RRF preserves route scores and complete source identity."""

import pytest

from app.knowledge.fusion import fuse
from app.knowledge.models import EvidenceChunk


def evidence(document_id, score):
    return EvidenceChunk(
        document_id=document_id,
        document_version="v1",
        chunk_id=document_id,
        content_hash="same",
        evidence_id=document_id,
        source_title="title",
        public_source_key=document_id,
        section=None,
        line_start=1,
        line_end=1,
        content="same",
        retrieval_score=score,
        domain="platform_help",
    )


def test_rrf_keeps_source_identity_scores_and_stable_ties():
    a, b = evidence("a", 0.8), evidence("b", 0.6)
    result = fuse([b, a], [evidence("a", -2.0), evidence("b", -1.0)])
    assert [item.evidence.document_id for item in result] == ["a", "b"]
    assert result[0].scores.dense.score == 0.8
    assert result[0].scores.sparse.score == -2.0
    assert result[0].scores.rrf_score == pytest.approx(1 / 61 + 1 / 62)
    assert fuse([], []) == ()
