"""Frozen Task 1.3.2 fixture and two-stage, isolated real-model quality receipt.

Run via task131-local-validation.py pytest with TASK132_PHASE=freeze|qwen|bge.
Freeze must precede either model stage; stages avoid co-resident models.
"""

import ctypes
import hashlib
import json
import math
import os
import platform
import time
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from app.core.config import Settings
from app.infrastructure.postgres import open_pool
from app.knowledge.chunking import prepare_document, read_manifest, token_count
from app.knowledge.embedding import create_embeddings, validate_vectors
from app.knowledge.fusion import fuse
from app.knowledge.ingest import KnowledgeIngestor
from app.knowledge.models import EvidenceChunk, KnowledgeError, canonical, digest
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.reranker import BGEReranker
from app.knowledge.sparse import INDEX_NAME, check_sparse_ready
from scripts import run_async

ROOT = Path("data/v2-01-quality")
OUT = Path(os.environ.get("TASK132_OUTPUT_DIR", "docs/v2-01-task132-evidence"))
QUESTIONS = [
    ("当前提供哪些演示用户？", "account-help"),
    ("选择 dev-user 是否等于真实生产登录？", "account-help"),
    ("如何发起模拟退款申请？", "refund-entry"),
    ("申请模拟退款需要提供什么信息？", "refund-entry"),
    ("知识说明可以改变退款资格和金额吗？", "refund-entry"),
    ("等待审批时，在聊天中说“同意”可以批准吗？", "approval-wait"),
    ("审批通过后恢复原任务还是另建任务？", "approval-wait"),
    ("一次审批能放行其他任意调用吗？", "approval-wait"),
    ("模拟退款会扣真实银行卡的钱吗？", "refund-safety"),
    ("退款结果未知时可以直接再退一次吗？", "refund-safety"),
    ("相同退款操作如何避免重复副作用？", "refund-safety"),
    ("查询订单需要提供什么？", "order-query"),
    ("能查看其他演示用户的订单吗？", "order-query"),
    ("关闭聊天页面后，已受理任务会停止吗？", "stream-help"),
    ("断开连接后应如何核对任务结果？", "stream-help"),
    ("If the stream disconnects, does the accepted task continue?", "stream-help"),
    ("Does this demo connect to a real payment provider?", "refund-safety"),
    ("Who handles a pending refund approval?", "approval-wait"),
    ("dev-user 和 demo-user-b 是生产认证账号吗？", "account-help"),
    ("申请退款后，谁审批，审批后如何继续？", "refund-entry,approval-wait"),
    ("火星基地量子发动机的保修期是多少年？", ""),
    ("真实银行卡退款需要几天到账？", ""),
    ("生产账号忘记密码怎样重置？", ""),
    ("国际物流费用如何计算？", ""),
]


