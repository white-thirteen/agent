"""Explicit Task6.1.2 HTTP protocol probe: controlled Chat, real PG/Saver/Store/Qwen.

Only UUID fixtures are written. No paid Chat calls, seed, process restart or migration.
"""

import argparse
import asyncio
import json
import tempfile
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.base import PutOp

from app.agents.types import TaskType
from app.core.config import Settings
from app.graph.contracts import RouteDecision, SupervisorOutput
from app.graph.specialists.knowledge.builder import AnswerDraft, EvidenceAssessment
from app.infrastructure.checkpoint import checkpoint_serializer
from app.infrastructure.postgres import validate_test_target
from app.knowledge.chunking import prepare_document
from app.knowledge.models import ManifestEntry
from app.main import create_app
from app.memory.manager import preference_namespace
from app.runtime.model_gateway import ModelCallLimits, ModelGateway
from scripts import run_async
from scripts.verify_05_memory_manage import database_snapshot, fingerprints

ANSWER = "普通聊天不能批准模拟退款；请通过独立本地审批入口提交。"


class ProtocolChat:
    """Choose deterministic model outputs; all tools and persistence remain real."""

    def __init__(self, order_id):
        self.order_id = order_id
        self.schema = None
        self.tools = []
        self.calls = 0

    def with_structured_output(self, schema, **kwargs):
        self.schema = schema
        return self

    def bind_tools(self, tools):
        self.schema = None
        self.tools = tools
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        if self.schema is SupervisorOutput:
            text = next(m.content for m in reversed(messages) if isinstance(m, HumanMessage))
            if text == "clarify":
                task, entities = TaskType.ORDER_QUERY, {}
            elif text == "请记住：回答语言=英语":
                task, entities = TaskType.MEMORY_MANAGE, {}
            elif text == "knowledge":
                task, entities = TaskType.KNOWLEDGE_QA, {}
            elif text == "refund":
                task, entities = TaskType.REFUND_APPLY, {"order_id": self.order_id}
            else:
                task, entities = TaskType.ORDER_QUERY, {"order_id": self.order_id}
            parsed = SupervisorOutput(
                kind="route",
                decision=RouteDecision(
                    agent_type=task.target_agent,
                    task_type=task,
                    task_goal="查询单个订单" if task is TaskType.ORDER_QUERY else text,
                    entities=entities,
                    needs_clarification=text == "clarify",
                    missing_fields=["order_id"] if text == "clarify" else [],
                    clarification_question="请提供订单号。" if text == "clarify" else None,
                ),
            )
        elif self.schema in (EvidenceAssessment, AnswerDraft):
            evidence = json.loads(messages[-1].content)["evidence"]
            ids = [e["evidence_id"] for e in evidence]
            parsed = (
                EvidenceAssessment(status="sufficient", selected_ids=ids, reason="controlled")
                if self.schema is EvidenceAssessment
                else AnswerDraft(answer=ANSWER, citations=ids)
            )
        else:
            name = self.tools[0]["function"]["name"]
            if name == "get_order" and any(isinstance(m, ToolMessage) for m in messages):
                return AIMessage(content="private model summary")
            args = (
                {"query": json.loads(messages[-1].content)["question"], "domain": None, "top_k": 3}
                if name == "search_knowledge"
                else {"order_id": self.order_id}
            )
            return AIMessage(
                content="private model planner",
                tool_calls=[{"id": "protocol-call-" + uuid4().hex, "name": name, "args": args}],
            )
        return {
            "raw": AIMessage(content="private structured"),
            "parsed": parsed,
            "parsing_error": None,
        }


def frames(response):
    assert response.status_code == 200, response.status_code
    events = []
    for frame in response.text.replace("\r\n", "\n").strip().split("\n\n"):
        lines = frame.splitlines()
        events.append({"event": lines[0][7:], "data": json.loads(lines[1][6:])})
    sequences = [e["data"]["sequence"] for e in events]
    assert sequences == sorted(set(sequences))
    assert sum(e["event"] == "done" for e in events) == 1
    for event in events:
        data = event["data"]
        assert data["task_id"] == data["workflow_id"]
    for secret in (
        "private model",
        "private structured",
        "call_records",
        "permission_scopes",
        "raw_args",
        "checkpoint_ns",
        "api_key",
        "embedding_profile",
    ):
        assert secret not in response.text
    return events


