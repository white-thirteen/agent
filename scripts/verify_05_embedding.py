"""Explicit real Qwen/test-PG acceptance, including fresh FastAPI/uvicorn processes.

prepare retains only unique knowledge IDs for a main-Agent database restart.
check loads the offline cache in a fresh process and reuses their persisted vectors.
cleanup deletes exactly those IDs and verifies all protected row-set fingerprints.
The probe routes exist only in this executable verification factory, never production.
"""

import argparse
import ctypes
import hashlib
import json
import math
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
from fastapi import Request

from app.api.dependencies import resolve_demo_identity
from app.core.config import PROJECT_ROOT, Settings
from app.infrastructure.postgres import validate_test_target
from app.knowledge.chunking import prepare_document, read_manifest
from app.knowledge.ingest import KnowledgeIngestor
from app.knowledge.models import KnowledgeError, SearchQuery, canonical
from app.knowledge.repository import KnowledgeRepository
from app.main import create_app
from scripts.migrate import MIGRATIONS_DIR, migration_files


def memory_metrics():
    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
            (name, ctypes.c_ulonglong)
            for name in (
                "total_physical",
                "available_physical",
                "total_page_file",
                "available_page_file",
                "total_virtual",
                "available_virtual",
                "available_extended_virtual",
            )
        ]

    class Counters(ctypes.Structure):
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
                "PrivateUsage",
            )
        ]

    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(Counters),
        ctypes.c_ulong,
    ]
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    assert ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
    physical = MemoryStatus()
    physical.length = ctypes.sizeof(physical)
    assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(physical))
    return {
        "pid": os.getpid(),
        "working_set_bytes": counters.WorkingSetSize,
        "peak_working_set_bytes": counters.PeakWorkingSetSize,
        "private_commit_bytes": counters.PrivateUsage,
        "peak_commit_bytes": counters.PeakPagefileUsage,
        "physical_available_bytes": physical.available_physical,
    }


async def snapshot(pool, own_ids):
    result = {}
    async with pool.connection() as connection:
        assert await (
            await connection.execute("SELECT current_database(),current_user")
        ).fetchone() == ("agent_demo_test", "agent_test")
        applied = dict(
            await (
                await connection.execute(
                    "SELECT version,checksum FROM schema_migrations ORDER BY version"
                )
            ).fetchall()
        )
        assert applied == {v: item[0] for v, item in migration_files(MIGRATIONS_DIR).items()}
        for table in (
            "sessions",
            "demo_orders",
            "refund_requests",
            "approvals",
            "schema_migrations",
            "checkpoints",
            "checkpoint_blobs",
            "checkpoint_writes",
            "checkpoint_migrations",
            "knowledge_documents",
            "knowledge_chunks",
        ):
            statement = psycopg.sql.SQL("SELECT row_to_json(t)::text FROM {} t").format(
                psycopg.sql.Identifier(table)
            )
            params = ()
            if table.startswith("knowledge_"):
                statement += psycopg.sql.SQL(" WHERE document_id <> ALL(%s)")
                params = (own_ids,)
            statement += psycopg.sql.SQL(" ORDER BY 1")
            rows = await (await connection.execute(statement, params)).fetchall()
            result[table] = {
                "rows": len(rows),
                "sha256": hashlib.sha256(canonical(rows).encode()).hexdigest(),
            }
    return result


