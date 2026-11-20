"""Application-owned HTTP clients and one shared OpenAI-compatible model/gateway."""

from contextlib import asynccontextmanager
from urllib.parse import urlsplit

import httpx
from langchain_openai import ChatOpenAI

from app.core.config import Settings
from app.runtime.model_gateway import ModelCallLimits, ModelGateway


class DeepSeekChatOpenAI(ChatOpenAI):
    """DeepSeek Chat Completions requires max_tokens on the wire."""

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        if "max_completion_tokens" in payload:
            payload["max_tokens"] = payload.pop("max_completion_tokens")
        return payload


@asynccontextmanager
async def model_resources(settings: Settings):
    # Both transports are ours. SDK retries are disabled so every attempt is counted.
    with httpx.Client(timeout=settings.model_timeout_seconds) as sync_client:
        async with httpx.AsyncClient(timeout=settings.model_timeout_seconds) as async_client:
            model_class = (
                DeepSeekChatOpenAI
                if urlsplit(settings.model_base_url or "").hostname == "api.deepseek.com"
                else ChatOpenAI
            )
            model = model_class(
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
                context_window=settings.context_model_window_tokens,
                output_reserve=settings.context_model_output_tokens,
            )
            yield model, gateway
