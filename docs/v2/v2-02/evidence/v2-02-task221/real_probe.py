"""Single synthetic model probe in a guarded, disposable local schema."""

import json
import os
import tempfile
from pathlib import Path
from uuid import uuid4

import psycopg
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


async def main():
    dsn = os.environ["CONTEXT_ARCHIVE_TEST_DSN"]
    parts = conninfo_to_dict(dsn)
    assert parts.get("host") == "127.0.0.1" and parts.get("port") == "56422"
    schema = "ctx221_" + uuid4().hex
    receipt = {"schema_cleaned": False}
    async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as admin:
        row = await (
            await admin.execute(
                "SELECT current_database(),current_user,current_setting('server_version_num'),"
                "shobj_description(oid,'pg_database') FROM pg_database "
                "WHERE datname=current_database()"
            )
        ).fetchone()
        assert row == ("agent_context_test", "agent_test", "170012", "codex-v202-local-20261119")
        await admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            await admin.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            for migration in ("008_context_archive.sql", "009_context_compaction.sql"):
                await admin.execute(Path("migrations", migration).read_text(encoding="utf-8"))
            pool = AsyncConnectionPool(
                dsn,
                kwargs={"options": f"-csearch_path={schema}"},
                open=False,
                min_size=1,
                max_size=2,
            )
            with tempfile.TemporaryDirectory(prefix="ctx221_") as directory:
                async with pool:
                    repo = ContextRepository(pool)
                    manager = ContextManager(repo, ArchiveStore(Path(directory)))
                    identity = SessionIdentity(
                        user_id="synthetic-user", conversation_id="synthetic-session"
                    )
                    item = PublicInteraction(
                        task_id="synthetic-task",
                        task_status="COMPLETED",
                        messages=(
                            PublicMessage(
                                message_id="u",
                                role="user",
                                content="Please answer briefly.",
                                task_id="synthetic-task",
                            ),
                            PublicMessage(
                                message_id="a",
                                role="assistant",
                                content="Understood.",
                                task_id="synthetic-task",
                            ),
                        ),
                    )
                    archive = await manager.publish(
                        identity,
                        "synthetic-cp",
                        [item],
                        retain_recent=0,
                        max_messages=2,
                        session_status="COMPLETED",
                    )
                    settings = Settings(
                        context_model_window_tokens=4224, context_model_output_tokens=128
                    )
                    assert settings.model_configured
                    async with model_resources(settings) as (_, gateway):
                        summary, reports = await manager.compact(
                            identity,
                            archive_refs=(archive.archive_ref,),
                            parent_summary_id=None,
                            source_checkpoint_id="synthetic-cp",
                            version=1,
                            policy_version="synthetic-v1",
                            model_version=settings.model_name,
                            prompt_version=SUMMARY_PROMPT_VERSION,
                            max_bytes=10000,
                            gateway=gateway,
                            token_counter=count_tokens_approximately,
                            max_input_tokens=4096,
                            max_output_tokens=128,
                            settings=settings,
                            maintenance={
                                "maintenance_id": "synthetic-maintenance",
                                "source_task_id": "synthetic-task",
                                "source_run_id": "synthetic-run",
                                "budget_version": "v1",
                            },
                        )
                    work = await repo.maintenance("synthetic-maintenance")
                    actual, usage = await repo.maintenance_usage("synthetic-maintenance")
                    assert summary.message_ids == ("u", "a") and work["status"] == "SUCCEEDED"
                    assert work["reserved_attempts"] == actual == 1 and len(reports) == 1
                    recovered = await manager.recover(
                        identity,
                        summary_id=summary.summary_id,
                        candidate_limit=1,
                        max_bytes=10000,
                        max_tokens=1000,
                        token_counter=lambda x: len(x),
                    )
                    assert recovered == item.messages
                    receipt.update(
                        status="ok",
                        prompt_version=SUMMARY_PROMPT_VERSION,
                        input_limit_for_probe=4096,
                        output_limit_for_probe=128,
                        attempts=actual,
                        usage_status=usage.status,
                        input_tokens=usage.input_tokens,
                        output_tokens=usage.output_tokens,
                        covered_messages=len(summary.message_ids),
                        archive_status=archive.status,
                        maintenance_status=work["status"],
                    )
        finally:
            await admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
            receipt["schema_cleaned"] = (
                await (
                    await admin.execute(
                        "SELECT count(*) FROM pg_namespace WHERE nspname=%s", (schema,)
                    )
                ).fetchone()
            ) == (0,)
            assert receipt["schema_cleaned"]
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    run_async(main())