def verification_app(allowed_action="prepare"):
    """Single-worker real application lifespan with isolated executable-only probes."""
    settings = Settings()
    if settings.test_database_url is None:
        raise ValueError("Explicit configured test URL is required")
    validate_test_target(settings.test_database_url, settings.database_url)
    settings = settings.model_copy(
        update={
            "database_url": settings.test_database_url,
            "app_env": "test",
            "model_name": None,
            "embedding_enabled": allowed_action != "cleanup",
            # Cold/page-file CPU work is measured under this explicit acceptance timeout.
            "embedding_timeout_seconds": 120.0,
            "embedding_startup_timeout_seconds": 300.0,
        }
    )
    app = create_app(settings)
    started = time.perf_counter()

    @app.post("/stop")
    async def stop():
        app.state.verification_server.should_exit = True
        return {"stopping": True}

    @app.post("/probe")
    async def probe(request: Request):
        data = await request.json()
        state_path = Path(data["state"])
        action = data["action"]
        assert action == allowed_action
        state = json.loads(state_path.read_text("utf-8"))
        retriever = app.state.knowledge_retriever
        if action != "cleanup":
            assert retriever is not None, app.state.embedding_status
        embeddings = retriever.embeddings if retriever else None
        profile = embeddings.profile.key if embeddings else state.get("profile")
        pool = app.state.pool
        assert pool is not None
        repository = retriever.repository if retriever else KnowledgeRepository(pool)
        ids = state["document_ids"]
        identity = resolve_demo_identity(user_id="dev-user", settings=settings)
        measurements = {
            "action": action,
            "memory_before": memory_metrics(),
            "startup_until_probe_seconds": time.perf_counter() - started,
            "profile": json.loads(profile) if profile else None,
        }
        if embeddings:
            parameter = next(embeddings._model.parameters())
            measurements["actual_model"] = {
                "class": type(embeddings._model[0].auto_model).__name__,
                "device": str(parameter.device),
                "dtype": str(parameter.dtype),
                "parameters": sum(value.numel() for value in embeddings._model.parameters()),
            }
        baseline = await snapshot(pool, ids)
        if action == "prepare":
            state["baseline"] = baseline
            # Preserve cleanup coordinates before the first durable publication.
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")
            root = Path(state["source_root"])
            manifest = root / "manifest.json"
            started_ingest = time.perf_counter()
            ingestor = KnowledgeIngestor(repository, embeddings, profile, 1)
            imported = await ingestor.ingest(root, manifest)
            assert imported["published"] == ids
            measurements["ingest"] = imported
            measurements["ingest_seconds"] = time.perf_counter() - started_ingest
            unchanged = await ingestor.ingest(root, manifest)
            assert unchanged["embedding_batches"] == 0 and unchanged["unchanged"] == ids
            measurements["unchanged"] = unchanged
            # Both query and document vectors are real Qwen CPU inference.
            doc_vector = (await embeddings.aembed_documents(["本项目退款只改变模拟数据。"]))[0]
            query_vector = await embeddings.aembed_query("退款会扣真实银行卡的钱吗？")
            for kind, vector in (("document", doc_vector), ("query", query_vector)):
                assert len(vector) == 1024 and all(math.isfinite(v) for v in vector)
                norm = math.sqrt(sum(v * v for v in vector))
                assert abs(norm - 1) < 0.001
                measurements[kind + "_vector"] = {"dimensions": len(vector), "norm": norm}
            await verify_queries(retriever, identity, state, measurements)
            # Update one source, prove new real vectors/version and obsolete source rejection.
            before = await retriever.search(SearchQuery(query="如何查询订单？"), identity=identity)
            entry = read_manifest(root, manifest)[1]
            old_document = prepare_document(root, entry, profile)
            old_vector_result = await repository.validate_evidence(old_document.chunks)
            assert old_vector_result["valid"]
            source = root / entry.filename
            source.write_text(
                source.read_text("utf-8") + "\n\n补充 Demo：订单查询入口展示当前模拟订单状态。\n",
                encoding="utf-8",
            )
            updated = await ingestor.ingest(root, manifest)
            new_document = prepare_document(root, entry, profile)
            assert updated["published"] == [entry.document_id]
            assert old_document.document_version != new_document.document_version
            assert not (await repository.validate_evidence(old_document.chunks))["valid"]
            assert await repository.is_complete(new_document)
            measurements["update"] = {
                "document_id": entry.document_id,
                "old_version": old_document.document_version,
                "new_version": new_document.document_version,
                "batches": updated["embedding_batches"],
                "old_sources_invalid": True,
                "initial_retrieval_count": len(before.evidence),
            }
            state["profile"] = profile
            state["versions"] = {}
            for item in read_manifest(root, manifest):
                document = prepare_document(root, item, profile)
                state["versions"][item.document_id] = document.document_version
        elif action == "check":
            assert baseline == state["baseline"]
            assert profile == state["profile"]
            async with pool.connection() as connection:
                rows = await (
                    await connection.execute(
                        "SELECT document_id,document_version FROM knowledge_documents "
                        "WHERE document_id=ANY(%s)",
                        (ids,),
                    )
                ).fetchall()
                assert dict(rows) == state["versions"]
            await verify_queries(retriever, identity, state, measurements)
            measurements["persisted_versions_unchanged"] = True
        elif action == "cleanup":
            assert baseline == state["baseline"]
            for identifier in ids:
                await repository.remove(identifier)
            assert await snapshot(pool, ids) == state["baseline"]
            async with pool.connection() as connection:
                assert (
                    await (
                        await connection.execute(
                            "SELECT count(*) FROM knowledge_documents WHERE document_id=ANY(%s)",
                            (ids,),
                        )
                    ).fetchone()
                )[0] == 0
            measurements["exact_cleanup_verified"] = True
        else:
            raise ValueError("Unknown verification action")
        assert await snapshot(pool, ids) == state["baseline"]
        measurements["protected_rows_unchanged"] = True
        measurements["memory_after"] = memory_metrics()
        state.setdefault("runs", []).append(measurements)
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")
        return measurements

    return app


