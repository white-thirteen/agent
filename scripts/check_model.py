"""Explicit paid provider checks using fixed non-private text and RouteDecision."""

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from app.agents.types import AgentType
from app.core.config import Settings
from app.core.logging import configure_logging
from app.graph.contracts import RouteDecision
from app.infrastructure.model import model_resources
from app.runtime.model_gateway import (
    STRUCTURED_METHOD,
    ModelCallContext,
    ModelCallError,
    ModelCallUsage,
)


async def main() -> int:
    configure_logging("WARNING")
    try:
        settings = Settings()
    except ValidationError:
        print("Model check failed. Invalid settings.")
        return 1
    if not settings.model_configured:
        print("Model check failed. Model configuration incomplete.")
        return 1
    failures = 0
    async with model_resources(settings) as (_, gateway):
        # These are fixed diagnostic correlation labels, unrelated to formal business Tasks.
        context = ModelCallContext("diagnostic-run", "diagnostic-check", AgentType.SUPERVISOR)
        usage = ModelCallUsage()
        for capability in ("text", "structured"):
            try:
                if capability == "text":
                    result = await gateway.invoke(
                        [HumanMessage(content="Reply with the single word READY.")],
                        context=context,
                        model_usage=usage,
                    )
                    if not result.message.content:
                        print("text failed (empty response)")
                        failures += 1
                        usage = result.model_usage
                        continue
                else:
                    result = await gateway.invoke_structured(
                        [
                            SystemMessage(
                                content=(
                                    "Classify the request with the supplied schema. "
                                    "For an unknown intent, "
                                    "use task_type=clarification and agent_type=supervisor, "
                                    "needs_clarification=true, missing_fields=['intent'], "
                                    "clarification_question='How can I help?', "
                                    "task_goal='Clarify intent'."
                                )
                            ),
                            HumanMessage(content="Hello."),
                        ],
                        schema=RouteDecision,
                        context=context,
                        model_usage=usage,
                    )
                usage = result.model_usage
                method = STRUCTURED_METHOD if capability == "structured" else "chat"
                print(
                    f"{capability} passed model={settings.model_name} "
                    f"adapter=ChatOpenAI method={method} reasoning_effort=none "
                    f"usage={result.usage.status} attempts={usage.model_attempts}"
                )
            except ModelCallError as error:
                failures += 1
                usage = error.model_usage
                print(f"{capability} failed code={error.code} attempts={usage.model_attempts}")
    logging.shutdown()
    return 1 if failures else 0


if __name__ == "__main__":
    from scripts import run_async

    raise SystemExit(run_async(main()))
