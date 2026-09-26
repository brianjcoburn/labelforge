from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import ModelState, TrainingRunStatus, TrainingTrigger


class ModelVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_number: int
    classifier_type: str
    state: ModelState
    metrics_json: dict | None
    activated_at: datetime | None
    deactivated_at: datetime | None
    created_at: datetime


class TrainingRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trigger: TrainingTrigger
    trigger_reason: str
    status: TrainingRunStatus
    annotation_count_snapshot: int
    started_at: datetime | None
    completed_at: datetime | None
    resulting_model_version_id: int | None
    error_message: str | None