def dump(path, obj):
    with path.open("x", encoding="utf-8") as output:
        output.write(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_error(exc):
    return f"KnowledgeError:{exc}" if isinstance(exc, KnowledgeError) else type(exc).__name__


def memory_snapshot():
    """Windows process working-set and physical-memory receipt in bytes."""

    class ProcessMemory(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
            (name, ctypes.c_size_t)
            for name in (
                "PeakWorkingSetSize",
                "WorkingSetSize",
                "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage",
                "PagefileUsage",
                "PeakPagefileUsage",
            )
        ]

    class MemoryStatus(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + [
            (name, ctypes.c_ulonglong)
            for name in (
                "ullTotalPhys",
                "ullAvailPhys",
                "ullTotalPageFile",
                "ullAvailPageFile",
                "ullTotalVirtual",
                "ullAvailVirtual",
                "ullAvailExtendedVirtual",
            )
        ]

    process = ProcessMemory()
    process.cb = ctypes.sizeof(process)
    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(status)
    kernel = ctypes.windll.kernel32
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    if not ctypes.windll.psapi.GetProcessMemoryInfo(
        ctypes.c_void_p(kernel.GetCurrentProcess()), ctypes.byref(process), process.cb
    ) or not kernel.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise OSError("Windows memory metrics unavailable")
    return {
        "working_set_bytes": process.WorkingSetSize,
        "peak_working_set_bytes": process.PeakWorkingSetSize,
        "available_physical_bytes": status.ullAvailPhys,
        "total_physical_bytes": status.ullTotalPhys,
    }


def guarded_settings():
    """Never allow fixture operations against any other database or identity."""
    settings = Settings(_env_file=None, app_env="test")
    info = conninfo_to_dict(settings.database_url.get_secret_value())
    assert (info.get("host"), info.get("port"), info.get("dbname"), info.get("user")) == (
        "127.0.0.1",
        "56431",
        "agent_demo",
        "agent_app",
    )
    with psycopg.connect(
        settings.database_url.get_secret_value(), options="-c default_transaction_read_only=on"
    ) as conn:
        row = conn.execute(
            "SELECT current_setting('server_version_num'), "
            "shobj_description(oid,'pg_database') FROM pg_database "
            "WHERE datname=current_database()"
        ).fetchone()
        assert row == ("170012", "codex-task131-0e62")
    return settings


def freeze():
    OUT.mkdir(exist_ok=True)
    target = OUT / "fixture.json"
    if target.exists():
        raise RuntimeError("Frozen fixture already exists; preserve it")
    s = guarded_settings()
    with psycopg.connect(
        s.database_url.get_secret_value(), options="-c default_transaction_read_only=on"
    ) as c:
        rows = c.execute(
            "SELECT document_id,document_version,content_hash,embedding_profile "
            "FROM knowledge_documents ORDER BY document_id"
        ).fetchall()
        assert {r[0] for r in rows} == {
            f"demo-{x}"
            for x in (
                "account-help",
                "order-query",
                "refund-entry",
                "approval-wait",
                "stream-help",
                "refund-safety",
            )
        }
        profiles = {r[3] for r in rows}
        assert len(profiles) == 1
        profile = profiles.pop()
        dbchunks = c.execute(
            "SELECT d.document_id,d.document_version,c.chunk_id,c.content_hash,c.content,"
            "c.line_start,c.line_end FROM knowledge_documents d JOIN knowledge_chunks c "
            "USING(document_id,document_version) ORDER BY d.document_id,c.ordinal"
        ).fetchall()
    original = []
    manifest = read_manifest(Path("data/knowledge"), Path("data/knowledge/manifest.json"))
    for entry in manifest:
        doc = prepare_document(Path("data/knowledge"), entry, profile)
        original.append(doc)
    chunks = []
    for doc in original + [
        prepare_document(ROOT, e, profile) for e in read_manifest(ROOT, ROOT / "manifest.json")
    ]:
        for c in doc.chunks:
            chunks.append(
                dict(
                    document_id=c.document_id,
                    document_version=c.document_version,
                    chunk_id=c.chunk_id,
                    content_hash=c.content_hash,
                    content=c.content,
                    line_start=c.line_start,
                    line_end=c.line_end,
                )
            )
    actual = {(r[0], r[1], r[2], r[3], r[4], r[5], r[6]) for r in dbchunks}
    expected = {
        (
            c["document_id"],
            c["document_version"],
            c["chunk_id"],
            c["content_hash"],
            c["content"],
            c["line_start"],
            c["line_end"],
        )
        for c in chunks
        if c["document_id"].startswith("demo-")
    }
    assert actual == expected
    # Background is assigned by subject from source content, not observed rankings.
    background = {
        1: [2],
        2: [2],
        3: [7, 8, 9],
        4: [7, 8],
        5: [7, 8],
        6: [9, 10],
        7: [9, 10],
        8: [9, 10],
        9: [7, 8, 11],
        10: [7, 12],
        11: [7, 12],
        12: [3, 4],
        13: [2, 3, 4],
        14: [1, 5, 6],
        15: [1, 5, 6],
        16: [1, 5, 6],
        17: [11],
        18: [9, 10],
        19: [2],
        20: [7, 8, 9, 10],
        22: [7, 11],
        23: [2],
    }
    related = {
        **{i: ["approval-wait", "refund-safety"] for i in (3, 4, 5)},
        **{i: ["refund-entry"] for i in (6, 7, 8, 9, 10, 11, 18)},
        13: ["account-help"],
        20: ["refund-safety"],
        22: ["refund-safety"],
        23: ["account-help"],
    }
    labels = {}
    for i, (_question, answer) in enumerate(QUESTIONS, 1):
        expected_ids = {f"demo-{v}" for v in answer.split(",") if v}
        # Grade 2 for each partial source of the two-source question; 3 for complete evidence.
        background_ids = {f"task132-distractor-{n:02}" for n in background.get(i, [])}
        background_ids.update(f"demo-{name}" for name in related.get(i, []))
        labels[f"Q{i:02}"] = {
            c["chunk_id"]: (
                (2 if i == 20 else 3)
                if c["document_id"] in expected_ids
                else 1
                if c["document_id"] in background_ids
                else 0
            )
            for c in chunks
        }
    files = (
        [Path("data/knowledge") / e.filename for e in manifest]
        + [ROOT / e.filename for e in read_manifest(ROOT, ROOT / "manifest.json")]
        + [Path("data/knowledge/manifest.json"), ROOT / "manifest.json"]
    )
    dump(
        target,
        dict(
            parser="parser-v1",
            chunker="chunker-v1",
            profile=profile,
            domain=None,
            permission="knowledge:read",
            questions=[
                dict(id=f"Q{i:02}", text=q, expected=a) for i, (q, a) in enumerate(QUESTIONS, 1)
            ],
            sources={str(p).replace("\\", "/"): sha(p) for p in files},
            chunks=chunks,
            qrels=labels,
            annotation=(
                "Labels assigned before retrieval. Grade 0 = no answer evidence; "
                "grade 1 = background, grade 2 = partial, grade 3 = complete."
            ),
        ),
    )
    print("FROZEN", sha(target), "chunks", len(chunks), "questions", len(QUESTIONS), flush=True)


def load_frozen():
    fixture = json.loads((OUT / "fixture.json").read_text(encoding="utf-8"))
    for path, expected in fixture["sources"].items():
        assert sha(Path(path)) == expected
    return fixture


async def qwen():
    fixture = load_frozen()
    s = guarded_settings()
    pool = await open_pool(s)
    model = create_embeddings(s)
    try:
        start = time.perf_counter()
        await model.initialize()
        cold = time.perf_counter() - start
        memory_loaded = memory_snapshot()
        assert model.profile.key == fixture["profile"]
        repo = KnowledgeRepository(pool)
        ingestion = await KnowledgeIngestor(
            repo, model, model.profile.key, s.embedding_batch_size
        ).ingest(ROOT, ROOT / "manifest.json")
        print("INGEST", len(ingestion["published"]), len(ingestion["unchanged"]), flush=True)
        await model.aembed_query(fixture["questions"][0]["text"])  # warm model once
        results = []
        rounds = int(os.environ.get("TASK132_ROUNDS", "1"))
        for round_no in range(rounds):
            for q in fixture["questions"]:
                entry = {"round": round_no + 1, "id": q["id"]}
                start = time.perf_counter()
                try:
                    vector = await model.aembed_query(q["text"])
                    mid = time.perf_counter()
                    watermark, dense, sparse = await repo.hybrid_candidates(
                        vector, q["text"], model.profile.key, None
                    )
                    end = time.perf_counter()
                    fused = fuse(dense, sparse)
                    entry.update(
                        embedding_ms=(mid - start) * 1000,
                        database_ms=(end - mid) * 1000,
                        watermark=watermark,
                        A=[x.model_dump() for x in dense],
                        B=[x.model_dump() for x in sparse],
                        C=[x.evidence.model_dump() for x in fused],
                        error=None,
                    )
                except Exception as exc:
                    entry.update(
                        error=safe_error(exc),
                        elapsed_ms=(time.perf_counter() - start) * 1000,
                    )
                results.append(entry)
                print("QWEN", round_no + 1, q["id"], entry["error"], flush=True)
        dump(
            OUT / "qwen.json",
            dict(
                fixture_sha256=sha(OUT / "fixture.json"),
                cold_seconds=cold,
                rounds=rounds,
                results=results,
                ingestion=ingestion,
                platform=platform.platform(),
                memory_after_load=memory_loaded,
                memory_after_run=memory_snapshot(),
            ),
        )
    finally:
        await model.aclose()
        await pool.close()


async def bge():
    fixture = load_frozen()
    source = json.loads((OUT / "qwen.json").read_text(encoding="utf-8"))
    assert source["fixture_sha256"] == sha(OUT / "fixture.json")
    s = Settings(_env_file=None, app_env="test")
    model = BGEReranker(s)
    from app.knowledge.models import EvidenceChunk

    try:
        start = time.perf_counter()
        await model.initialize()
        cold = time.perf_counter() - start
        memory_loaded = memory_snapshot()
        result = []
        warm = next(row for row in source["results"] if not row["error"] and row["C"])
        await model.score(
            fixture["questions"][int(warm["id"][1:]) - 1]["text"],
            [EvidenceChunk.model_validate(x) for x in warm["C"]],
        )
        for row in source["results"]:
            item = {"round": row["round"], "id": row["id"]}
            if row["error"]:
                item["error"] = "upstream:" + row["error"]
                result.append(item)
                continue
            q = fixture["questions"][int(row["id"][1:]) - 1]["text"]
            candidates = [EvidenceChunk.model_validate(x) for x in row["C"]]
            start = time.perf_counter()
            try:
                scores = await model.score(q, candidates) if candidates else []
                ranked = sorted(
                    zip(candidates, scores, strict=True),
                    key=lambda x: (
                        -x[1],
                        x[0].document_id,
                        x[0].document_version,
                        x[0].chunk_id,
                        x[0].content_hash,
                    ),
                )
                item.update(
                    D=[
                        e.model_copy(update={"retrieval_score": score}).model_dump()
                        for e, score in ranked
                    ],
                    bge_ms=(time.perf_counter() - start) * 1000,
                    error=None,
                )
            except Exception as exc:
                item.update(
                    error=safe_error(exc),
                    bge_ms=(time.perf_counter() - start) * 1000,
                )
            result.append(item)
            print("BGE", item["round"], item["id"], item["error"], flush=True)
        dump(
            OUT / "bge.json",
            dict(
                fixture_sha256=sha(OUT / "fixture.json"),
                qwen_sha256=sha(OUT / "qwen.json"),
                cold_seconds=cold,
                memory_after_load=memory_loaded,
                memory_after_run=memory_snapshot(),
                results=result,
            ),
        )
    finally:
        await model.aclose()


# The production repository exposes Top 10 only as a paired query. These two
# evaluation-only queries mirror its projections, predicates and tie-breaking,
# so each route can be timed without charging it for the other route.
async def single_route(pool, route, query, profile, vector=None):
    fields = (
        "c.chunk_id,c.document_id,c.document_version,c.content_hash,c.content,"
        "c.section,c.line_start,c.line_end,d.source_title,d.public_source_key,d.domain,"
    )
    source = (
        " FROM knowledge_chunks c JOIN knowledge_documents d "
        "ON c.document_id=d.document_id AND c.document_version=d.document_version "
        "WHERE d.embedding_profile=%s AND (%s::text IS NULL OR d.domain=%s) "
    )
    tie = "c.document_id,c.document_version,c.chunk_id,c.content_hash"
    async with pool.connection() as conn, conn.transaction():
        await conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        await conn.execute("SET LOCAL statement_timeout = '5s'")
        if route == "B":
            await check_sparse_ready(conn)
        async with conn.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                "SELECT EXISTS(SELECT 1 FROM knowledge_documents WHERE embedding_profile<>%s)",
                (profile,),
            )
            if (await cursor.fetchone())["exists"]:
                raise KnowledgeError("embedding_profile_mismatch")
            if route == "A":
                vector = validate_vectors([vector], 1)[0]
                await cursor.execute(
                    "SELECT "
                    + fields
                    + "1-(c.embedding <=> %s::vector) AS retrieval_score"
                    + source
                    + "ORDER BY c.embedding <=> %s::vector,"
                    + tie
                    + " LIMIT 10",
                    (str(vector), profile, None, None, str(vector)),
                )
            else:
                assert route == "B"
                await cursor.execute(
                    "SELECT "
                    + fields
                    + "c.search_text <@> to_bm25query(%s,%s) AS retrieval_score"
                    + source
                    + "AND c.search_text <@> to_bm25query(%s,%s) < 0 "
                    + "ORDER BY retrieval_score,"
                    + tie
                    + " LIMIT 10",
                    (
                        query,
                        "public." + INDEX_NAME,
                        profile,
                        None,
                        None,
                        query,
                        "public." + INDEX_NAME,
                    ),
                )
            rows = await cursor.fetchall()
    return tuple(EvidenceChunk(evidence_id=digest(row["chunk_id"]), **row) for row in rows)


async def measure_abc(group, question, pool, repo, embeddings, profile):
    """Return Top 10 and complete budgeted Top 5; caller times this entire path."""
    query = question["text"]
    if not query.strip() or token_count(query) > 512:
        raise ValueError("invalid query")
    if group == "B":
        candidates = await single_route(pool, "B", query, profile)
    else:
        vector = await embeddings.aembed_query(query)
        if group == "A":
            candidates = await single_route(pool, "A", query, profile, vector)
        else:
            assert group == "C"
            _, dense, sparse = await repo.hybrid_candidates(vector, query, profile, None)
            candidates = tuple(c.evidence for c in fuse(dense, sparse))
    rows = [candidate.model_dump() for candidate in candidates]
    selected = pack(rows)
    if candidates and not selected:
        raise KnowledgeError("retrieval_context_budget_exceeded")
    # Materialize the exact complete evidence payload before the timer stops.
    context = canonical(selected)
    return rows, selected, token_count(context), len(context.encode("utf-8"))


async def corpus_rows(pool):
    async with pool.connection() as conn, conn.transaction():
        await conn.execute("SET TRANSACTION READ ONLY")
        cursor = await conn.execute(
            "SELECT d.document_id,d.document_version,d.content_hash,d.domain,d.source_title,"
            "d.public_source_key,d.embedding_profile,c.chunk_id,c.content_hash,c.content,"
            "c.section,c.line_start,c.line_end FROM knowledge_documents d JOIN knowledge_chunks c "
            "USING(document_id,document_version) ORDER BY d.document_id,c.ordinal"
        )
        return await cursor.fetchall()


def expected_corpus(fixture):
    documents = [
        prepare_document(root, entry, fixture["profile"])
        for root, manifest in (
            (Path("data/knowledge"), Path("data/knowledge/manifest.json")),
            (ROOT, ROOT / "manifest.json"),
        )
        for entry in read_manifest(root, manifest)
    ]
    return {
        (
            doc.entry.document_id,
            doc.document_version,
            doc.content_hash,
            doc.entry.domain,
            doc.entry.source_title,
            doc.entry.public_source_key,
            doc.embedding_profile,
            c.chunk_id,
            c.content_hash,
            c.content,
            c.section,
            c.line_start,
            c.line_end,
        )
        for doc in documents
        for c in doc.chunks
    }


async def abc_sparse_preflight():
    """Read-only SQL preflight on the currently restored six-document corpus."""
    fixture = load_frozen()
    settings = guarded_settings()
    pool = await open_pool(settings)
    try:
        rows = await single_route(pool, "B", fixture["questions"][2]["text"], fixture["profile"])
        assert rows and any(row.document_id == "demo-refund-entry" for row in rows)
    finally:
        await pool.close()


async def abc_latency():
    """Isolated, independent actual A/B/C entry-to-complete-Evidence timing."""
    import asyncio

    output = OUT / "abc-end-to-end-rerun.json"
    if output.exists():
        raise FileExistsError("Preserve the existing latency receipt")
    fixture = load_frozen()
    assert sha(OUT / "fixture.json") == (
        "404b70e8732b6c7be1eedeae97055c1763643daf12a382853d21794b4665d2df"
    )
    assert sha(OUT / "qwen.json") == (
        "7c0dfdbf0f35c2cea91f4d4bd1f2450e5d882245d16286430bf6c135fc4fdf06"
    )
    original = json.loads((OUT / "qwen.json").read_text(encoding="utf-8"))
    assert original["fixture_sha256"] == sha(OUT / "fixture.json")
    baseline = {row["id"]: row for row in original["results"] if row["round"] == 1}
    assert len(baseline) == 24 and not any(row["error"] for row in baseline.values())
    expected = expected_corpus(fixture)
    assert len(expected) == len(fixture["chunks"]) == 18
    settings = guarded_settings()
    pool = await open_pool(settings)
    embeddings = create_embeddings(settings)
    repo = KnowledgeRepository(pool)
    missing_ids = []
    initial = []
    attempts = []
    cold = None
    corpus_ok = False
    measurement_complete = False
    ingestion = None
    known = {
        (c["document_id"], c["document_version"], c["chunk_id"], c["content_hash"])
        for c in fixture["chunks"]
    }
    try:
        initial = await corpus_rows(pool)
        assert set(initial) <= expected and len(initial) == len(set(initial))
        before_ids = {row[0] for row in initial}
        async with pool.connection() as conn, conn.transaction():
            await conn.execute("SET TRANSACTION READ ONLY")
            cursor = await conn.execute("SELECT document_id FROM knowledge_documents")
            document_ids = {row[0] for row in await cursor.fetchall()}
        # Reject incomplete or unexpected documents rather than replacing any of them.
        assert document_ids == before_ids
        missing_ids = sorted({row[0] for row in expected} - before_ids)
        assert all(doc_id.startswith("task132-distractor-") for doc_id in missing_ids)
        start = time.perf_counter()
        await embeddings.initialize()
        cold = time.perf_counter() - start
        assert embeddings.profile.key == fixture["profile"]
        if missing_ids:
            ingestion = await KnowledgeIngestor(
                repo, embeddings, embeddings.profile.key, settings.embedding_batch_size
            ).ingest(ROOT, ROOT / "manifest.json")
            assert set(ingestion["published"]) == set(missing_ids)
        assert set(await corpus_rows(pool)) == expected
        assert fixture["permission"] == "knowledge:read" and fixture["domain"] is None
        # Fixed execution order: Q01-Q24, A then B then C; warm each route once.
        for group in "ABC":
            await measure_abc(
                group, fixture["questions"][0], pool, repo, embeddings, embeddings.profile.key
            )
        for round_no in range(int(os.environ.get("TASK132_ROUNDS", "5"))):
            for question in fixture["questions"]:
                for group in "ABC":
                    start = time.perf_counter()
                    item = {"round": round_no + 1, "id": question["id"], "group": group}
                    try:
                        async with asyncio.timeout(30):
                            rows, selected, tokens, size = await measure_abc(
                                group, question, pool, repo, embeddings, embeddings.profile.key
                            )
                        elapsed = (time.perf_counter() - start) * 1000
                        actual = [
                            (
                                r["document_id"],
                                r["document_version"],
                                r["chunk_id"],
                                r["content_hash"],
                            )
                            for r in rows
                        ]
                        reference = [
                            (
                                r["document_id"],
                                r["document_version"],
                                r["chunk_id"],
                                r["content_hash"],
                            )
                            for r in baseline[question["id"]][group]
                        ]
                        if not set(actual) <= known or len(actual) != len(set(actual)):
                            raise KnowledgeError("fixture_identity_drift")
                        item.update(
                            error=None,
                            ranked=actual,
                            scores=[r["retrieval_score"] for r in rows],
                            reference_scores=[
                                r["retrieval_score"] for r in baseline[question["id"]][group]
                            ],
                            rank_drift=actual != reference,
                            evidence_ids=[r["chunk_id"] for r in selected],
                            context_tokens=tokens,
                            context_bytes=size,
                            elapsed_ms=elapsed,
                        )
                    except Exception as exc:
                        item.update(
                            error=safe_error(exc), elapsed_ms=(time.perf_counter() - start) * 1000
                        )
                    attempts.append(item)
        measurement_complete = True
    finally:
        try:
            await embeddings.aclose()
            if measurement_complete:
                # The main agent owns the next business check on this exact corpus.
                corpus_ok = set(await corpus_rows(pool)) == expected
            else:
                for document_id in missing_ids:
                    await repo.remove(document_id)
                corpus_ok = (await corpus_rows(pool)) == initial
        finally:
            await pool.close()
        if attempts:
            summaries = {}
            for group in "ABC":
                group_attempts = [x for x in attempts if x["group"] == group]
                successful = [
                    x["elapsed_ms"]
                    for x in group_attempts
                    if not x["error"] and int(x["id"][1:]) <= 20
                ]
                summaries[group] = {
                    "attempts": len(group_attempts),
                    "failures": sum(bool(x["error"]) for x in group_attempts),
                    "rank_drift_attempts": sum(bool(x.get("rank_drift")) for x in group_attempts),
                    "answered_success_samples": len(successful),
                    "p50_ms": percentile(successful, 0.5),
                    "p95_ms": percentile(successful, 0.95),
                }
            dump(
                output,
                {
                    "fixture_sha256": sha(OUT / "fixture.json"),
                    "baseline_sha256": sha(OUT / "qwen.json"),
                    "order": "round, Q01..Q24, A then B then C",
                    "qwen_cold_seconds": cold,
                    "ingestion": ingestion,
                    "fixture_retained_for_main": measurement_complete and corpus_ok,
                    "corpus_verified": corpus_ok,
                    "fixture_document_count": len({row[0] for row in expected})
                    if measurement_complete and corpus_ok
                    else None,
                    "distractor_document_count": 12 if measurement_complete and corpus_ok else None,
                    "summaries": summaries,
                    "attempts": attempts,
                },
            )
    if not corpus_ok or not measurement_complete or any(item["error"] for item in attempts):
        raise AssertionError("ABC timing failure, identity drift, or corpus mismatch")


def audit_cleanup():
    """Verify original isolated fixture chunks after exact distractor removal."""
    fixture = load_frozen()
    settings = guarded_settings()
    with psycopg.connect(
        settings.database_url.get_secret_value(), options="-c default_transaction_read_only=on"
    ) as conn:
        rows = conn.execute(
            "SELECT d.document_id,d.document_version,c.chunk_id,c.content_hash,c.content,"
            "c.line_start,c.line_end FROM knowledge_documents d JOIN knowledge_chunks c "
            "USING(document_id,document_version) ORDER BY d.document_id,c.ordinal"
        ).fetchall()
        watermark = conn.execute(
            "SELECT watermark FROM knowledge_index_state WHERE singleton"
        ).fetchone()[0]
    expected = {
        (
            c["document_id"],
            c["document_version"],
            c["chunk_id"],
            c["content_hash"],
            c["content"],
            c["line_start"],
            c["line_end"],
        )
        for c in fixture["chunks"]
        if c["document_id"].startswith("demo-")
    }
    assert set(rows) == expected and len(rows) == len(expected)
    dump(
        OUT / "cleanup.json",
        {
            "fixture_sha256": sha(OUT / "fixture.json"),
            "original_chunks_verified": len(rows),
            "distractor_documents_remaining": 0,
            "watermark_after_cleanup": watermark,
        },
    )


async def end_to_end():
    """Measure actual Hybrid entry through complete Evidence, including real inference."""
    from app.knowledge.models import SearchQuery
    from app.knowledge.retriever import HybridRetriever
    from app.runtime.context import DemoIdentity

    fixture = load_frozen()
    settings = guarded_settings()
    pool = await open_pool(settings)
    embeddings = create_embeddings(settings)
    reranker = BGEReranker(settings)
    try:
        start = time.perf_counter()
        await embeddings.initialize()
        qwen_cold = time.perf_counter() - start
        start = time.perf_counter()
        await reranker.initialize()
        bge_cold = time.perf_counter() - start
        assert embeddings.profile.key == fixture["profile"]
        retriever = HybridRetriever(
            KnowledgeRepository(pool), embeddings, reranker, embeddings.profile.key, timeout=30
        )
        identity = DemoIdentity(user_id="dev-user", permission_scopes=frozenset({"knowledge:read"}))
        await retriever.search(
            SearchQuery(query=fixture["questions"][0]["text"], top_k=5), identity=identity
        )
        attempts = []
        for round_no in range(int(os.environ.get("TASK132_ROUNDS", "5"))):
            for question in fixture["questions"]:
                start = time.perf_counter()
                try:
                    result = await retriever.search(
                        SearchQuery(query=question["text"], top_k=5), identity=identity
                    )
                    attempt = {
                        "error": None,
                        "evidence_ids": [e.chunk_id for e in result.evidence],
                        "candidate_count": result.candidate_count,
                    }
                except Exception as exc:
                    attempt = {"error": safe_error(exc)}
                attempt.update(
                    round=round_no + 1,
                    id=question["id"],
                    elapsed_ms=(time.perf_counter() - start) * 1000,
                )
                attempts.append(attempt)
        succeeded = [a["elapsed_ms"] for a in attempts if not a["error"] and int(a["id"][1:]) <= 20]
        dump(
            OUT / "hybrid-end-to-end.json",
            {
                "fixture_sha256": sha(OUT / "fixture.json"),
                "qwen_cold_seconds": qwen_cold,
                "bge_cold_seconds": bge_cold,
                "memory_after_run": memory_snapshot(),
                "attempts": attempts,
                "success_p50_ms": percentile(succeeded, 0.5),
                "success_p95_ms": percentile(succeeded, 0.95),
            },
        )
    finally:
        await reranker.aclose()
        await embeddings.aclose()
        await pool.close()


async def cleanup():
    fixture = load_frozen()
    settings = guarded_settings()
    pool = await open_pool(settings)
    try:
        repo = KnowledgeRepository(pool)
        ids = sorted(
            {
                c["document_id"]
                for c in fixture["chunks"]
                if c["document_id"].startswith("task132-distractor-")
            }
        )
        assert ids == [f"task132-distractor-{i:02}" for i in range(1, 13)]
        for document_id in ids:
            await repo.remove(document_id)
        async with pool.connection() as conn:
            remaining = await (
                await conn.execute(
                    "SELECT count(*) FROM knowledge_documents WHERE document_id = ANY(%s)", (ids,)
                )
            ).fetchone()
            assert remaining == (0,)
        print("CLEANUP exact fixture IDs:", len(ids), "remaining:", remaining[0])
    finally:
        await pool.close()


def test_task132():
    phase = os.environ["TASK132_PHASE"]
    if phase == "freeze":
        freeze()
    elif phase == "qwen":
        run_async(qwen())
    elif phase == "bge":
        run_async(bge())
    elif phase == "report":
        report()
    elif phase == "cleanup":
        run_async(cleanup())
    elif phase == "audit_cleanup":
        audit_cleanup()
    elif phase == "abc_latency":
        run_async(abc_latency())
    elif phase == "abc_sparse_preflight":
        run_async(abc_sparse_preflight())
    elif phase == "end_to_end":
        run_async(end_to_end())
    else:
        raise ValueError(phase)


def percentile(values, p):
    return sorted(values)[math.ceil(p * len(values)) - 1] if values else None


def pack(rows):
    selected = []
    for row in rows:
        if len(selected) >= 5:
            break
        encoded = canonical([*selected, row])
        if token_count(encoded) <= 2400 and len(encoded.encode("utf-8")) <= 24 * 1024:
            selected.append(row)
    return selected


def report():
    fixture = load_frozen()
    a = json.loads((OUT / "qwen.json").read_text(encoding="utf-8"))
    d = json.loads((OUT / "bge.json").read_text(encoding="utf-8"))
    assert a["fixture_sha256"] == d["fixture_sha256"] == sha(OUT / "fixture.json")
    assert d["qwen_sha256"] == sha(OUT / "qwen.json")
    by_d = {(x["round"], x["id"]): x for x in d["results"]}
    evaluated = []
    for x in a["results"]:
        y = by_d[(x["round"], x["id"])]
        if not x["error"] and not y["error"]:
            assert {e["chunk_id"] for e in x["C"]} == {e["chunk_id"] for e in y["D"]}
        evaluated.append(dict(source=x, bge=y))
    first = {x["source"]["id"]: x for x in evaluated if x["source"]["round"] == 1}
    groups = {}
    details = {}
    for q in fixture["questions"]:
        qid = q["id"]
        marks = fixture["qrels"][qid]
        item = first[qid]
        relevant = {k for k, v in marks.items() if v >= 2}
        details[qid] = {}
        for group in "ABCD":
            src = item["bge"] if group == "D" else item["source"]
            rows = src.get(group, []) if not src["error"] else []
            ids = [r["chunk_id"] for r in rows]
            assert set(ids) <= set(marks)
            ranked = [marks[x] for x in ids]
            row = {
                "ranked_chunk_ids": ids,
                "grades": ranked,
                "error": src["error"],
                "evidence_top5_ids": [r["chunk_id"] for r in pack(rows)],
                "first_relevant_rank": next((i for i, v in enumerate(ranked, 1) if v >= 2), None),
            }
            if relevant:
                row["evidence_recall_top5"] = len(
                    relevant.intersection(row["evidence_top5_ids"])
                ) / len(relevant)
                for k in (3, 5, 10):
                    hits = sum(v >= 2 for v in ranked[:k])
                    rr = next((1 / i for i, v in enumerate(ranked[:k], 1) if v >= 2), 0)
                    dcg = sum((2**v - 1) / math.log2(i + 1) for i, v in enumerate(ranked[:k], 1))
                    ideal = sorted(marks.values(), reverse=True)[:k]
                    idcg = sum((2**v - 1) / math.log2(i + 1) for i, v in enumerate(ideal, 1))
                    row[str(k)] = {"recall": hits / len(relevant), "mrr": rr, "ndcg": dcg / idcg}
            details[qid][group] = row
    for group in "ABCD":
        subset = [details[f"Q{i:02}"][group] for i in range(1, 21)]
        groups[group] = {
            str(k): {
                metric: sum(x[str(k)][metric] for x in subset) / 20
                for metric in ("recall", "mrr", "ndcg")
            }
            for k in (3, 5, 10)
        }
        successful = [x for x in subset if not x["error"]]
        groups[group]["success_subset"] = {
            str(k): {
                metric: sum(x[str(k)][metric] for x in successful) / len(successful)
                if successful
                else None
                for metric in ("recall", "mrr", "ndcg")
            }
            for k in (3, 5, 10)
        }
        groups[group]["evidence_recall_top5"] = sum(x["evidence_recall_top5"] for x in subset) / 20
        groups[group]["errors"] = [
            f"Q{i:02}" for i in range(1, 21) if details[f"Q{i:02}"][group]["error"]
        ]
    timings = {}
    for name, field, part in [
        ("embedding", "embedding_ms", "source"),
        ("database_both_routes", "database_ms", "source"),
        ("bge", "bge_ms", "bge"),
    ]:
        values = [
            v[part][field]
            for v in evaluated
            if int(v["source"]["id"][1:]) <= 20 and not v[part]["error"] and field in v[part]
        ]
        timings[name] = {
            "count": len(values),
            "p50_ms": percentile(values, 0.50),
            "p95_ms": percentile(values, 0.95),
        }
    dump(
        OUT / "metrics.json",
        dict(
            fixture_sha256=sha(OUT / "fixture.json"),
            qwen_sha256=sha(OUT / "qwen.json"),
            bge_sha256=sha(OUT / "bge.json"),
            groups=groups,
            questions=details,
            timings=timings,
            attempts=len(evaluated),
            source_failures=sum(bool(v["source"]["error"]) for v in evaluated),
            rerank_failures=sum(bool(v["bge"]["error"]) for v in evaluated),
            no_answer_note=(
                "Retrieval-only experiment: evidence insufficiency, wrong answers "
                "and fabricated citations are not measured."
            ),
            timing_note=(
                "Sequential stages; database measures both routes together. "
                "Not end-to-end group latency."
            ),
        ),
    )
    print(json.dumps(groups, ensure_ascii=False, indent=2), flush=True)
