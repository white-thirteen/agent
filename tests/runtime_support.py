"""Controlled model and real compiled topology shared by stage 02 regression tests."""

import inspect
from uuid import uuid4

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.agents.types import AgentType, TaskType
from app.graph.builder import build_supervisor_graph
from app.graph.contracts import RouteDecision, SupervisorOutput
from app.graph.specialists.knowledge.builder import build_knowledge_graph
from app.graph.specialists.order.builder import build_order_graph
from app.graph.specialists.refund.builder import build_refund_graph
from app.runtime.context import DemoContext, SubmitOptions
from app.runtime.model_gateway import ModelCallLimits, ModelGateway
from app.streaming.subscription import SubscriptionOwner


def route(task=TaskType.ORDER_QUERY, **updates):
    return SupervisorOutput(
        kind="route",
        decision=RouteDecision(
            **{
                "agent_type": task.target_agent,
                "task_type": task,
                "task_goal": "Find requested facts",
                **updates,
            }
        ),
    )


def clarify(task=TaskType.CLARIFICATION):
    return route(
        task,
        needs_clarification=True,
        missing_fields=["intent" if task is TaskType.CLARIFICATION else "order_id"],
        clarification_question="What do you need?"
        if task is TaskType.CLARIFICATION
        else "Which order?",
    )


class ControlledModel:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = 0
        self.messages = []

    def with_structured_output(self, schema, **kwargs):
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        self.messages.append(messages)
        output = next(self.outputs)
        if isinstance(output, BaseException):
            raise output
        if callable(output):
            output = output(messages)
            if inspect.isawaitable(output):
                output = await output
        return {
            "raw": AIMessage(
                content="controlled",
                usage_metadata={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
            ),
            "parsed": output,
            "parsing_error": None,
        }


def compiled(model, *, saver=None, specialists=None, attempts=8):
    gateway = ModelGateway(model, ModelCallLimits(attempts, 5, 0))
    graph = build_supervisor_graph(
        gateway=gateway,
        checkpointer=saver or InMemorySaver(),
        specialists=specialists
        or {
            AgentType.ORDER: build_order_graph(),
            AgentType.REFUND: build_refund_graph(),
            AgentType.KNOWLEDGE: build_knowledge_graph(),
        },
    )
    return graph


def context(*, user="dev-user", conversation="session", thread="thread", message="hello"):
    return DemoContext(
        user, conversation, thread, str(uuid4()), message, frozenset({"orders:read"})
    )


async def run_to_end(runtime, ctx, options=None):
    owner = SubscriptionOwner()
    handle = await runtime.submit(ctx, options=options or SubmitOptions(), subscription_owner=owner)
    events = [event async for event in handle.subscription]
    view = await runtime.get_run(
        user_id=ctx.user_id, conversation_id=ctx.conversation_id, run_id=handle.run_id
    )
    return handle, view, events


class MemorySessions:
    """Only a test repository. Formal lifespan always uses SessionRepository."""

    def __init__(self):
        self.bindings = {}
        self.creations = 0

    async def get_or_create(self, *, user_id, conversation_id):
        from datetime import UTC, datetime

        from app.infrastructure.sessions import SessionBinding

        key = (user_id, conversation_id)
        if key not in self.bindings:
            self.creations += 1
            self.bindings[key] = SessionBinding(
                user_id, conversation_id, uuid4(), datetime.now(UTC)
            )
        return self.bindings[key]

    async def get(self, *, user_id, conversation_id):
        return self.bindings.get((user_id, conversation_id))


def http_application(model, **runtime_options):
    from contextlib import asynccontextmanager

    from app.core.config import Settings
    from app.main import create_app
    from app.runtime.agent_runtime import AgentRuntime, RunLimits
    from app.services.agent_service import AgentService

    runtime = AgentRuntime(compiled(model), run_limits=RunLimits(10, 12), **runtime_options)
    sessions = MemorySessions()
    app = create_app(Settings(_env_file=None, app_env="test"))
    app.state.agent_service = AgentService(runtime, sessions)
    app.state.agent_runtime = runtime
    app.state.database_status = "ready"
    app.state.model_status = "initialized"

    @asynccontextmanager
    async def lifespan(application):
        try:
            yield
        finally:
            await runtime.shutdown()

    app.router.lifespan_context = lifespan
    return app, runtime, sessions
