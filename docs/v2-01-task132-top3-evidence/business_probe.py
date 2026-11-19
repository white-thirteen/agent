"""Opt-in Task 1.3.2 business check through the actual configured chat gateway in isolated PG."""

import asyncio
import json
import tempfile
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import httpx
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.config import Settings
from app.infrastructure.checkpoint import checkpoint_serializer
from app.knowledge.chunking import prepare_document
from app.knowledge.fusion import fuse
from app.knowledge.models import EvidenceReference, ManifestEntry, SearchQuery
from app.main import create_app
from app.runtime.context import DemoIdentity
from scripts import run_async
from scripts.compare_v2_01_local_rerank import identity, merge, rankings, read, sha
from scripts.verify_v2_01_quality import corpus_rows, expected_corpus, guarded_settings

cases = [
    ("normal", "模拟退款会扣真实银行卡的钱吗？", "completed"),
    ("Q21", "火星基地量子发动机的保修期是多少年？", "rejected"),
    ("Q22", "真实银行卡退款需要几天到账？", "rejected"),
    ("Q23", "生产账号忘记密码怎样重置？", "rejected"),
    ("Q24", "国际物流费用如何计算？", "rejected"),
    ("conflict", "Demo蓝星计划的资料保留期是多少天？", "rejected"),
]
ROOT = Path("docs/v2-01-task132-top3-evidence")


