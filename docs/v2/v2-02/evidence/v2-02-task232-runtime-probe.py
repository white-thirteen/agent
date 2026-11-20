"""Real model/Runtime/Saver probe with enabled context limits and exact cleanup."""

import json
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.base import PutOp

from app.core.config import Settings
from app.infrastructure.checkpoint import checkpoint_serializer, open_checkpoint_pool
from app.infrastructure.postgres import open_pool, validate_test_target
from app.infrastructure.store import store_resources
from app.main import create_app
from app.memory.manager import preference_namespace
from scripts import run_async
from scripts.verify_05_memory_manage import compare_publication_snapshots, database_snapshot

OUTPUT = Path("docs/v2/v2-02/evidence/v2-02-task232-runtime-probe.json")


async def main():
    assert not OUTPUT.exists()
    original = Settings()
    assert original.model_configured and original.test_database_url is not None
    validate_test_target(original.test_database_url, original.database_url)
    prefix = "ctx232-runtime-" + uuid4().hex
    user, other = prefix + "-user", prefix + "-other"
    order_id = prefix + "-order"
    conversations = [prefix + "-history", prefix + "-baseline"]
    report = {
        "model": original.model_name,
        "host": urlsplit(original.model_base_url).hostname,
        "cases": [],
        "cleanup": False,
    }

    def save():
        OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), "utf-8")

    with tempfile.TemporaryDirectory(prefix="ctx232-runtime-") as directory:
        settings = original.model_copy(
            update={
                "database_url": original.test_database_url,
                "app_env": "test",
                "demo_user_ids": (user, other),
                "embedding_enabled": False,
                "context_model_window_tokens": 16384,
                "context_model_output_tokens": 512,
                "context_summary_output_tokens": 256,
                "context_archive_read_tokens": 4096,
                "context_archive_retain_interactions": 10,
                "context_archive_root": Path(directory),
            }
        )
        report["context_limits"] = {
            "window": 16384,
            "output": 512,
            "summary_output": 256,
            "archive_input": 4096,
            "retain_interactions": 10,
        }
        pool = await open_pool(settings)
        checkpoint_pool = await open_checkpoint_pool(settings)
        saver = AsyncPostgresSaver(checkpoint_pool, serde=checkpoint_serializer())
        before = await database_snapshot(pool)
        threads = set()
        try:
            async with pool.connection() as conn:
                await conn.execute(
                    "INSERT INTO demo_orders(order_id,owner_id,amount,currency,payment_status,"
                    "is_refunded,created_at) VALUES (%s,%s,12.34,'CNY','paid',false,now())",
                    (order_id, user),
                )

            async def request(app, label, conversation, message):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=180
                ) as client:
                    response = await client.post(
                        "/agent/chat",
                        json={"user_id": user, "conversation_id": conversation, "message": message},
                    )
                binding = await app.state.sessions.get(user_id=user, conversation_id=conversation)
                if binding is None:
                    report["cases"].append({"label": label, "status_code": response.status_code})
                    save()
                    return
                thread = str(binding.thread_id)
                threads.add(thread)
                state = (
                    await app.state.agent_runtime._graph.aget_state(
                        {"configurable": {"thread_id": thread}}
                    )
                ).values
                specialist = state.get("specialist_result")
                report["cases"].append(
                    {
                        "label": label,
                        "status_code": response.status_code,
                        "thread_id": thread,
                        "task_id": state.get("task_id"),
                        "run_id": state.get("run_id"),
                        "task_status": state.get("task_status"),
                        "context_view": state.get("context_view"),
                        "specialist_result": specialist.model_dump(mode="json")
                        if specialist
                        else None,
                        "history_ids": [
                            [m.id for m in interaction]
                            for interaction in state.get("context_history", [])
                        ],
                        "events": [
                            json.loads(line[6:])
                            for line in response.text.splitlines()
                            if line.startswith("data: ")
                        ],
                    }
                )
                save()

            app = create_app(settings)
            async with app.router.lifespan_context(app):
                await request(app, "order", conversations[0], f"请查询订单 {order_id} 的当前状态。")
                async with pool.connection() as conn:
                    report["order_database"] = await (
                        await conn.execute(
                            "SELECT amount,currency,payment_status,is_refunded FROM demo_orders "
                            "WHERE order_id=%s AND owner_id=%s",
                            (order_id, user),
                        )
                    ).fetchone()
                save()
                await request(app, "with_history", conversations[0], "这个演示能处理什么问题？")
                await request(app, "without_history", conversations[1], "这个演示能处理什么问题？")
            report["first_application_closed"] = True
            save()
            app = create_app(settings)
            async with app.router.lifespan_context(app):
                await request(app, "after_restart", conversations[0], "请再简要说明演示范围。")
                report["same_binding_after_restart"] = report["cases"][0].get(
                    "thread_id"
                ) == report["cases"][-1].get("thread_id")
                save()
        finally:
            async with pool.connection() as conn:
                rows = await (
                    await conn.execute(
                        "SELECT thread_id FROM sessions WHERE user_id=%s "
                        "AND conversation_id=ANY(%s)",
                        (user, conversations),
                    )
                ).fetchall()
                threads.update(str(row[0]) for row in rows)
            for thread in threads:
                await saver.adelete_thread(thread)
            async with store_resources(settings) as store:
                await store.abatch(
                    [
                        PutOp(preference_namespace(user), "profile", None),
                        PutOp(preference_namespace(other), "profile", None),
                    ]
                )
            async with pool.connection() as conn, conn.transaction():
                await conn.execute(
                    "DELETE FROM preference_command_receipt WHERE user_id=ANY(%s)", ([user, other],)
                )
                await conn.execute(
                    "DELETE FROM demo_orders WHERE order_id=%s AND owner_id=%s", (order_id, user)
                )
                await conn.execute(
                    "DELETE FROM context_maintenance_attempt WHERE maintenance_id IN "
                    "(SELECT maintenance_id FROM context_maintenance WHERE user_id=%s)",
                    (user,),
                )
                for table in (
                    "context_maintenance",
                    "context_revision",
                    "context_summary",
                    "context_archive",
                ):
                    await conn.execute(
                        f"DELETE FROM {table} WHERE user_id=%s AND conversation_id=ANY(%s)",
                        (user, conversations),
                    )
                await conn.execute(
                    "DELETE FROM sessions WHERE user_id=%s AND conversation_id=ANY(%s)",
                    (user, conversations),
                )
            after = await database_snapshot(pool)
            report["cleanup"] = compare_publication_snapshots(before, after, expected_delta=0)
            save()
            await checkpoint_pool.close()
            await pool.close()
            assert report["cleanup"]["protected_unchanged"]


if __name__ == "__main__":
    run_async(main())
