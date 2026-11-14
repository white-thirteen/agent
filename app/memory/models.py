"""Finite explicit commands and safe durable mutation results."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from app.memory.manager import PREFERENCE_VALUES


class MemoryCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    operation: Literal["read", "upsert", "delete", "clear"]
    field: Literal["answer_language", "answer_style"] | None = None
    value: Literal["zh-CN", "en", "concise", "detailed"] | None = None

    @model_validator(mode="after")
    def combination(self):
        if self.operation == "upsert":
            valid = self.field in PREFERENCE_VALUES and self.value in PREFERENCE_VALUES[self.field]
        elif self.operation == "delete":
            valid = self.field is not None and self.value is None
        else:
            valid = self.field is None and self.value is None
        if not valid:
            raise ValueError("Invalid preference command combination")
        return self


class MemoryMutationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    status: Literal["applied", "reused", "conflict", "unknown"]
    operation_id: str
    revision: int | None
    changed_fields: list[Literal["answer_language", "answer_style"]]
    preferences: dict[str, str] | None
