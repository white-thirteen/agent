"""Real configured provider probe; prints status and usage only, no credentials/content."""

import asyncio
import json

from langchain_core.messages import HumanMessage
from langchain_core.messages.utils import count_tokens_approximately

from app.agents.types import AgentType
from app.context.compaction import summarize_messages
from app.core.config import Settings
from app.infrastructure.model import model_resources
from app.runtime.model_gateway import ModelCallContext, ModelCallUsage


async def main():
    settings = Settings()
    if not settings.model_configured:
        print(json.dumps({"status": "not_configured"}))
        return
    try:
        async with model_resources(settings) as (_, gateway):
            summary, usage, reports = await summarize_messages(
                [HumanMessage(content="The user wants a concise answer.", id="probe-1")],
                running_summary=None,
                gateway=gateway,
                context=ModelCallContext("probe-run", "probe-task", AgentType.SUPERVISOR),
                model_usage=ModelCallUsage(),
                token_counter=count_tokens_approximately,
                max_input_tokens=4096,
                max_output_tokens=128,
            )
        print(
            json.dumps(
                {
                    "status": "ok",
                    "ids": sorted(summary.summarized_message_ids),
                    "attempts": usage.model_attempts,
                    "usage_status": reports[0].status,
                    "input_tokens": reports[0].input_tokens,
                    "output_tokens": reports[0].output_tokens,
                }
            )
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "code": getattr(exc, "code", None),
                }
            )
        )


asyncio.run(main())
