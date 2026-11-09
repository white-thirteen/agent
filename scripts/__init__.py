"""Explicit local commands, invoked with python -m."""

import asyncio
import sys


def run_async(coroutine):
    """psycopg requires a selector loop on Windows, scoped to the script runner."""
    if sys.platform == "win32":
        from asyncio import SelectorEventLoop

        with asyncio.Runner(loop_factory=SelectorEventLoop) as runner:
            return runner.run(coroutine)
    return asyncio.run(coroutine)
