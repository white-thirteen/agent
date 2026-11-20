"""One real structured Supervisor call; capture only sanitized parser metadata."""

import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402

from app.agents.prompts.supervisor import SUPERVISOR_SYSTEM_PROMPT  # noqa: E402
from app.agents.types import AgentType  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.graph.contracts import NewSupervisorOutput  # noqa: E402
from app.infrastructure.model import model_resources  # noqa: E402
from app.runtime.model_gateway import ModelCallContext, ModelCallError, ModelCallUsage  # noqa: E402


def shape(value):
    if isinstance(value, dict):
        return {str(key): shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [shape(item) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str) and value in {
        "route",
        "unsupported",
        "ORDER_QUERY",
        "REFUND_APPLY",
        "KNOWLEDGE_QA",
        "CLARIFICATION",
        "supervisor",
        "order",
        "refund",
        "knowledge",
    }:
        return value
    return "<redacted-string>"


async def main():
    output = ROOT / "docs/integration/2026-11-20/project-http-it001-diagnostic.json"
    assert not output.exists()
    settings = Settings().model_copy(
        update={
            "model_max_retries": 0,
            "context_model_window_tokens": 16384,
            "context_model_output_tokens": 512,
        }
    )
    assert settings.model_configured
    report = {
        "type": "single Supervisor Gateway diagnostic, no prior HTTP state",
        "gateway_attempt_limit": 1,
        "reproduces_prior_http_context": False,
        "raw": None,
        "gateway": None,
    }
    async with model_resources(settings) as (_, gateway):
        original_call = gateway._call_recorded

        async def observing_call(runnable, messages, **kwargs):
            class Observer:
                async def ainvoke(self, *args, **kw):
                    response = await runnable.ainvoke(*args, **kw)
                    raw = response.get("raw")
                    error = response.get("parsing_error")
                    details = []
                    if error and callable(getattr(error, "errors", None)):
                        details = [
                            {"loc": list(x.get("loc", ())), "type": x.get("type")}
                            for x in error.errors()
                        ]
                    report["raw"] = {
                        "parsed_type": type(response.get("parsed")).__name__,
                        "tool_calls": shape(getattr(raw, "tool_calls", [])),
                        "invalid_tool_calls": shape(getattr(raw, "invalid_tool_calls", [])),
                        "finish_reason": getattr(raw, "response_metadata", {}).get("finish_reason"),
                        "usage": getattr(raw, "usage_metadata", None),
                        "parsing_error_type": type(error).__name__ if error else None,
                        "validation_errors": details,
                    }
                    return response

            return await original_call(Observer(), messages, **kwargs)

        gateway._call_recorded = observing_call
        try:
            result = await gateway.invoke_structured(
                [
                    SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT),
                    HumanMessage(content="请简要说明你能处理什么问题。"),
                ],
                schema=NewSupervisorOutput,
                context=ModelCallContext(
                    "it001-run", "it001-task", AgentType.SUPERVISOR, max_call_attempts=1
                ),
                model_usage=ModelCallUsage(),
            )
            report["gateway"] = {
                "status": "success",
                "usage": asdict(result.usage),
                "model_usage": asdict(result.model_usage),
                "parsed": shape(result.parsed.model_dump(mode="json")),
            }
        except ModelCallError as error:
            report["gateway"] = {
                "status": "error",
                "code": error.code,
                "usage": asdict(error.usage),
                "model_usage": asdict(error.model_usage),
            }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True))


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
