from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PromptDraftOut(BaseModel):
    template_text: str


class PromptVersionCreate(BaseModel):
    template_text: str


class PromptVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_number: int
    template_text: str
    provider: str
    model_name: str
    is_active: bool
    created_at: datetime


class PromptTestRequest(BaseModel):
    record_id: int
    template_text: str | None = None
    version_id: int | None = None


class PromptTestOut(BaseModel):
    predicted_label_ids: list[int]
    predicted_label_names: list[str]
    raw_response: str