async def verify_novel(service, fixture):
    questions_path = ROOT / "novel-questions.json"
    questions = read(questions_path)
    qrels = {
        q["id"]: {c["chunk_id"]: q["grades"].get(c["document_id"], 0) for c in fixture["chunks"]}
        for q in questions
    }
    results = {}
    raw = {}
    for question in questions:
        qid, query = question["id"], question["text"]
        vector = await service.candidate_retriever.embeddings.aembed_query(query)
        watermark, dense, sparse = await service.repository.hybrid_candidates(
            vector, query, service.profile, None
        )
        fused = [candidate.evidence for candidate in fuse(dense, sparse)]
        scores = await service.reranker.score(query, fused)
        rrf = [row.model_dump() for row in fused]
        full = sorted(
            [{**row, "retrieval_score": score} for row, score in zip(rrf, scores, strict=True)],
            key=lambda row: (-row["retrieval_score"], identity(row)),
        )
        local = rankings(rrf, full)
        groups = {
            "A": [r.model_dump() for r in dense],
            "B": [r.model_dump() for r in sparse],
            "C": rrf,
            "D": full,
            "E": local,
        }
        results[qid] = [groups]
        raw[qid] = {"watermark": watermark, **groups}
        print("NOVEL", qid, flush=True)
    output = {
        "question_sha256": sha(questions_path),
        "fixture_sha256": sha(ROOT / "fixture.json"),
        "qrels": qrels,
        "results": raw,
        **merge(results, qrels),
    }
    (ROOT / "novel.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


async def main():
    guarded = guarded_settings()
    settings = Settings(embedding_enabled=True, knowledge_retrieval_mode="hybrid", app_env="test")
    assert settings.database_url == guarded.database_url
    assert settings.model_configured
    app = create_app(settings)
    new = uuid4().hex[:12]
    sessions = []
    conflicts = []
    result = {"isolation": "codex-task131-0e62", "cases": [], "model_name": settings.model_name}
    output = ROOT / "business.json"
    fixture = read(ROOT / "fixture.json")
    expected_rows = expected_corpus(fixture)
    assert len(expected_rows) == len(fixture["chunks"]) == 18
    frozen_questions = {q["id"]: q["text"] for q in fixture["questions"]}
    cases[:] = [
        (label, frozen_questions.get(label, question), expected)
        for label, question, expected in cases
    ]
    assert not output.exists()
    async with app.router.lifespan_context(app):
        assert app.state.knowledge_status == "ready"
        async with app.state.pool.connection() as connection:
            chunk_count = (
                await (await connection.execute("SELECT count(*) FROM knowledge_chunks")).fetchone()
            )[0]
            assert chunk_count == 18, chunk_count
        result["normal_frozen_chunk_count"] = chunk_count
        assert set(await corpus_rows(app.state.pool)) == expected_rows
        result["frozen_corpus_exact"] = True
        service = app.state.knowledge_retriever
        profile = json.loads(service.retrieval_profile)
        assert profile["reranker_order"] == "rrf-top3-bge-local-v1"
        result["retrieval_profile"] = profile
        await verify_novel(service, fixture)
        ref = EvidenceReference.model_validate(
            {k: fixture["chunks"][0][k] for k in EvidenceReference.model_fields}
        )
        identity_for_validation = DemoIdentity(
            user_id="dev-user", permission_scopes=frozenset({"knowledge:read"})
        )
        valid = await service.validate_evidence([ref], identity=identity_for_validation)
        stale = await service.validate_evidence(
            [ref.model_copy(update={"document_version": "0" * 64})],
            identity=identity_for_validation,
        )
        assert valid["valid"] and not stale["valid"]
        result["source_validation"] = {"current": valid, "stale_version": stale}
        expected_ranks = {
            row["id"]: row["groups"]["E"]["ranked_chunk_ids"]
            for row in read(ROOT / "fresh-metrics.json")["attempts"]
            if row["round"] == 1
        }
        live = []
        for question in fixture["questions"]:
            qid = question["id"]
            actual = await service.search(
                SearchQuery(query=question["text"], top_k=5),
                identity=identity_for_validation,
            )
            ranked = [row.chunk_id for row in actual.candidates]
            live.append(
                {
                    "id": qid,
                    "match": ranked == expected_ranks[qid],
                    "actual": ranked,
                    "expected": expected_ranks[qid],
                    "packed_ids": [row.chunk_id for row in actual.evidence],
                    "truncated": actual.truncated,
                    "elapsed_ms": actual.elapsed_ms,
                }
            )
        result["runtime_rank_comparisons"] = live
        print("LIVE_RANK_MATCH", sum(row["match"] for row in live), len(live), flush=True)
        saver = AsyncPostgresSaver(app.state.checkpoint_pool, serde=checkpoint_serializer())
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://local", timeout=180
            ) as client:
                for label, question, expected in cases:
                    if label == "conflict":
                        for i, body in enumerate(
                            (
                                "Demo蓝星计划的资料保留期固定为30天。",
                                "Demo蓝星计划的资料保留期固定为90天。",
                            )
                        ):
                            key = f"task132-{new}-conflict-{i}"
                            with tempfile.TemporaryDirectory(prefix="task132-fixture-") as temp:
                                root = Path(temp)
                                (root / "fixture.md").write_text(
                                    "# Demo蓝星计划\n\n" + body, encoding="utf-8"
                                )
                                doc = prepare_document(
                                    root,
                                    ManifestEntry(
                                        document_id=key,
                                        filename="fixture.md",
                                        source_title="Demo蓝星计划",
                                        domain="platform_help",
                                        public_source_key=key,
                                    ),
                                    service.profile,
                                )
                            vectors = await service.candidate_retriever.embeddings.aembed_documents(
                                [x.embedding_text for x in doc.chunks]
                            )
                            if await service.repository.replace(doc, vectors):
                                conflicts.append(key)
                    conversation = f"task132-{new}-{label}"
                    sessions.append(conversation)
                    stamp = perf_counter()
                    entry = {"label": label, "expected": expected}
                    try:
                        async with asyncio.timeout(150):
                            response = await client.post(
                                "/agent/chat",
                                json={
                                    "user_id": "dev-user",
                                    "conversation_id": conversation,
                                    "message": "请查知识库说明：" + question,
                                    "input_mode": "new_task",
                                },
                            )
                        response.raise_for_status()
                        events = [
                            json.loads(line[6:])
                            for line in response.text.splitlines()
                            if line.startswith("data: {")
                        ]
                        entry["events"] = [
                            x
                            for x in events
                            if set(x) & {"content", "status", "error_code", "code"}
                        ]
                        binding = await app.state.sessions.get(
                            user_id="dev-user", conversation_id=conversation
                        )
                        assert binding
                        private = []
                        async for cp in saver.alist(
                            {"configurable": {"thread_id": str(binding.thread_id)}}
                        ):
                            values = cp.checkpoint["channel_values"]
                            if values.get("retrieval_observation") and values.get("result"):
                                private.append(values)
                        state = next(
                            (
                                x
                                for x in private
                                if x["retrieval_observation"].get("mode") == "hybrid"
                            ),
                            None,
                        )
                        if state:
                            obs = state["retrieval_observation"]
                            graph_result = state["result"]
                            sources = [s.model_dump(mode="json") for s in graph_result.sources]
                            entry.update(
                                actual=graph_result.status,
                                approved_answer=graph_result.approved_answer,
                                sources=sources,
                                contract_version=obs["contract_version"],
                                candidate_count=obs["candidate_count"],
                                assessment=state.get("evidence_assessment"),
                                error_code=state.get("error_code"),
                                evidence_document_ids=[e["document_id"] for e in obs["evidence"]],
                            )
                            entry["pass"] = (
                                obs.get("retrieval_profile") == service.retrieval_profile
                                and graph_result.status == expected
                                and (
                                    any(s["document_id"] == "demo-refund-safety" for s in sources)
                                    if expected == "completed"
                                    else not sources
                                    and not graph_result.approved_answer
                                    and state.get("error_code")
                                    == (
                                        "evidence_conflicting"
                                        if label == "conflict"
                                        else "evidence_insufficient"
                                    )
                                )
                            )
                        else:
                            entry.update(actual="no_completed_hybrid_node_state", **{"pass": False})
                    except (TimeoutError, httpx.HTTPError, AssertionError) as error:
                        entry.update(actual=type(error).__name__, **{"pass": False})
                    finally:
                        entry["seconds"] = round(perf_counter() - stamp, 3)
                        result["cases"].append(entry)
                        print("Business case", label, entry["actual"], entry["pass"], flush=True)
                        output.write_text(
                            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8",
                        )
        finally:
            await app.state.agent_runtime.shutdown()
            for conversation in sessions:
                binding = await app.state.sessions.get(
                    user_id="dev-user", conversation_id=conversation
                )
                if binding:
                    await saver.adelete_thread(str(binding.thread_id))
            async with app.state.pool.connection() as connection:
                await connection.execute(
                    "DELETE FROM sessions WHERE user_id=%s AND conversation_id=ANY(%s)",
                    ("dev-user", sessions),
                )
            for key in conflicts:
                await service.repository.remove(key)
            assert set(await corpus_rows(app.state.pool)) == expected_rows
            result["frozen_corpus_restored"] = True
            result["exact_cleanup"] = {
                "conversations": len(sessions),
                "conflict_documents": len(conflicts),
            }
            output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    result["passed"] = sum(x["pass"] for x in result["cases"])
    result["resources_closed"] = app.state.pool.closed and app.state.checkpoint_pool.closed
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "Business results",
        result["passed"],
        len(cases),
        "resources closed",
        result["resources_closed"],
        flush=True,
    )


run_async(main())