async def verify(output):
    original = Settings()
    validate_test_target(original.test_database_url, original.database_url)
    prefix = "protocol612-" + uuid4().hex
    user, order_id, document_id = (prefix + suffix for suffix in ("-user", "-order", "-doc"))
    settings = original.model_copy(
        update={
            "database_url": original.test_database_url,
            "app_env": "test",
            "demo_user_ids": (user,),
            "embedding_enabled": True,
        }
    )
    report = {
        "probe_id": prefix,
        "chat": "controlled; no paid provider requests",
        "dependencies": "real PostgreSQL/Saver/Store/Qwen CPU1024",
        "cases": [],
    }

    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")

    model = ProtocolChat(order_id)

    @asynccontextmanager
    async def controlled_model(local):
        yield (
            model,
            ModelGateway(
                model,
                ModelCallLimits(
                    local.model_max_attempts, local.model_timeout_seconds, local.model_max_retries
                ),
            ),
        )

    with patch("app.main.model_resources", controlled_model):
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            runtime, pool = app.state.agent_runtime, app.state.pool
            graph = runtime._graph
            retriever = app.state.knowledge_retriever
            saver = AsyncPostgresSaver(app.state.checkpoint_pool, serde=checkpoint_serializer())
            before = await database_snapshot(pool)
            report["protected_before"] = fingerprints(before)
            threads, conversations = [], []
            with tempfile.TemporaryDirectory(prefix=prefix) as directory:
                root = Path(directory)
                source = root / "approval.md"
                try:
                    async with pool.connection() as conn:
                        await conn.execute(
                            "INSERT INTO demo_orders(order_id,owner_id,amount,"
                            "currency,payment_status,is_refunded,created_at) "
                            "VALUES (%s,%s,12.34,'CNY','paid',false,now())",
                            (order_id, user),
                        )
                    source.write_text(
                        "# Demo审批规则\n\n普通聊天不能批准模拟退款。"
                        "请通过独立本地审批入口提交。\n",
                        "utf-8",
                    )
                    doc = prepare_document(
                        root,
                        ManifestEntry(
                            document_id=document_id,
                            filename=source.name,
                            source_title="Demo审批规则",
                            domain="platform_help",
                            public_source_key=prefix,
                        ),
                        retriever.profile,
                    )
                    vectors = await retriever.embeddings.aembed_documents(
                        [chunk.embedding_text for chunk in doc.chunks]
                    )
                    await retriever.repository.replace(doc, vectors)
                    conversation = prefix + "-conversation"
                    conversations.append(conversation)
                    body = {"user_id": user, "conversation_id": conversation}
                    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
                    async with httpx.AsyncClient(
                        transport=transport, base_url="http://test", timeout=180
                    ) as client:

                        async def chat(message, **extra):
                            response = await client.post(
                                "/agent/chat", json={**body, "message": message, **extra}
                            )
                            events = frames(response)
                            binding = await app.state.sessions.get(**body)
                            thread = str(binding.thread_id)
                            if thread not in threads:
                                threads.append(thread)
                            state = (
                                await graph.aget_state({"configurable": {"thread_id": thread}})
                            ).values
                            view = (
                                await client.post(
                                    f"/agent/runs/{events[-1]['data']['run_id']}/status", json=body
                                )
                            ).json()
                            assert view["task_id"] == events[-1]["data"]["task_id"]
                            if view["task_status"] != "waiting_approval":
                                assert state["run_usage"] == view["run_usage"]
                                assert state["model_call_usage"] == view["model_call_usage"]
                                assert state["task_status"] == view["task_status"]
                                assert view["usage_complete"]
                            case = {
                                "message": message,
                                "events": events,
                                "view": view,
                                "thread": thread,
                                "snapshot_task_status": str(state["task_status"]),
                            }
                            report["cases"].append(case)
                            save()
                            return case, state

                        memory, _ = await chat("请记住：回答语言=英语")
                        assert memory["view"]["sources"] == []
                        assert memory["view"]["run_usage"]["tool_calls"] == 2
                        knowledge, state = await chat("knowledge")
                        assert (
                            knowledge["view"]["final_answer"]
                            == state["specialist_result"].approved_answer
                            == ANSWER
                        )
                        sources = [s.model_dump(mode="json") for s in state["sources"]]
                        assert knowledge["view"]["sources"] == sources and sources
                        token = next(e for e in knowledge["events"] if e["event"] == "token")
                        assert (
                            token["data"]["content"] == ANSWER
                            and token["data"]["sources"] == sources
                        )
                        assert {s["document_id"] for s in sources} == {document_id}
                        clarification, state = await chat("clarify")
                        assert state["task_status"] == "needs_input" and state["sources"] == []
                        assert (
                            state["specialist_result"] is None
                            and state["memory_read_record"] is None
                        )
                        continued, state = await chat("order")
                        assert continued["view"]["task_id"] == clarification["view"]["task_id"]
                        assert continued["view"]["run_id"] != clarification["view"]["run_id"]
                        assert continued["view"]["model_call_usage"]["model_attempts"] == 4
                        assert state["specialist_result"].facts["order"]["order_id"] == order_id
                        assert continued["view"]["sources"] == []
                        assert len({c["thread"] for c in report["cases"]}) == 1
                        assert len({c["view"]["task_id"] for c in report["cases"]}) == 3

                        # Hold the real Graph before it writes any new Task checkpoint.
                        entered, release = asyncio.Event(), asyncio.Event()
                        invoke = type(graph).ainvoke

                        async def delayed(self, *args, **kwargs):
                            entered.set()
                            await release.wait()
                            return await invoke(self, *args, **kwargs)

                        with patch.object(type(graph), "ainvoke", delayed):
                            request = asyncio.create_task(
                                client.post("/agent/chat", json={**body, "message": "order"})
                            )
                            try:
                                await entered.wait()
                                active = next(
                                    r
                                    for r in runtime._records.values()
                                    if r.run_status == "running"
                                )
                                public = (
                                    await client.post("/agent/tasks/current", json=body)
                                ).json()["current_task"]
                                assert public["task_id"] == active.execution.context.task_id
                                assert public["task_id"] != continued["view"]["task_id"]
                                assert public["run_id"] == active.context.run_id
                                conflict = await client.post(
                                    "/agent/chat", json={**body, "message": "order"}
                                )
                                assert conflict.status_code == 409
                                report["before_first_checkpoint"] = public
                            finally:
                                release.set()
                                frames(await request)

                        pending, _ = await chat("refund")
                        assert pending["view"]["task_status"] == "waiting_approval"
                        assert pending["view"]["final_answer"] is None
                        paused = next(
                            e["data"] for e in pending["events"] if e["event"] == "workflow_paused"
                        )
                        current = (await client.post("/agent/tasks/current", json=body)).json()[
                            "current_task"
                        ]
                        assert current["task_status"] == "waiting_approval"
                        assert current["refund"]["approval_id"] == paused["approval_id"]
                        approval = await app.state.approval_service.get(paused["approval_id"])
                        _, application = await app.state.approval_service.get_application(
                            paused["approval_id"]
                        )
                        classified = await runtime._inspect_refund_checkpoint(approval, application)
                        assert classified.kind == "pending" and classified.bound
                        child = classified.child.values
                        assert (
                            child["run_usage"]["tool_calls"]
                            == pending["view"]["run_usage"]["tool_calls"]
                        )
                        assert child["model_call_usage"] == pending["view"]["model_call_usage"]
                        report["pause"] = {
                            "public": current,
                            "child_usage": child["run_usage"],
                            "child_model_usage": child["model_call_usage"],
                            "call_id": approval["subject_snapshot"]["call_id"],
                        }
                        for mode in ("auto", "new_task"):
                            blocked = await client.post(
                                "/agent/chat", json={**body, "message": "order", "input_mode": mode}
                            )
                            assert blocked.status_code == 409
                        path = f"/admin/approvals/{paused['approval_id']}"
                        decision = await client.post(
                            path + "/decision",
                            json={
                                "decision": "REJECTED",
                                "subject_digest": approval["subject_digest"],
                            },
                        )
                        assert decision.status_code == 200
                        acceptance = await client.post(path + "/resume", json={})
                        assert acceptance.status_code == 202
                        accepted = acceptance.json()
                        assert (
                            accepted["accepted"]
                            and accepted["task_id"] == pending["view"]["task_id"]
                        )
                        assert accepted["run_id"] != pending["view"]["run_id"]
                        resumed_record = runtime._records[accepted["run_id"]]
                        await resumed_record.task
                        resumed = asdict(runtime._view(resumed_record))
                        assert (
                            resumed["task_status"] == "rejected"
                            and resumed["run_status"] == "completed"
                        )
                        assert (
                            resumed["run_usage"]["tool_calls"] >= child["run_usage"]["tool_calls"]
                        )
                        assert (
                            resumed["model_call_usage"]["model_attempts"]
                            >= child["model_call_usage"]["model_attempts"]
                        )
                        report["resume"] = {
                            "acceptance": accepted,
                            "usage": resumed["run_usage"],
                            "model_usage": resumed["model_call_usage"],
                            "task_status": resumed["task_status"],
                        }
                        count, calls = len(runtime._records), model.calls
                        ended = await client.post(path + "/resume", json={})
                        assert ended.status_code == 200 and not ended.json()["accepted"]
                        assert ended.json()["run_id"] is None
                        assert len(runtime._records) == count and model.calls == calls
                        report["normal_end_resume"] = ended.json()
                        # Run views are evictable; persistent current Task/business survive.
                        runtime._records.clear()
                        missing = await client.post(
                            f"/agent/runs/{accepted['run_id']}/status", json=body
                        )
                        assert missing.status_code == 404
                        current = (await client.post("/agent/tasks/current", json=body)).json()[
                            "current_task"
                        ]
                        assert current["task_status"] == "rejected" and current["run_id"] is None
                        business = await client.post(
                            f"/agent/refunds/{paused['application_id']}/status", json=body
                        )
                        assert (
                            business.status_code == 200 and business.json()["status"] == "REJECTED"
                        )
                        report["cache_lost"] = {
                            "run_http": missing.status_code,
                            "current": current,
                            "business": business.json(),
                        }
                        async with pool.connection() as conn:
                            assert (
                                await (
                                    await conn.execute(
                                        "SELECT is_refunded FROM demo_orders "
                                        "WHERE order_id=%s AND owner_id=%s",
                                        (order_id, user),
                                    )
                                ).fetchone()
                            ) == (False,)
                    report["probe_result"] = "PASS"
                finally:
                    await runtime.shutdown()
                    for conversation in conversations:
                        binding = await app.state.sessions.get(
                            user_id=user, conversation_id=conversation
                        )
                        if binding and str(binding.thread_id) not in threads:
                            threads.append(str(binding.thread_id))
                    for thread in threads:
                        await saver.adelete_thread(thread)
                    async with pool.connection() as conn:
                        await conn.execute(
                            "DELETE FROM approvals WHERE subject_snapshot->>'user_id'=%s", (user,)
                        )
                        await conn.execute("DELETE FROM refund_requests WHERE user_id=%s", (user,))
                        await conn.execute(
                            "DELETE FROM demo_orders WHERE order_id=%s AND owner_id=%s",
                            (order_id, user),
                        )
                        await conn.execute(
                            "DELETE FROM sessions WHERE user_id=%s AND conversation_id=ANY(%s)",
                            (user, conversations),
                        )
                    await app.state.memory_store.abatch(
                        [PutOp(preference_namespace(user), "profile", None)]
                    )
                    await retriever.repository.remove(document_id)
                    after = await database_snapshot(pool)
                    report["protected_after"] = fingerprints(after)
                    report["protected_unchanged"] = before == after
                    report["exact_cleanup"] = {
                        "user": user,
                        "threads": threads,
                        "order_id": order_id,
                        "document_id": document_id,
                        "conversations": conversations,
                    }
                    save()
                    assert before == after
    print("Task6.1.2 real persistence / controlled Chat probe PASS", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh evidence path")
    run_async(verify(args.output))


if __name__ == "__main__":
    main()
