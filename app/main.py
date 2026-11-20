"""Application factory and process-scoped resources."""

import logging
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.agents.types import AgentType
from app.api.dependencies import resolve_demo_identity
from app.api.routes import agent, approvals, preferences, workflows
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
from app.infrastructure.store import store_resources
from app.knowledge.embedding import create_embeddings
from app.knowledge.models import KnowledgeError
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.reranker import BGEReranker
from app.knowledge.retriever import HybridRetriever, VectorRetriever
from app.memory.manager import MemoryManager
from app.memory.reader import MemoryReader
from app.runtime.agent_runtime import AgentRuntime, RunLimits
from app.services.agent_service import AgentService
from app.services.preference_service import PreferenceService
from app.tools.executor import ToolExecutor
from app.tools.implementations.knowledge import knowledge_tools
from app.tools.implementations.memory import read_preferences_tool, write_preferences_tool
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
            # The exit stack closes Runtime, then Store callers/pool, then model
            # resources, Saver and business pool. Register dependencies first.
            application.state.model_status = "not_configured"
            application.state.model_gateway = None
            if settings.model_configured:
                _, gateway = await resources.enter_async_context(model_resources(settings))
                application.state.model_gateway = gateway
                application.state.model_status = "initialized"
            application.state.embedding_status = "disabled"
            application.state.knowledge_status = "unavailable"
            application.state.knowledge_retriever = None
            if settings.embedding_enabled:
                embeddings = create_embeddings(settings)
                resources.push_async_callback(embeddings.aclose)
                try:
                    await embeddings.initialize()
                except KnowledgeError:
                    application.state.embedding_status = "unavailable"
                    logger.warning("Local embedding resource unavailable")
                else:
                    application.state.embedding_status = "ready"
                    if pool:
                        repository = KnowledgeRepository(pool)
                        try:
                            await repository.check_ready(embeddings.profile.key)
                            if settings.knowledge_retrieval_mode == "hybrid":
                                await repository.check_hybrid_ready()
                        except KnowledgeError:
                            application.state.knowledge_status = "unavailable"
                            logger.warning("Knowledge index unavailable or incompatible")
                        else:
                            if settings.knowledge_retrieval_mode == "hybrid":
                                reranker = BGEReranker(settings)
                                resources.push_async_callback(reranker.aclose)
                                try:
                                    await reranker.initialize()
                                except KnowledgeError:
                                    logger.warning("Local reranker resource unavailable")
                                else:
                                    application.state.knowledge_retriever = HybridRetriever(
                                        repository,
                                        embeddings,
                                        reranker,
                                        embeddings.profile.key,
                                        settings.knowledge_retrieval_timeout_seconds,
                                    )
                            else:
                                application.state.knowledge_retriever = VectorRetriever(
                                    repository, embeddings, embeddings.profile.key
                                )
                            if application.state.knowledge_retriever:
                                application.state.knowledge_status = "ready"
            application.state.store_status = "not_configured"
            application.state.memory_store = None
            if pool:
                try:
                    application.state.memory_store = await resources.enter_async_context(
                        store_resources(settings)
                    )
                except DatabaseUnavailableError:
                    application.state.store_status = "unavailable"
                    logger.warning("Store resource unavailable; run explicit setup")
                else:
                    application.state.store_status = "ready"
            application.state.memory_manager = MemoryManager(
                application.state.memory_store, user_ids=settings.demo_user_ids
            )
            application.state.memory_reader = MemoryReader(application.state.memory_manager)
            preference_registry = ToolRegistry()
            preference_registry.register(
                read_preferences_tool(
                    application.state.memory_reader,
                    enabled=application.state.memory_store is not None,
                )
            )
            preference_registry.register(
                write_preferences_tool(
                    application.state.memory_manager,
                    enabled=application.state.memory_store is not None,
                )
            )
            preference_registry.freeze()
            application.state.preference_service = (
                PreferenceService(
                    pool,
                    ToolExecutor(preference_registry, ToolPolicy()),
                    user_ids=settings.demo_user_ids,
                )
                if pool
                else None
            )
            await initialize_graph_and_service(application, resources)
            yield
        logger.info("Application stopped")

    async def initialize_graph_and_service(application: FastAPI, resources: AsyncExitStack):
        graph = None
        gateway = application.state.model_gateway
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
            for definition in knowledge_tools(
                application.state.knowledge_retriever,
                mode=settings.knowledge_retrieval_mode,
                retrieval_timeout=settings.knowledge_retrieval_timeout_seconds,
            ):
                registry.register(definition)
            registry.register(
                read_preferences_tool(
                    application.state.memory_reader,
                    enabled=application.state.memory_store is not None,
                )
            )
            registry.register(
                write_preferences_tool(
                    application.state.memory_manager,
                    enabled=application.state.memory_store is not None,
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
                    AgentType.KNOWLEDGE: build_knowledge_graph(
                        gateway=gateway,
                        registry=registry,
                        executor=executor,
                        profile=application.state.knowledge_retriever.profile
                        if application.state.knowledge_retriever
                        else None,
                        mode=settings.knowledge_retrieval_mode,
                        retrieval_profile=getattr(
                            application.state.knowledge_retriever, "retrieval_profile", None
                        ),
                    ),
                },
            )
        elif not settings.model_configured:
            logger.info("Agent graph not initialized; model configuration is incomplete")
        gate_graph = graph
        if gate_graph is None and application.state.checkpoint_pool:
            # State inspection does not require a configured model or an executable graph.
            gate_graph = build_supervisor_graph(
                gateway=None,
                checkpointer=AsyncPostgresSaver(
                    application.state.checkpoint_pool, serde=checkpoint_serializer()
                ),
                specialists={
                    AgentType.ORDER: build_order_graph(gateway=None, registry=None, executor=None),
                    AgentType.REFUND: build_refund_graph(
                        gateway=None,
                        registry=None,
                        executor=None,
                        approval_service=None,
                        refund_service=None,
                    ),
                    AgentType.KNOWLEDGE: build_knowledge_graph(),
                },
            )
        if gate_graph is None or not await legacy_memory_cutover_safe(
            gate_graph, application.state.pool
        ):
            logger.warning("Legacy preference cutover gate unavailable or not safe")
            graph = None
            application.state.preference_service = None
        from app.context.archive_store import ArchiveStore
        from app.context.manager import ContextManager
        from app.context.repository import ContextRepository

        context_manager = (
            ContextManager(
                ContextRepository(application.state.pool),
                ArchiveStore(settings.context_archive_root),
            )
            if application.state.pool
            else None
        )
        runtime = AgentRuntime(
            graph,
            context_manager=context_manager,
            context_read_bytes=settings.context_archive_read_bytes,
            context_settings=settings,
            context_gateway=gateway,
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
        if runtime._maintenance:
            await runtime._maintenance.resume_pending()
        application.state.agent_service = AgentService(runtime, application.state.sessions)
        logger.info(
            "Application started; preparation_ready=%s",
            settings.app_env in ("development", "test")
            and application.state.agent_service.is_ready,
        )

    application = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
    application.state.settings = settings
    application.include_router(agent.router)
    application.include_router(preferences.router)
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
            "embedding_status": request.app.state.embedding_status,
            "knowledge_ready": request.app.state.knowledge_retriever is not None,
            "knowledge_status": request.app.state.knowledge_status,
            "checkpoint_status": request.app.state.checkpoint_status,
            "checkpoint_backend": "postgres",
            "store_status": request.app.state.store_status,
        }

    return application


