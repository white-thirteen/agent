"""Enter a controlled Gateway call after persisting its maintenance reservation."""

import asyncio
import os
import re
import time

from langchain_core.messages import HumanMessage
from psycopg.conninfo import conninfo_to_dict
from psycopg_pool import AsyncConnectionPool

from app.context.manager import _ClaimBudget
from app.context.repository import ContextRepository
from app.runtime.model_gateway import (
    MaintenanceCallContext,
    ModelCallLimits,
    ModelCallUsage,
    ModelGateway,
)
from scripts import run_async


class PausedModel:
    def bind(self, **kwargs):
        return self

    async def ainvoke(self, messages):
        print("controlled-call-started", flush=True)
        await asyncio.Event().wait()


async def main():
    dsn = os.environ["CONTEXT_ARCHIVE_TEST_DSN"]
    parts = conninfo_to_dict(dsn)
    assert (parts.get("host"), parts.get("port")) == ("127.0.0.1", "56422")
    schema = os.environ["CTX221_TEST_SCHEMA"]
    assert re.fullmatch(r"ctx221_[0-9a-f]{32}", schema)
    async with AsyncConnectionPool(dsn, kwargs={"options": f"-csearch_path={schema}"}) as pool:
        repo = ContextRepository(pool)
        claim = await repo.claim_maintenance("killed")
        await ModelGateway(PausedModel(), ModelCallLimits(2, 25, 0)).invoke(
            [HumanMessage(content="controlled call")],
            context=MaintenanceCallContext(
                maintenance_id="killed",
                budget=_ClaimBudget(repo, claim),
                deadline_monotonic=time.monotonic() + 25,
                max_output_tokens=128,
            ),
            model_usage=ModelCallUsage(),
        )


if __name__ == "__main__":
    run_async(main())
