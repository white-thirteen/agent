"""Run-budget compaction through real Saver and isolated PostgreSQL."""

import os
from uuid import uuid4

import psycopg
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from runtime_support import ControlledModel, context, run_to_end

from app.agents.prompts.supervisor import SUPERVISOR_SYSTEM_PROMPT
from app.agents.types import AgentType
from app.context.archive_store import ArchiveStore
from app.context.builder import ContextBuilder
from app.context.manager import ContextManager
from app.context.repository import ContextRepository
from app.core.config import Settings
from app.graph.builder import build_supervisor_graph
from app.graph.contracts import NewSupervisorOutput
from app.graph.specialists.knowledge.builder import build_knowledge_graph
from app.infrastructure.checkpoint import checkpoint_serializer
from app.runtime.agent_runtime import AgentRuntime, RunLimits
from app.runtime.model_gateway import ModelCallLimits, ModelGateway
from scripts import run_async


def test_run_compaction_charged_and_bound_without_checkpoint_pruning(tmp_path):
    dsn = os.environ.get("AGENT_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("isolated database not configured")
    info = conninfo_to_dict(dsn)
    assert (info.get("host"), info.get("port"), info.get("dbname"), info.get("user")) == (
        "127.0.0.1",
        "56431",
        "agent_demo_test",
        "agent_test",
    )

    async def probe():
        async with await psycopg.AsyncConnection.connect(
            dsn, autocommit=True, options="-c default_transaction_read_only=on"
        ) as guard:
            row = await (
                await guard.execute(
                    "SELECT current_database(),current_user,current_setting('server_version_num'),"
                    "shobj_description(oid,'pg_database') FROM pg_database "
                    "WHERE datname=current_database()"
                )
            ).fetchone()
            assert row == ("agent_demo_test", "agent_test", "170012", "codex-task131-0e62")
        user = "ctxrun231-" + uuid4().hex
        thread, conversation = user, "conversation"
        first = "x" * 1200
        measured = ContextBuilder(
            token_counter=count_tokens_approximately, count_method="estimate"
        ).build(
            mandatory=[
                SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT),
                HumanMessage(content=first),
            ],
            history=[],
            window_tokens=10000,
            output_tokens=128,
            schema=NewSupervisorOutput,
        )
        window = measured.input_tokens + 128 + 35
        settings = Settings(
            _env_file=None,
            model_name="controlled",
            context_model_window_tokens=window,
            context_model_output_tokens=128,
            context_summary_output_tokens=32,
            context_archive_read_tokens=window - 32,
            context_archive_retain_interactions=0,
        )

        class Provider(ControlledModel):
            def bind(self, **kwargs):
                return self

        class Summary:
            calls = 0

            def bind(self, **kwargs):
                assert kwargs == {"max_tokens": 32, "temperature": 0}
                return self

            async def ainvoke(self, messages):
                self.calls += 1
                return AIMessage(content="Earlier unsupported request.")

        provider = Provider([NewSupervisorOutput(kind="unsupported")] * 2)
        summary_model = Summary()
        gateway = ModelGateway(
            provider, ModelCallLimits(8, 5, 0), context_window=window, output_reserve=128
        )
        summary_gateway = ModelGateway(
            summary_model, ModelCallLimits(8, 5, 0), context_window=window, output_reserve=128
        )
        async with AsyncConnectionPool(dsn, open=False) as pool:
            async with AsyncConnectionPool(
                dsn,
                open=False,
                kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
            ) as saver_pool:
                saver = AsyncPostgresSaver(saver_pool, serde=checkpoint_serializer())
                graph = build_supervisor_graph(
                    gateway=gateway,
                    checkpointer=saver,
                    specialists={
                        role: build_knowledge_graph()
                        for role in (AgentType.ORDER, AgentType.REFUND, AgentType.KNOWLEDGE)
                    },
                )
                manager = ContextManager(ContextRepository(pool), ArchiveStore(tmp_path))
                runtime = AgentRuntime(
                    graph,
                    run_limits=RunLimits(30, 12),
                    context_manager=manager,
                    context_settings=settings,
                    context_gateway=summary_gateway,
                )
                runtime._maintenance.schedule = lambda *args: None
                try:
                    one, _, _ = await run_to_end(
                        runtime,
                        context(user=user, conversation=conversation, thread=thread, message=first),
                    )
                    await runtime._records[one.run_id].task
                    two, view, _ = await run_to_end(
                        runtime,
                        context(
                            user=user,
                            conversation=conversation,
                            thread=thread,
                            message="another request",
                        ),
                    )
                    await runtime._records[two.run_id].task
                    assert view.task_status == "rejected" and summary_model.calls == 1
                    assert view.model_call_usage.model_attempts == 2
                    snapshot = await graph.aget_state({"configurable": {"thread_id": thread}})
                    assert not snapshot.values.get("context_ref")
                    assert len(snapshot.values["messages"]) == 4
                    assert snapshot.values["context_view"]["history_ids"][0].startswith("summary:")
                finally:
                    await runtime.shutdown()
                    await saver.adelete_thread(thread)
                    async with pool.connection() as conn, conn.transaction():
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
                                f"DELETE FROM {table} WHERE user_id=%s AND conversation_id=%s",
                                (user, conversation),
                            )
                            assert (
                                await (
                                    await conn.execute(
                                        f"SELECT count(*) FROM {table} "
                                        "WHERE user_id=%s AND conversation_id=%s",
                                        (user, conversation),
                                    )
                                ).fetchone()
                            )[0] == 0
                    assert (await saver.aget_tuple({"configurable": {"thread_id": thread}})) is None

    run_async(probe())
