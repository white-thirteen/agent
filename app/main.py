"""Application factory and process-scoped resources."""

import logging
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import agent, workflows
from app.core.config import Settings
from app.core.errors import PublicError
from app.core.logging import configure_logging
from app.graph.builder import build_supervisor_graph
from app.infrastructure.model import model_resources
from app.infrastructure.postgres import DatabaseUnavailableError, open_pool
from app.infrastructure.sessions import SessionRepository
from app.runtime.agent_runtime import AgentRuntime
from app.services.agent_service import AgentService

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
            graph = build_supervisor_graph(model)
            application.state.model_status = "initialized"
        else:
            logger.info("Agent graph not initialized; model configuration is incomplete")
        runtime = AgentRuntime(graph)
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

    @application.exception_handler(PublicError)
    async def public_error_handler(request: Request, exc: PublicError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
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
        }

    return application


app = create_app()
