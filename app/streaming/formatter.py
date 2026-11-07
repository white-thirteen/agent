"""Encode payloads as one JSON data field; sse-starlette frames the SSE response."""

import json
from collections.abc import AsyncIterable, AsyncIterator

from app.streaming.events import StreamEvent


def format_event(event: StreamEvent) -> dict[str, str]:
    return {
        "event": event.event,
        "data": json.dumps(event.data, ensure_ascii=False, allow_nan=False, separators=(",", ":")),
    }


async def format_events(events: AsyncIterable[StreamEvent]) -> AsyncIterator[dict[str, str]]:
    async for event in events:
        yield format_event(event)
