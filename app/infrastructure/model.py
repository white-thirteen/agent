"""Application-owned HTTP clients and one shared OpenAI-compatible model/gateway."""

from contextlib import asynccontextmanager

import httpx
from langchain_openai import ChatOpenAI

from app.core.config import Settings
from app.runtime.model_gateway import ModelCallLimits, ModelGateway


@asynccontextmanager
async def model_resources(settings: Settings):
    # Both transports are ours. SDK retries are disabled so every attempt is counted.
    with httpx.Client(timeout=settings.model_timeout_seconds) as sync_client:
        async with httpx.AsyncClient(timeout=settings.model_timeout_seconds) as async_client:
            model = ChatOpenAI(
                model=settings.model_name,
                api_key=settings.model_api_key.get_secret_value(),
                base_url=settings.model_base_url,
                timeout=settings.model_timeout_seconds,
                max_retries=0,
                # Current provider requires non-thinking for forced structured tool choice.
                reasoning_effort="none",
                http_client=sync_client,
                http_async_client=async_client,
            )
            gateway = ModelGateway(
                model,
                ModelCallLimits(
                    max_attempts=settings.model_max_attempts,
                    timeout_seconds=settings.model_timeout_seconds,
                    max_retries=settings.model_max_retries,
                ),
            )
            yield model, gateway
