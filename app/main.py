"""Application factory and process-scoped resources."""

import logging
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.agents.types import AgentType
from app.api.dependencies import resolve_demo_identity
from app.api.routes import agent, approvals, workflows
from app.core.config import Settings
from app.core.errors import PublicError
from app.core.logging import configure_logging
from app.domain.orders import MockOrderService, OrderRepository
from app.domain.refunds import MockRefundService
from app.graph.builder import build_supervisor_graph
from app.graph.specialists.knowledge.builder import build_knowledge_graph
from app.graph.specialists.order.builder import build_order_graph
from app.graph.specialists.refund.builder import build_refund_graph
from app.infrastructure.checkpoint import checkpoint_serializer, open_checkpoint_pool
from app.infrastructure.model import model_resources
from app.infrastructure.postgres import DatabaseUnavailableError, open_pool
from app.infrastructure.sessions import SessionRepository
from app.runtime.agent_runtime import AgentRuntime, RunLimits
from app.services.agent_service import AgentService
from app.tools.executor import ToolExecutor
from app.tools.implementations.orders import order_tools
from app.tools.implementations.refunds import refund_node_tools, refund_order_tool
from app.tools.policy import ToolPolicy
from app.tools.registry import ToolRegistry
from app.workflows.approvals import ApprovalService, LocalDemoApprovalActor

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an application; process-scoped model and graph start in lifespan."""
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        configure_logging(settings.log_level)
        async with AsyncExitStack() as resources:
            pool = None
            application.state.database_status = "not_configured"
            if settings.database_url:
                try:
                    pool = await open_pool(settings)
                except DatabaseUnavailableError:
                    application.state.database_status = "unavailable"
                    logger.warning("Database resource unavailable; check connection and migrations")
                else:
                    resources.push_async_callback(pool.close)
                    application.state.database_status = "ready"
            application.state.pool = pool
            application.state.sessions = SessionRepository(pool) if pool else None
            application.state.approval_service = ApprovalService(pool) if pool else None
            application.state.refund_service = MockRefundService(pool) if pool else None
            if settings.app_env in ("development", "test"):
                application.state.approval_actor_provider = LocalDemoApprovalActor()
            application.state.checkpoint_status = "not_configured"
            application.state.checkpoint_pool = None
            if pool:
                try:
                    checkpoint_pool = await open_checkpoint_pool(settings)
                except DatabaseUnavailableError:
                    application.state.checkpoint_status = "unavailable"
                    logger.warning("Checkpoint resource unavailable; run explicit setup")
                else:
                    application.state.checkpoint_pool = checkpoint_pool
                    application.state.checkpoint_status = "ready"
                    resources.push_async_callback(checkpoint_pool.close)
            await initialize_model_and_service(application, resources)
            try:
                yield
            finally:
                logger.info("Application stopped")

    async def initialize_model_and_service(application: FastAPI, resources: AsyncExitStack):
        graph = None
        application.state.model_status = "not_configured"
        application.state.model_gateway = None
        if settings.model_configured:
            model, gateway = await resources.enter_async_context(model_resources(settings))
            application.state.model_gateway = gateway
            application.state.model_status = "initialized"
        if settings.model_configured and application.state.checkpoint_pool:
            registry = ToolRegistry()
            service = MockOrderService(OrderRepository(application.state.pool))
            for definition in order_tools(
                service,
                timeout_seconds=settings.tool_timeout_seconds,
                max_retries=settings.tool_read_max_retries,
            ):
                registry.register(definition)
            for definition in refund_node_tools(
                application.state.refund_service,
                application.state.approval_service,
                timeout_seconds=settings.tool_timeout_seconds,
            ):
                registry.register(definition)
            registry.register(
                refund_order_tool(
                    application.state.refund_service, timeout_seconds=settings.tool_timeout_seconds
                )
            )
            registry.freeze()
            executor = ToolExecutor(
                registry,
                ToolPolicy(),
                max_calls_per_message=settings.tool_max_calls_per_message,
                approval_service=application.state.approval_service,
            )
            application.state.tool_registry = registry
            graph = build_supervisor_graph(
                gateway=gateway,
                checkpointer=AsyncPostgresSaver(
                    application.state.checkpoint_pool, serde=checkpoint_serializer()
                ),
                specialists={
                    AgentType.ORDER: build_order_graph(
                        gateway=gateway, registry=registry, executor=executor
                    ),
                    AgentType.REFUND: build_refund_graph(
                        gateway=gateway,
                        registry=registry,
                        executor=executor,
                        approval_service=application.state.approval_service,
                        refund_service=application.state.refund_service,
                    ),
                    AgentType.KNOWLEDGE: build_knowledge_graph(),
                },
            )
        elif not settings.model_configured:
            logger.info("Agent graph not initialized; model configuration is incomplete")
        runtime = AgentRuntime(
            graph,
            run_limits=RunLimits(settings.run_timeout_seconds, settings.run_max_tool_calls),
            queue_capacity=settings.runtime_queue_capacity,
            max_active_runs=settings.runtime_max_active_runs,
            retained_runs=settings.runtime_retained_runs,
            result_ttl_seconds=settings.runtime_result_ttl_seconds,
            shutdown_grace_seconds=settings.runtime_shutdown_grace_seconds,
            approval_service=(
                application.state.approval_service
                if settings.app_env in ("development", "test")
                else None
            ),
            refund_service=application.state.refund_service,
            scope_resolver=lambda user_id: (
                resolve_demo_identity(user_id=user_id, settings=settings).permission_scopes
            ),
        )
        application.state.agent_runtime = runtime
        resources.push_async_callback(runtime.shutdown)
        application.state.agent_service = AgentService(runtime, application.state.sessions)
        logger.info(
            "Application started; preparation_ready=%s",
            settings.app_env in ("development", "test")
            and application.state.agent_service.is_ready,
        )

    application = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
    application.state.settings = settings
    application.include_router(agent.router)
    application.include_router(workflows.router)
    if settings.app_env in ("development", "test"):
        application.include_router(approvals.router)

    @application.exception_handler(PublicError)
    async def public_error_handler(request: Request, exc: PublicError):
        error = {"code": exc.code, "message": exc.message}
        if getattr(exc, "status_url", None):
            error["status_url"] = exc.status_url
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": error},
        )

    @application.get("/health", tags=["health"])
    async def health(request: Request) -> dict[str, str | bool]:
        return {
            "status": "ok",
            "service": settings.app_name,
            "agent_ready": (
                settings.app_env in ("development", "test")
                and request.app.state.agent_service.is_ready
            ),
            "database_status": request.app.state.database_status,
            "model_status": request.app.state.model_status,
            "checkpoint_backend": "postgres",
        }

    return application


app = create_app()
