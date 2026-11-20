"""Run frozen synthetic fixtures through real maintenance, LangMem, PG and archive."""

import hashlib
import json
import os
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

import psycopg
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.messages.utils import count_tokens_approximately
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg_pool import AsyncConnectionPool

from app.context.archive_store import ArchiveStore
from app.context.compaction import SUMMARY_PROMPT_VERSION
from app.context.manager import ContextManager
from app.context.models import PublicInteraction, PublicMessage, SessionIdentity
from app.context.repository import ContextRepository
from app.core.config import Settings
from app.infrastructure.model import model_resources
from scripts import run_async

ROOT = Path("docs/v2/v2-02/evidence")
OUTPUT = ROOT / (
    "v2-02-task232-quality-r6-raw.jsonl"
    if "--quality-r6" in sys.argv
    else "v2-02-task232-quality-r5-raw.jsonl"
    if "--quality-r5" in sys.argv
    else "v2-02-task232-quality-r4-raw.jsonl"
    if "--quality-r4" in sys.argv
    else "v2-02-task232-quality-r3-raw.jsonl"
    if "--quality-r3" in sys.argv
    else "v2-02-task232-quality-r2-raw.jsonl"
    if "--quality-only" in sys.argv
    else "v2-02-task232-quality-raw.jsonl"
)


def emit(result):
    with OUTPUT.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")


async def main():
    assert not OUTPUT.exists(), "Use a fresh evidence path"
    fixtures = []
    for filename, expected in (
        (
            "summary-quality-fixtures.json",
            "3ee9cca13f1fea4c982aa9452e1f2c80922b347870c19222432a8a6c3b48d0dd",
        ),
        (
            "context-resource-fixture.json",
            "24ac79e8e06cd7f1021b4acbd40e0669ddf96e637f28d69de9e7f67ead7c3ee3",
        ),
    ):
        raw = (ROOT / filename).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == expected
        fixtures.append(json.loads(raw))
    cases = [(case["id"], case["messages"]) for case in fixtures[0]["cases"]]
    resource = []
    for i, item in enumerate(fixtures[1]["interactions"]):
        resource.extend(
            [
                {"id": f"resource-{i}-u", "role": "user", "content": item["user"]},
                {"id": f"resource-{i}-a", "role": "assistant", "content": item["assistant"]},
            ]
        )
    if not any(
        flag in sys.argv
        for flag in (
            "--quality-only",
            "--quality-r3",
            "--quality-r4",
            "--quality-r5",
            "--quality-r6",
        )
    ):
        cases.append(("resource", resource))
    dsn = os.environ["CONTEXT_ARCHIVE_TEST_DSN"]
    parts = conninfo_to_dict(dsn)
    assert (parts.get("host"), parts.get("port")) == ("127.0.0.1", "56422")
    schema = "ctx232_" + uuid4().hex
    async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as admin:
        row = await (
            await admin.execute(
                "SELECT current_database(),current_user,current_setting('server_version_num'),"
                "shobj_description(oid,'pg_database') FROM pg_database "
                "WHERE datname=current_database()"
            )
        ).fetchone()
        assert row == ("agent_context_test", "agent_test", "170012", "codex-v202-local-20261119")
        await admin.execute(sql.SQL("CREATE SCHEMA {} ").format(sql.Identifier(schema)))
        try:
            await admin.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            for migration in ("008_context_archive.sql", "009_context_compaction.sql"):
                await admin.execute(Path("migrations", migration).read_text(encoding="utf-8"))
            pool = AsyncConnectionPool(
                dsn, kwargs={"options": f"-csearch_path={schema}"}, open=False
            )
            with tempfile.TemporaryDirectory(prefix="ctx232_") as directory:
                async with pool:
                    manager = ContextManager(ContextRepository(pool), ArchiveStore(Path(directory)))
                    settings = Settings(
                        context_model_window_tokens=65536, context_model_output_tokens=1024
                    )
                    assert settings.model_configured
                    async with model_resources(settings) as (_, gateway):
                        for case_id, messages in cases:
                            identity = SessionIdentity(
                                user_id="quality-" + case_id, conversation_id="fixture"
                            )
                            items = tuple(
                                PublicMessage(
                                    message_id=m["id"],
                                    role=m["role"],
                                    content=m["content"],
                                    task_id="fixture",
                                )
                                for m in messages
                            )
                            interaction = PublicInteraction(
                                task_id="fixture", task_status="COMPLETED", messages=items
                            )
                            archive = await manager.publish(
                                identity,
                                "fixture-cp",
                                [interaction],
                                retain_recent=0,
                                max_messages=len(items),
                                session_status="COMPLETED",
                            )
                            before = count_tokens_approximately(
                                [
                                    (HumanMessage if m["role"] == "user" else AIMessage)(
                                        content=m["content"]
                                    )
                                    for m in messages
                                ]
                            )
                            started = time.monotonic()
                            record = {
                                "case": case_id,
                                "model": settings.model_name,
                                "prompt_version": SUMMARY_PROMPT_VERSION,
                                "archive_ref": archive.archive_ref,
                                "archive_bytes": manager.store._path(archive.relative_path)
                                .stat()
                                .st_size,
                                "input_estimated_tokens": before,
                                "message_ids": [m["id"] for m in messages],
                            }
                            try:
                                summary, reports = await manager.compact(
                                    identity,
                                    archive_refs=(archive.archive_ref,),
                                    parent_summary_id=None,
                                    source_checkpoint_id="fixture-cp",
                                    version=1,
                                    policy_version="fixture-v1",
                                    model_version=settings.model_name,
                                    prompt_version=SUMMARY_PROMPT_VERSION,
                                    max_bytes=1000000,
                                    gateway=gateway,
                                    token_counter=count_tokens_approximately,
                                    max_input_tokens=64512,
                                    max_output_tokens=1024,
                                    settings=settings,
                                    maintenance={
                                        "maintenance_id": "maintenance-" + case_id,
                                        "source_task_id": "fixture",
                                        "source_run_id": "source-run",
                                        "budget_version": "fixture-v1",
                                    },
                                )
                                record.update(
                                    status="ok",
                                    summary=summary.text,
                                    covered_ids=summary.message_ids,
                                    usage=[asdict(report) for report in reports],
                                    summary_estimated_tokens=count_tokens_approximately(
                                        [HumanMessage(content=summary.text)]
                                    ),
                                )
                            except Exception as error:
                                record.update(status="error", error_type=type(error).__name__)
                            record["elapsed_seconds"] = time.monotonic() - started
                            emit(record)
        finally:
            await admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
            assert (
                await (
                    await admin.execute(
                        "SELECT count(*) FROM pg_namespace WHERE nspname=%s", (schema,)
                    )
                ).fetchone()
            ) == (0,)
            emit({"cleanup": "schema dropped", "schema": schema})


if __name__ == "__main__":
    run_async(main())
