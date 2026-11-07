"""Application factory and process-scoped resources."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import agent, workflows
from app.core.config import Settings
from app.core.errors import AgentNotReadyError
from app.core.logging import configure_logging
from app.runtime.agent_runtime import AgentRuntime
from app.services.agent_service import AgentService

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an application without opening database or model connections."""
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        configure_logging(settings.log_level)
        runtime = AgentRuntime()
        application.state.agent_service = AgentService(runtime)
        logger.info("Application started; agent_ready=%s", runtime.is_ready)
        try:
            yield
        finally:
            logger.info("Application stopped")

    application = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
    application.state.settings = settings
    application.include_router(agent.router)
    application.include_router(workflows.router)

    @application.exception_handler(AgentNotReadyError)
    async def agent_not_ready_handler(request: Request, exc: AgentNotReadyError):
        return JSONResponse(
            status_code=503,
            content={"error": {"code": "agent_not_ready", "message": str(exc)}},
        )

    @application.get("/health", tags=["health"])
    async def health(request: Request) -> dict[str, str | bool]:
        return {
            "status": "ok",
            "service": settings.app_name,
            "agent_ready": request.app.state.agent_service.is_ready,
        }

    return application


app = create_app()