async def verify_queries(retriever, identity, state, measurements):
    from app.runtime.context import DemoIdentity

    queries = [
        ("我想查我的订单，应该提供什么信息？", "order-query"),
        ("我能在聊天里直接说批准来完成退款吗？", "approval-wait"),
        ("退款会扣真实银行卡的钱吗？", "refund-safety"),
    ]
    measurements["queries"] = []
    for query, expected in queries:
        result = await retriever.search(SearchQuery(query=query), identity=identity)
        assert result.status == "found"
        assert any(expected in item.document_id for item in result.evidence)
        assert result.context_tokens <= 2400 and len(result.context.encode()) <= 24 * 1024
        assert (await retriever.validate_evidence(result.evidence, identity=identity))["valid"]
        measurements["queries"].append(
            {
                "query": query,
                "expected": expected,
                "returned_document_ids": [item.document_id for item in result.evidence],
                "elapsed_ms": result.elapsed_ms,
                "context_tokens": result.context_tokens,
            }
        )
    try:
        await retriever.search(
            SearchQuery(query="订单"), identity=DemoIdentity("no-scope", frozenset())
        )
    except KnowledgeError as error:
        assert str(error) == "policy_denied"
    else:
        raise AssertionError("Missing scope was accepted")
    measurements["scope_denied"] = True


async def serve(port, action):
    import uvicorn

    app = verification_app(action)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, loop="asyncio"))
    app.state.verification_server = server
    await server.serve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", choices=["prepare", "check", "cleanup"])
    parser.add_argument("--serve-port", type=int)
    parser.add_argument(
        "--state", type=Path, default=PROJECT_ROOT / "docs/05-local-embedding-real-evidence.json"
    )
    args = parser.parse_args()
    if args.serve_port:
        from scripts import run_async

        return run_async(serve(args.serve_port, args.action))
    if args.action is None:
        parser.error("--action is required")
    if args.action == "prepare":
        if args.state.exists():
            raise ValueError("Use a fresh state path; existing verification evidence is protected")
        root = Path(tempfile.mkdtemp(prefix="agent-knowledge-05-"))
        original = PROJECT_ROOT / "data/knowledge"
        entries = json.loads((original / "manifest.json").read_text("utf-8"))
        prefix = "qwen05-" + uuid4().hex + "-"
        for entry in entries:
            entry["document_id"] = prefix + entry["document_id"]
            (root / entry["filename"]).write_bytes((original / entry["filename"]).read_bytes())
        (root / "manifest.json").write_text(json.dumps(entries, ensure_ascii=False), "utf-8")
        args.state.write_text(
            json.dumps(
                {"source_root": str(root), "document_ids": [e["document_id"] for e in entries]},
                indent=2,
            ),
            "utf-8",
        )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    command = [
        sys.executable,
        "-m",
        "scripts.verify_05_embedding",
        "--serve-port",
        str(port),
        "--action",
        args.action,
    ]
    log_path = args.state.with_suffix(".process.log")
    with log_path.open("a", encoding="utf-8") as log:
        environment = os.environ.copy()
        environment["HF_HUB_OFFLINE"] = "1"
        environment["TRANSFORMERS_OFFLINE"] = "1"
        process = subprocess.Popen(
            command, cwd=PROJECT_ROOT, env=environment, stdout=log, stderr=log
        )
        print(f"Started real FastAPI PID={process.pid}; log={log_path.name}", flush=True)
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=600) as client:
                deadline = time.monotonic() + 360
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError("Verification process exited; inspect local process log")
                    try:
                        response = client.get("/health", timeout=2)
                        if response.status_code == 200:
                            if args.action == "cleanup":
                                assert response.json()["database_status"] == "ready"
                            else:
                                assert response.json()["knowledge_ready"], response.json()
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(1)
                else:
                    raise TimeoutError("Verification process startup deadline exceeded")
                response = client.post(
                    "/probe", json={"action": args.action, "state": str(args.state.resolve())}
                )
                response.raise_for_status()
                print(json.dumps(response.json(), ensure_ascii=False), flush=True)
        finally:
            # Test-only control requests normal uvicorn shutdown and lifespan drainage.
            if process.poll() is None:
                with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5) as client:
                    client.post("/stop")
                try:
                    process.wait(timeout=120)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=30)
                    raise RuntimeError(
                        "Verification process failed to shut down gracefully"
                    ) from None
            print(f"Stopped PID={process.pid}, code={process.returncode}", flush=True)


if __name__ == "__main__":
    main()