app = create_app()


async def legacy_memory_cutover_safe(graph, pool):
    """Require every bound legacy Memory task to be terminal and fully settled."""
    from app.agents.types import TaskType
    from app.runtime.models import TaskStatus

    async with pool.connection() as connection:
        rows = await (
            await connection.execute("SELECT user_id,conversation_id,thread_id FROM sessions")
        ).fetchall()
    for user_id, conversation_id, thread_id in rows:
        # Inspect the latest snapshot of each task, not only the latest task on
        # the thread: a subsequent task does not settle an unknown old write.
        seen = set()
        async for snapshot in graph.aget_state_history(
            {"configurable": {"thread_id": str(thread_id)}}
        ):
            values = snapshot.values
            if not values:
                continue
            # The initial input checkpoint precedes all identity channels. It is
            # safe to skip only after a later checkpoint identified the task.
            if (
                seen
                and set(values) == {"messages"}
                and snapshot.metadata.get("source") == "input"
                and snapshot.metadata.get("step") == -1
            ):
                continue
            if (values.get("user_id"), values.get("conversation_id")) != (user_id, conversation_id):
                return False
            task_id = values.get("task_id")
            if not task_id:
                return False
            if task_id in seen:
                continue
            seen.add(task_id)
            pending = values.get("pending_task")
            pending_type = (
                pending.get("task_type")
                if isinstance(pending, dict)
                else getattr(pending, "task_type", None)
            )
            if pending_type == TaskType.MEMORY_MANAGE:
                return False
            if values.get("task_type") is None and (
                snapshot.next
                or values.get("task_status") in (TaskStatus.RUNNING, TaskStatus.FAILED)
            ):
                return False
            if values.get("task_type") == TaskType.MEMORY_MANAGE and (
                snapshot.next
                or pending is not None
                or values.get("task_status") not in (TaskStatus.COMPLETED, TaskStatus.REJECTED)
            ):
                return False
    return True
