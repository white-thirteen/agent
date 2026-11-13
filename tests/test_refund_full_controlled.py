"""Controlled full application topology with real LangGraph interrupt and resume."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import psycopg
import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from runtime_support import ControlledModel, MemorySessions, route

from app.agents.types import AgentType, TaskType
from app.core.config import Settings
from app.domain.orders import OrderView
from app.domain.refunds import canonical_digest
from app.graph.builder import build_supervisor_graph
from app.graph.specialists.knowledge.builder import build_knowledge_graph
from app.graph.specialists.order.builder import build_order_graph
from app.graph.specialists.refund.builder import build_refund_graph
from app.main import create_app
from app.runtime.agent_runtime import AgentRuntime, RunLimits
from app.runtime.model_gateway import ModelCallLimits, ModelGateway
from app.services.agent_service import AgentService
from app.tools.executor import ToolExecutor
from app.tools.implementations.orders import order_tools
from app.tools.implementations.refunds import refund_node_tools, refund_order_tool
from app.tools.policy import ToolPolicy
from app.tools.registry import ToolRegistry
from app.workflows.approvals import LocalDemoApprovalActor, VerifiedApproval


class Provider(ControlledModel):
    def __init__(self):
        super().__init__([route(TaskType.REFUND_APPLY, entities={"order_id": "order-1"})])
        self.structured_model = ControlledModel(
            [route(TaskType.REFUND_APPLY, entities={"order_id": "order-1"})]
        )
        self.order_tool_calls = 0

    def with_structured_output(self, schema, **kwargs):
        return self.structured_model

    def bind_tools(self, tools):
        assert len(tools) == 1 and tools[0]["function"]["name"] == "refund_order"
        return self

    async def ainvoke(self, messages):
        self.order_tool_calls += 1
        if self.order_tool_calls == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {"id": "original-call", "name": "refund_order", "args": {"order_id": "order-1"}}
                ],
            )
        return AIMessage(content="untrusted summary")


class ControlledOrders:
    async def get_order(self, *, user_id, order_id):
        return OrderView(
            order_id=order_id,
            amount="42.50",
            currency="CNY",
            payment_status="paid",
            is_refunded=False,
            created_at="2026-01-01T00:00:00+00:00",
        )


class ControlledRefunds:
    def __init__(self, fault=None):
        self.row = None
        self.effect_count = 0
        self.fault = fault
        self.fact = None

    async def check_eligibility(self, *, context, order_id):
        return {"order_id": order_id, "amount": "42.50", "currency": "CNY", "simulated": True}

    async def prepare_application(self, *, context, original_call):
        from decimal import Decimal

        self.row = {
            "application_id": context.application_id,
            "operation_id": context.operation_id,
            "user_id": context.user_id,
            "conversation_id": context.conversation_id,
            "thread_id": context.thread_id,
            "task_id": context.task_id,
            "workflow_id": context.workflow_id,
            "order_id": "order-1",
            "call_id": original_call.call_id,
            "tool_name": original_call.tool_name,
            "tool_version": original_call.tool_version,
            "raw_args": original_call.raw_args,
            "canonical_args": original_call.canonical_args,
            "args_digest": canonical_digest(original_call.canonical_args),
            "amount": Decimal("42.50"),
            "currency": "CNY",
        }
        return {
            "application_id": context.application_id,
            "operation_id": context.operation_id,
            "order_id": "order-1",
            "amount": "42.50",
            "currency": "CNY",
            "status": "PENDING",
        }

    async def execute_original(self, *, context, order_id):
        self.effect_count += 1
        self.fact = {
            "operation_id": context.operation_id,
            "order_id": order_id,
            "amount": "42.50",
            "currency": "CNY",
            "simulated": True,
        }
        if self.fault:
            raise psycopg.OperationalError("controlled database failure")
        return self.fact

    async def get_operation(self, *, user_id, operation_id):
        if self.fault == "committed":
            return {
                "application_id": self.row["application_id"],
                "status": "SUCCEEDED",
                "execution_result": self.fact,
            }
        return None

    async def get_application_status(self, *, user_id, conversation_id, application_id):
        if not self.row or any(
            self.row[key] != value
            for key, value in (
                ("user_id", user_id),
                ("conversation_id", conversation_id),
                ("application_id", application_id),
            )
        ):
            return None
        return {
            "application_id": application_id,
            "operation_id": self.row["operation_id"],
            "thread_id": self.row["thread_id"],
            "task_id": self.row["task_id"],
            "order_id": self.row["order_id"],
            "amount": f"{self.row['amount']:.2f}",
            "currency": self.row["currency"],
            "status": "SUCCEEDED" if self.fact else "PENDING",
            "execution_result": self.fact,
            "simulated": True,
        }

    async def reject_application(self, *, context, reason_code):
        return {
            "application_id": context.application_id,
            "operation_id": context.operation_id,
            "order_id": "order-1",
            "amount": "42.50",
            "currency": "CNY",
            "status": "REJECTED",
        }


class ControlledApprovals:
    def __init__(self, refunds):
        self.refunds = refunds
        self.row = None

    async def register_pending(self, *, approval_id, subject):
        now = datetime.now(UTC)
        self.row = {
            "approval_id": approval_id,
            "application_id": subject["application_id"],
            "subject_snapshot": subject,
            "subject_digest": canonical_digest(subject),
            "decision": "PENDING",
            "expires_at": now + timedelta(minutes=30),
            "db_now": now,
            "interrupt_id": None,
            "checkpoint_ns": None,
            "checkpoint_id": None,
            "approver_id": None,
            "decided_at": None,
        }
        return self.row

    async def get(self, approval_id):
        return self.row.copy()

    async def get_application(self, approval_id):
        return self.row.copy(), self.refunds.row.copy()

    async def bind_interrupt(self, approval_id, binding):
        self.row.update(
            interrupt_id=binding.interrupt_id,
            checkpoint_ns=binding.checkpoint_ns,
            checkpoint_id=binding.checkpoint_id,
        )
        return self.row

    async def prepare_resume(self, approval_id, *, interrupt_id, checkpoint_ns):
        assert self.row["decision"] in ("APPROVED", "REJECTED")
        return self.row

    async def decide(self, approval_id, *, actor, decision, expected_subject_digest):
        assert approval_id == self.row["approval_id"]
        assert expected_subject_digest == self.row["subject_digest"]
        assert actor.approver_id == "local-demo-approval"
        self.row.update(
            decision=decision, approver_id=actor.approver_id, decided_at=datetime.now(UTC)
        )
        return self.row

    async def verify_for_call(self, reference, *, original_call, context, interrupt_binding):
        assert self.row["decision"] == "APPROVED"
        subject = self.row["subject_snapshot"]
        return VerifiedApproval(
            reference.approval_id,
            context.application_id,
            context.operation_id,
            self.row["subject_digest"],
            subject,
            "local-demo-approval",
            datetime.now(UTC),
            self.row["expires_at"],
        )


@pytest.mark.parametrize(
    ("decision_value", "fault"),
    [("APPROVED", None), ("REJECTED", None), ("APPROVED", "committed"), ("APPROVED", "unknown")],
)
async def test_compiled_refund_graph_pauses_and_resumes_original_call(decision_value, fault):
    provider = Provider()
    gateway = ModelGateway(provider, ModelCallLimits(8, 5, 0))
    refunds = ControlledRefunds(fault)
    approvals = ControlledApprovals(refunds)
    registry = ToolRegistry()
    for definition in (
        *order_tools(ControlledOrders(), timeout_seconds=1, max_retries=0),
        *refund_node_tools(refunds, approvals, timeout_seconds=1),
        refund_order_tool(refunds, timeout_seconds=1),
    ):
        registry.register(definition)
    registry.freeze()
    executor = ToolExecutor(registry, ToolPolicy(), approval_service=approvals)
    graph = build_supervisor_graph(
        gateway=gateway,
        checkpointer=InMemorySaver(),
        specialists={
            AgentType.ORDER: build_order_graph(
                gateway=gateway, registry=registry, executor=executor
            ),
            AgentType.REFUND: build_refund_graph(
                gateway=gateway,
                registry=registry,
                executor=executor,
                approval_service=approvals,
                refund_service=refunds,
            ),
            AgentType.KNOWLEDGE: build_knowledge_graph(),
        },
    )
    runtime = AgentRuntime(
        graph,
        run_limits=RunLimits(30, 12),
        approval_service=approvals,
        refund_service=refunds,
        scope_resolver=lambda user: frozenset({"orders:read", "refunds:request"}),
    )
    sessions = MemorySessions()
    app = create_app(Settings(_env_file=None, app_env="test"))
    app.state.agent_runtime = runtime
    app.state.agent_service = AgentService(runtime, sessions)
    app.state.approval_service = approvals
    app.state.approval_actor_provider = LocalDemoApprovalActor()
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 1234))
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            chat = await client.post(
                "/agent/chat",
                json={
                    "user_id": "dev-user",
                    "conversation_id": "refund-flow",
                    "message": "申请退款",
                },
            )
            assert chat.status_code == 200 and "event: workflow_paused" in chat.text
            assert "original-call" not in chat.text and "untrusted summary" not in chat.text
            first = next(iter(runtime._records.values()))
            assert first.task_status == "waiting_approval"
            assert refunds.effect_count == 0 and approvals.row["interrupt_id"]
            body = {"user_id": "dev-user", "conversation_id": "refund-flow"}
            current = await client.post("/agent/tasks/current", json=body)
            assert current.status_code == 200
            assert current.json()["current_task"]["task_status"] == "waiting_approval"
            assert current.json()["current_task"]["run_id"] is None
            assert (
                current.json()["current_task"]["refund"]["application_id"]
                == refunds.row["application_id"]
            )
            query_path = f"/agent/refunds/{refunds.row['application_id']}/status"
            assert (await client.post(query_path, json=body)).status_code == 200
            assert (
                await client.post(query_path, json={**body, "conversation_id": "other"})
            ).status_code == 404
            assert sessions.creations == 1 and refunds.effect_count == 0
            assert (
                await client.post("/agent/tasks/current", json={**body, "conversation_id": "other"})
            ).status_code == 404
            assert (
                await client.post(f"/agent/refunds/{uuid4()}/status", json=body)
            ).status_code == 404
            await sessions.get_or_create(user_id="dev-user", conversation_id="empty")
            empty = await client.post(
                "/agent/tasks/current", json={**body, "conversation_id": "empty"}
            )
            assert empty.status_code == 200 and empty.json()["current_task"] is None
            assert sessions.creations == 2 and refunds.effect_count == 0
            path = f"/admin/approvals/{approvals.row['approval_id']}"
            detail = await client.get(path)
            assert detail.status_code == 200 and detail.json()["can_decide"]
            decision = await client.post(
                path + "/decision",
                json={
                    "decision": decision_value,
                    "subject_digest": approvals.row["subject_digest"],
                },
            )
            assert decision.status_code == 200 and decision.json()["approval"]["can_resume"]
            response = await client.post(path + "/resume", json={})
            assert response.status_code == 202
            accepted = response.json()
        await runtime._records[accepted["run_id"]].task
        result = await runtime.get_run(
            user_id="dev-user", conversation_id="refund-flow", run_id=accepted["run_id"]
        )
        assert result.task_id == first.execution.context.task_id
        assert result.run_id != first.execution.context.run_id
        if decision_value == "APPROVED" and fault != "unknown":
            assert result.task_status == "completed" and "42.50" in result.final_answer
            assert refunds.effect_count == 1
        elif fault == "unknown":
            assert result.task_status == "failed" and refunds.effect_count == 1
            snapshot = await graph.aget_state(
                {"configurable": {"thread_id": first.context.thread_id}}, subgraphs=True
            )
            assert snapshot.next == ("refund",)
            assert snapshot.tasks[0].state.next == ("reconcile_operation",)
            refunds.fault = "committed"
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                recovered = await client.post(path + "/resume", json={})
                assert recovered.status_code == 202
            resumed_id = recovered.json()["run_id"]
            await runtime._records[resumed_id].task
            resumed = await runtime.get_run(
                user_id="dev-user", conversation_id="refund-flow", run_id=resumed_id
            )
            assert resumed.task_status == "completed" and refunds.effect_count == 1
        else:
            assert refunds.effect_count == 0
    finally:
        await runtime.shutdown()
