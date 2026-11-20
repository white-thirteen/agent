"""Revision adoption through a real isolated PostgreSQL Saver and archive files."""

import os
from uuid import uuid4

import psycopg
import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from runtime_support import ControlledModel, compiled, context, run_to_end

from app.context.archive_store import ArchiveStore, canonical, digest
from app.context.manager import ContextManager
from app.context.models import (
    ContextRevision,
    PublicInteraction,
    PublicMessage,
    SessionIdentity,
    Summary,
)
from app.context.repository import ContextRepository
from app.graph.contracts import SupervisorOutput
from app.infrastructure.checkpoint import checkpoint_serializer
from app.runtime.agent_runtime import AgentRuntime, RunLimits
from scripts import run_async


@pytest.mark.parametrize(
    "fault", ["receipt"]
)
def test_real_revision_adoption_and_receipt_recovery(tmp_path, fault):
    dsn = os.environ.get("AGENT_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("isolated Linux database required")

    parts = conninfo_to_dict(dsn)
    assert (parts.get("host"), parts.get("port"), parts.get("dbname"), parts.get("user")) == (
        "127.0.0.1",
        "56431",
        "agent_demo_test",
        "agent_test",
    ), "Dedicated PostgreSQL target required"

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
        token = uuid4().hex
        identity = SessionIdentity(user_id="ctx222-" + token, conversation_id="conv-" + token)
        thread = "ctx222-" + token
        async with AsyncConnectionPool(dsn, open=False) as pool:
            async with AsyncConnectionPool(
                dsn,
                open=False,
                kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
            ) as saver_pool:
                saver = AsyncPostgresSaver(saver_pool, serde=checkpoint_serializer())
                repository = ContextRepository(pool)
                manager = ContextManager(repository, ArchiveStore(tmp_path))
                model = ControlledModel([SupervisorOutput(kind="unsupported")] * 4)
                graph = compiled(model, saver=saver)
                runtime = AgentRuntime(graph, run_limits=RunLimits(10, 12), context_manager=manager)
                try:
                    ctx = context(
                        user=identity.user_id, conversation=identity.conversation_id, thread=thread
                    )
                    first, view, _ = await run_to_end(runtime, ctx)
                    await runtime._records[first.run_id].task
                    assert view.task_status == "rejected"
                    snapshot = await graph.aget_state({"configurable": {"thread_id": thread}})
                    source_id = snapshot.config["configurable"]["checkpoint_id"]
                    metadata = snapshot.values["public_message_metadata"]
                    msgs = tuple(
                        PublicMessage(
                            message_id=m.id,
                            role="user" if m.type == "human" else "assistant",
                            content=m.content,
                            task_id=metadata[m.id]["task_id"],
                            run_id=metadata[m.id]["run_id"],
                        )
                        for m in snapshot.values["messages"]
                    )
                    archive = await manager.publish(
                        identity,
                        source_id,
                        [
                            PublicInteraction(
                                task_id=first.task_id, task_status="REJECTED", messages=msgs
                            )
                        ],
                        retain_recent=0,
                        max_messages=2,
                        session_status="REJECTED",
                    )
                    summary = Summary(
                        identity=identity,
                        summary_id="s1",
                        version=1,
                        text="background",
                        archive_refs=(archive.archive_ref,),
                        message_ids=tuple(m.message_id for m in msgs),
                        parent_summary_id=None,
                        input_hash="input",
                        status="READY",
                    )
                    await repository.save_summary(
                        summary,
                        source_checkpoint_id=source_id,
                        policy_version="p",
                        model_version="m",
                        prompt_version="v",
                    )
                    revision = ContextRevision(
                        identity=identity,
                        revision=1,
                        base_revision=None,
                        source_checkpoint_id=source_id,
                        message_ids=summary.message_ids,
                        content_hash=digest(canonical([m.model_dump() for m in msgs])),
                        archive_refs=summary.archive_refs,
                        summary_id="s1",
                        policy_version="p",
                        model_version="m",
                        prompt_version="v",
                        status="PREPARING",
                    )
                    assert (
                        await manager.publish_revision(revision, max_bytes=100000)
                    ).status == "PUBLISHED"
                    before = await graph.aget_state({"configurable": {"thread_id": thread}})
                    assert (
                        "context_ref" not in before.values and len(before.values["messages"]) == 2
                    )
                    if fault in ("receipt", "after_commit_receipt"):
                        original_mark = repository.mark_revision

                        async def fail_once(*args, **kwargs):
                            if args[2] == "APPLIED":
                                repository.mark_revision = original_mark
                                raise RuntimeError("simulated receipt failure")
                            return await original_mark(*args, **kwargs)

                        repository.mark_revision = fail_once
                    if fault in ("before_commit", "after_commit", "after_commit_receipt"):
                        original_put = saver.aput

                        async def fail_put(config, checkpoint, metadata, versions):
                            if checkpoint["channel_values"].get("context_ref"):
                                saver.aput = original_put
                                if fault in ("after_commit", "after_commit_receipt"):
                                    await original_put(config, checkpoint, metadata, versions)
                                raise RuntimeError("simulated Saver commit failure")
                            return await original_put(config, checkpoint, metadata, versions)

                        saver.aput = fail_put
                    if fault == "stale":
                        await graph.aupdate_state(
                            {"configurable": {"thread_id": thread}},
                            {"messages": [HumanMessage(id=msgs[0].message_id, content="changed")]},
                            as_node="run_finish",
                        )
                    if fault == "append":
                        await graph.aupdate_state(
                            {"configurable": {"thread_id": thread}},
                            {"messages": [HumanMessage(id="outside-range", content="later")]},
                            as_node="run_finish",
                        )
                    if fault == "stale":
                        saved = (
                            await graph.aget_state({"configurable": {"thread_id": thread}})
                        ).values
                        _, stale = await runtime._context_candidate(ctx, saved)
                        assert stale == 1
                        assert (await repository.get_revision(identity, 1)).status == "PUBLISHED"
                    second_ctx = context(
                        user=identity.user_id,
                        conversation=identity.conversation_id,
                        thread=thread,
                        message="next",
                    )
                    second, view, _ = await run_to_end(runtime, second_ctx)
                    await runtime._records[second.run_id].task
                    after = await graph.aget_state({"configurable": {"thread_id": thread}})
                    old = await graph.aget_state(
                        {"configurable": {"thread_id": thread, "checkpoint_id": source_id}}
                    )
                    assert "context_ref" not in old.values and len(old.values["messages"]) == 2
                    revision_row = await repository.get_revision(identity, 1)
                    persisted = await saver.aget_tuple(after.config)
                    persisted_values = persisted.checkpoint["channel_values"]
                    if fault == "stale":
                        assert revision_row.status == "STALE"
                        assert not persisted_values.get("context_ref")
                        assert set(summary.message_ids).issubset(
                            m.id for m in persisted_values["messages"]
                        )
                    elif fault == "before_commit":
                        assert thread in runtime._uncertain
                        assert not persisted_values.get("context_ref")
                        assert set(summary.message_ids).issubset(
                            m.id for m in persisted_values["messages"]
                        )
                        assert revision_row.status == "PUBLISHED"
                    else:
                        assert after.values["context_ref"] == {"revision": 1, "summary_id": "s1"}
                        assert not set(summary.message_ids).intersection(
                            m.id for m in after.values["messages"]
                        )
                        if fault == "append":
                            assert revision_row.status == "APPLIED"
                            assert any(m.id == "outside-range" for m in after.values["messages"])
                        elif fault in ("after_commit", "after_commit_receipt"):
                            assert thread in runtime._uncertain
                            if fault == "after_commit_receipt":
                                assert revision_row.status == "PUBLISHED"
                                await runtime.reconcile_context_receipt(
                                    thread_id=thread,
                                    user_id=identity.user_id,
                                    conversation_id=identity.conversation_id,
                                )
                                assert (
                                    await repository.get_revision(identity, 1)
                                ).status == "APPLIED"
                                assert thread in runtime._uncertain
                            else:
                                assert revision_row.status == "APPLIED"
                        else:
                            assert (
                                view.task_status == "rejected"
                                and revision_row.status == "PUBLISHED"
                            )
                            await runtime._confirm_context(
                                thread,
                                identity.user_id,
                                identity.conversation_id,
                                record_receipt=False,
                            )
                            assert (
                                await repository.get_revision(identity, 1)
                            ).status == "PUBLISHED"
                            third_ctx = context(
                                user=identity.user_id,
                                conversation=identity.conversation_id,
                                thread=thread,
                                message="again",
                            )
                            third, _, _ = await run_to_end(runtime, third_ctx)
                            await runtime._records[third.run_id].task
                            assert (await repository.get_revision(identity, 1)).status == "APPLIED"
                            snap2 = await graph.aget_state({"configurable": {"thread_id": thread}})
                            cp2 = snap2.config["configurable"]["checkpoint_id"]
                            meta2 = snap2.values["public_message_metadata"]
                            msgs2 = tuple(
                                PublicMessage(
                                    message_id=m.id,
                                    role="user" if m.type == "human" else "assistant",
                                    content=m.content,
                                    task_id=meta2[m.id]["task_id"],
                                    run_id=meta2[m.id]["run_id"],
                                )
                                for m in snap2.values["messages"][:2]
                            )
                            archive2 = await manager.publish(
                                identity,
                                cp2,
                                [
                                    PublicInteraction(
                                        task_id=second.task_id,
                                        task_status="REJECTED",
                                        messages=msgs2,
                                    )
                                ],
                                retain_recent=0,
                                max_messages=2,
                                session_status="REJECTED",
                            )
                            summary2 = Summary(
                                identity=identity,
                                summary_id="s2",
                                version=2,
                                text="extended",
                                archive_refs=(*summary.archive_refs, archive2.archive_ref),
                                message_ids=(*summary.message_ids, *(m.message_id for m in msgs2)),
                                parent_summary_id=None,
                                input_hash="input2",
                                status="READY",
                            )
                            await repository.save_summary(
                                summary2,
                                source_checkpoint_id=cp2,
                                policy_version="p",
                                model_version="m",
                                prompt_version="v",
                            )
                            revision2 = ContextRevision(
                                identity=identity,
                                revision=2,
                                base_revision=1,
                                source_checkpoint_id=cp2,
                                message_ids=tuple(m.message_id for m in msgs2),
                                content_hash=digest(canonical([m.model_dump() for m in msgs2])),
                                archive_refs=summary2.archive_refs,
                                summary_id="s2",
                                policy_version="p",
                                model_version="m",
                                prompt_version="v",
                                status="PREPARING",
                            )
                            await manager.publish_revision(revision2, max_bytes=100000)
                            fourth, _, _ = await run_to_end(
                                runtime,
                                context(
                                    user=identity.user_id,
                                    conversation=identity.conversation_id,
                                    thread=thread,
                                    message="fourth",
                                ),
                            )
                            await runtime._records[fourth.run_id].task
                            assert (await repository.get_revision(identity, 2)).status == "APPLIED"
                            old_ref = await graph.aget_state(
                                {"configurable": {"thread_id": thread, "checkpoint_id": cp2}}
                            )
                            assert old_ref.values["context_ref"] == {
                                "revision": 1,
                                "summary_id": "s1",
                            }
                    assert (
                        await repository.get_revision(
                            SessionIdentity(
                                user_id="foreign", conversation_id=identity.conversation_id
                            ),
                            1,
                        )
                        is None
                    )
                finally:
                    await runtime.shutdown()
                    await saver.adelete_thread(thread)
                    async with pool.connection() as conn, conn.transaction():
                        for table in ("context_revision", "context_summary", "context_archive"):
                            await conn.execute(
                                f"DELETE FROM {table} WHERE user_id=%s AND conversation_id=%s",
                                (identity.user_id, identity.conversation_id),
                            )
                    async with pool.connection() as conn:
                        for table in ("context_revision", "context_summary", "context_archive"):
                            row = await (
                                await conn.execute(
                                    f"SELECT count(*) FROM {table} "
                                    "WHERE user_id=%s AND conversation_id=%s",
                                    (identity.user_id, identity.conversation_id),
                                )
                            ).fetchone()
                            assert row[0] == 0
                    assert (await saver.aget_tuple({"configurable": {"thread_id": thread}})) is None

    run_async(probe())

