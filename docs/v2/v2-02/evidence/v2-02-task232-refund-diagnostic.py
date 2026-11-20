"""Re-run the isolated repair test with metadata-only cutover diagnostics."""

import sys

import app.main as app_module

sys.path.insert(0, "tests")
from test_refund_repair_postgres import (  # noqa: E402
    test_real_repair_response_loss_concurrency_audit_and_expired_graph,
)

original = app_module.legacy_memory_cutover_safe


async def audited(graph, pool):
    result = await original(graph, pool)
    if not result:
        async with pool.connection() as connection:
            bindings = await (
                await connection.execute("SELECT user_id,conversation_id,thread_id FROM sessions")
            ).fetchall()
        for _, _, thread in bindings:
            seen = set()
            async for state in graph.aget_state_history(
                {"configurable": {"thread_id": str(thread)}}
            ):
                values = state.values
                task = values.get("task_id")
                if not task:
                    print(
                        {
                            "missing_task": True,
                            "keys": sorted(values),
                            "metadata": state.metadata,
                            "has_next": bool(state.next),
                        },
                        flush=True,
                    )
                    continue
                if task in seen:
                    continue
                seen.add(task)
                pending = values.get("pending_task")
                print(
                    {
                        "status": str(values.get("task_status")),
                        "type": str(values.get("task_type")),
                        "has_next": bool(state.next),
                        "has_pending": pending is not None,
                    },
                    flush=True,
                )
    return result


app_module.legacy_memory_cutover_safe = audited
test_real_repair_response_loss_concurrency_audit_and_expired_graph()
