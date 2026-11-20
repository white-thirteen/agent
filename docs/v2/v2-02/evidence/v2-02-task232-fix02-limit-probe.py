"""One real provider call with redacted wire receipt and durable maintenance budget."""

import json
import os
import time
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
from langchain_core.messages import HumanMessage
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg_pool import AsyncConnectionPool

from app.context.manager import _ClaimBudget
from app.context.models import SessionIdentity
from app.context.repository import ContextRepository
from app.core.config import Settings
from app.infrastructure.model import DeepSeekChatOpenAI
from app.runtime.model_gateway import (
    MaintenanceCallContext,
    ModelCallLimits,
    ModelCallUsage,
    ModelGateway,
)
from scripts import run_async

OUTPUT = Path("docs/v2/v2-02/evidence/v2-02-task232-fix02-limit.json")


async def main():
    assert not OUTPUT.exists()
    settings = Settings()
    assert settings.model_configured
    dsn = os.environ["CONTEXT_ARCHIVE_TEST_DSN"]
    parts = conninfo_to_dict(dsn)
    assert (parts.get("host"), parts.get("port")) == ("127.0.0.1", "56422")
    schema = "ctx232_" + uuid4().hex
    receipt = {"request": None, "response": None, "schema_cleaned": False}

    async def on_request(request):
        body = json.loads(request.content)
        receipt["request"] = {
            key: body.get(key)
            for key in ("model", "max_tokens", "max_completion_tokens", "reasoning_effort")
        }

    async def on_response(response):
        body = json.loads(await response.aread())
        receipt["response"] = {
            "model": body.get("model"),
            "usage": body.get("usage"),
            "finish_reason": body.get("choices", [{}])[0].get("finish_reason"),
        }

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
            async with AsyncConnectionPool(
                dsn, kwargs={"options": f"-csearch_path={schema}"}
            ) as pool:
                repo = ContextRepository(pool)
                await repo.register_maintenance(
                    SessionIdentity(user_id="synthetic-limit", conversation_id="fixture"),
                    maintenance_id="limit",
                    source_task_id="synthetic",
                    source_run_id="synthetic",
                    source_checkpoint_id="synthetic",
                    message_ids=("one",),
                    content_hash="fixture",
                    policy_version="fixture",
                    budget_version="fixture",
                    max_input_tokens=1024,
                    max_output_tokens=8,
                    archive_refs=("fixture",),
                )
                claim = await repo.claim_maintenance("limit")
                async with httpx.AsyncClient(
                    event_hooks={"request": [on_request], "response": [on_response]}
                ) as client:
                    model = DeepSeekChatOpenAI(
                        model=settings.model_name,
                        api_key=settings.model_api_key.get_secret_value(),
                        base_url=settings.model_base_url,
                        reasoning_effort="none",
                        max_retries=0,
                        http_async_client=client,
                    )
                    gateway = ModelGateway(model, ModelCallLimits(8, 25, 0))
                    result = await gateway.invoke(
                        [
                            HumanMessage(
                                content="Write a detailed numbered list of one hundred animals."
                            )
                        ],
                        context=MaintenanceCallContext(
                            "limit", _ClaimBudget(repo, claim), time.monotonic() + 25, 8
                        ),
                        model_usage=ModelCallUsage(),
                    )
                    receipt["gateway_attempts"] = result.model_usage.model_attempts
                    receipt["persisted_reserved"] = (await repo.maintenance("limit"))[
                        "reserved_attempts"
                    ]
        finally:
            await admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
            receipt["schema_cleaned"] = (
                await (
                    await admin.execute(
                        "SELECT count(*) FROM pg_namespace WHERE nspname=%s", (schema,)
                    )
                ).fetchone()
            ) == (0,)
            OUTPUT.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), "utf-8")
    assert receipt["schema_cleaned"]
    assert (
        receipt["request"]["max_tokens"] == 8
        and receipt["request"]["max_completion_tokens"] is None
    )
    assert receipt["response"]["usage"]["completion_tokens"] <= 8
    assert receipt["response"]["finish_reason"] == "length"


if __name__ == "__main__":
    run_async(main())
