"""Shared Reader delegates ownership, validation and projection to MemoryManager."""

from app.memory.manager import MemoryManager, PreferenceSnapshot


class MemoryReader:
    def __init__(self, manager: MemoryManager):
        self.manager = manager

    async def read_preferences(self, *, user_id: str) -> PreferenceSnapshot:
        return await self.manager.snapshot(user_id=user_id)
