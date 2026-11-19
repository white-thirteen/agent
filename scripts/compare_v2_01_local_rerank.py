"""Compare frozen BGE receipts using the production Top3 ordering function."""

import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import mean

from app.knowledge.retriever import local_rerank_order

METRICS = ("recall3", "mrr3", "ndcg3", "recall10")
GROUPS = ("A", "B", "C", "D", "E")


def identity(row):
    return tuple(
        row[key] for key in ("document_id", "document_version", "chunk_id", "content_hash")
    )


def rankings(retrieval, scored):
    """Use identical candidate identities and logits for full and local ranking."""
    identities = [identity(row) for row in retrieval]
    scores = {identity(row): row["retrieval_score"] for row in scored}
    assert len(retrieval) == len(scored) == len(scores) == len(set(identities))
    assert set(identities) == scores.keys()
    assert all(math.isfinite(score) for score in scores.values())
    assert [identity(row) for row in scored] == sorted(
        identities, key=lambda key: (-scores[key], key)
    )
    by_identity = {identity(row): row for row in scored}
    for row in retrieval:
        assert {**row, "retrieval_score": scores[identity(row)]} == by_identity[identity(row)]
    order = local_rerank_order([scores[key] for key in identities], identities)
    assert set(order[:3]) == set(range(min(3, len(identities))))
    assert order[3:] == tuple(range(3, len(identities)))
    return [by_identity[identities[i]] for i in order]


def metrics(rows, grades):
    if not any(grade >= 2 for grade in grades.values()):
        return None
    actual = [grades.get(row["chunk_id"], 0) for row in rows]
    relevant = sum(grade >= 2 for grade in grades.values())
    ideal = sorted(grades.values(), reverse=True)

    def dcg(values):
        return sum((2**grade - 1) / math.log2(rank + 1) for rank, grade in enumerate(values[:3], 1))

    return {
        "recall3": sum(grade >= 2 for grade in actual[:3]) / relevant,
        "mrr3": next((1 / i for i, grade in enumerate(actual[:3], 1) if grade >= 2), 0),
        "ndcg3": dcg(actual) / dcg(ideal),
        "recall10": sum(grade >= 2 for grade in actual[:10]) / relevant,
    }


def merge(group_rows, qrels):
    per_question = {}
    for qid, grades in qrels.items():
        attempts = group_rows[qid]
        per_question[qid] = {
            group: average([metrics(attempt[group], grades) for attempt in attempts])
            for group in GROUPS
        }
    macro = {group: average([row[group] for row in per_question.values()]) for group in GROUPS}
    changes = {"improved": [], "degraded": [], "unchanged": []}
    for qid, row in per_question.items():
        if row["C"] is None:
            continue
        delta = row["E"]["ndcg3"] - row["C"]["ndcg3"]
        label = "unchanged" if abs(delta) < 1e-12 else ("improved" if delta > 0 else "degraded")
        changes[label].append(qid)
    return {"macro": macro, "questions": per_question, "local_vs_rrf_ndcg3": changes}


def average(values):
    eligible = [v for v in values if v is not None]
    return {k: mean(v[k] for v in eligible) for k in METRICS} if eligible else None


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare(folder):
    fixture_path, qwen_path, bge_path = (
        folder / name for name in ("fixture.json", "qwen.json", "bge.json")
    )
    fixture, qwen, bge = (read(path) for path in (fixture_path, qwen_path, bge_path))
    assert qwen["fixture_sha256"] == bge["fixture_sha256"] == sha(fixture_path)
    assert bge["qwen_sha256"] == sha(qwen_path)
    expected = {(i, q["id"]) for i in range(1, qwen["rounds"] + 1) for q in fixture["questions"]}
    retrieval = {(row["round"], row["id"]): row for row in qwen["results"]}
    scored = {(row["round"], row["id"]): row for row in bge["results"]}
    assert expected == retrieval.keys() == scored.keys()
    assert len(expected) == len(qwen["results"]) == len(bge["results"])
    corpus = {identity(row): row["content"] for row in fixture["chunks"]}
    assert len(corpus) == len(fixture["chunks"])
    result = {qid: [] for qid in fixture["qrels"]}
    errors = []
    per_round = []
    for key in sorted(expected):
        it, qid = key
        base, full = retrieval[key], scored[key]
        if base.get("error") or full.get("error"):
            errors.append(
                {"round": it, "id": qid, "retrieval": base["error"], "rerank": full["error"]}
            )
        groups = {group: base.get(group, []) for group in "ABC"}
        groups["D"] = full.get("D", [])
        groups["E"] = [] if full.get("error") else rankings(groups["C"], groups["D"])
        for group in groups.values():
            assert all(corpus[identity(row)] == row["content"] for row in group)
        per_round.append(
            {
                "round": it,
                "id": qid,
                "groups": {
                    group: {
                        "metrics": metrics(rows, fixture["qrels"][qid]),
                        "ranked_chunk_ids": [row["chunk_id"] for row in rows],
                    }
                    for group, rows in groups.items()
                },
            }
        )
        result[qid].append(groups)
    report = merge(result, fixture["qrels"])
    timings = {}
    for source, field in (
        (retrieval, "embedding_ms"),
        (retrieval, "database_ms"),
        (scored, "bge_ms"),
    ):
        values = sorted(
            row[field]
            for key, row in source.items()
            if any(grade >= 2 for grade in fixture["qrels"][key[1]].values())
            and not row.get("error")
            and field in row
        )
        if values:
            timings[field] = {
                "count": len(values),
                "p50_ms": values[math.ceil(0.50 * len(values)) - 1],
                "p95_ms": values[math.ceil(0.95 * len(values)) - 1],
            }
    report.update(
        rounds=qwen["rounds"],
        errors=errors,
        attempts=per_round,
        timing_by_stage=timings,
        sha256={path.name: sha(path) for path in (fixture_path, qwen_path, bge_path)},
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_directory", type=Path)
    options = parser.parse_args()
    print(json.dumps(compare(options.evidence_directory), ensure_ascii=False, indent=2))
