"""Validated development chat input; production identity comes from the backend."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Identifier = Annotated[str, Field(min_length=1, max_length=128)]


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_id: Identifier
    conversation_id: Identifier
    workflow_id: Identifier
    message: str = Field(min_length=1, max_length=32000)
