from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.chat import Identifier
from app.memory.models import MemoryCommand


class PreferenceIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    user_id: Identifier


class PreferenceMutation(PreferenceIdentity):
    operation_id: Identifier
    expected_revision: int = Field(ge=0, strict=True)
    command: MemoryCommand
