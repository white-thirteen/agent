"""Public SSE event envelope; individual payload schemas will evolve with the graph."""

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

EventType = Literal["token", "status", "done", "error"]


class StreamEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: EventType
    data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    kind: EventType
    run_id: str
    task_id: str
    sequence: int
    data: dict

    def public_event(self) -> StreamEvent:
        fields = {
            "status": {"run_status", "task_status", "code", "snapshot", "view"},
            "token": {"content"},
            "error": {"code", "message", "usage_complete"},
            "done": {"run_status", "task_status"},
        }
        return StreamEvent(
            event=self.kind,
            data={
                **{key: value for key, value in self.data.items() if key in fields[self.kind]},
                "run_id": self.run_id,
                "task_id": self.task_id,
                "workflow_id": self.task_id,
                "sequence": self.sequence,
            },
        )
