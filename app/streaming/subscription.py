"""Single bounded subscription ownership; closing never owns execution cancellation."""

import asyncio
from collections.abc import Callable
from uuid import uuid4

from app.streaming.events import RuntimeEvent


class EventSubscription:
    def __init__(self, capacity: int, detach: Callable[[str], None]):
        self.subscription_id = str(uuid4())
        self._queue: asyncio.Queue[RuntimeEvent | None] = asyncio.Queue(capacity)
        self._detach = detach
        self.closed = False
        self.slow = False

    def publish(self, event: RuntimeEvent) -> None:
        if self.closed:
            return
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            self.slow = True
            self.close()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self._detach(self.subscription_id)
        while not self._queue.empty():
            self._queue.get_nowait()
        self._queue.put_nowait(None)

    async def __aiter__(self):
        try:
            while True:
                event = await self._queue.get()
                if event is None:
                    return
                yield event
                if event.kind == "done":
                    return
        finally:
            self.close()


class SubscriptionOwner:
    def __init__(self):
        self._subscription: EventSubscription | None = None
        self.closed = False

    def adopt(self, subscription: EventSubscription) -> None:
        if self.closed or self._subscription is not None:
            subscription.close()
            raise RuntimeError("Subscription owner is unavailable")
        self._subscription = subscription

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            if self._subscription is not None:
                self._subscription.close()
