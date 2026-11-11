"""SSE request owner covers endpoint, response construction and the full ASGI call."""

from fastapi.routing import APIRoute
from sse_starlette.sse import EventSourceResponse

from app.streaming.subscription import SubscriptionOwner


class SubscriptionRoute(APIRoute):
    async def handle(self, scope, receive, send):
        if self.response_class is not EventSourceResponse:
            return await super().handle(scope, receive, send)
        owner = SubscriptionOwner()
        scope.setdefault("state", {})["subscription_owner"] = owner
        try:
            await super().handle(scope, receive, send)
        finally:
            # Wrap handle, including FastAPI's effective included-router context.
            owner.close()
