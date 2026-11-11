"""Validated development chat input; production identity comes from the backend."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# PostgreSQL text cannot store NUL, so reject it before session preparation.
Identifier = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[^\x00]+$")]


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_id: Identifier
    conversation_id: Identifier
    message: str = Field(min_length=1, max_length=32000)
    input_mode: Literal["auto", "new_task"] = "auto"
    request_id: UUID | None = None


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_id: Identifier
    conversation_id: Identifier
