from pydantic import BaseModel, ConfigDict

from app.models.enums import (
    AnnotationMode,
    ClassificationType,
    DataType,
    LLMProviderType,
)


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    classification_type: ClassificationType
    data_type: DataType = DataType.TEXT


class ProjectSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    annotation_mode: AnnotationMode
    automation_enabled: bool
    llm_provider: LLMProviderType
    local_model_id: str | None


class ProjectSettingsUpdate(BaseModel):
    annotation_mode: AnnotationMode | None = None
    automation_enabled: bool | None = None
    llm_provider: LLMProviderType | None = None
    local_model_id: str | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    classification_type: ClassificationType
    data_type: DataType


class ProjectDetailOut(ProjectOut):
    settings: ProjectSettingsOut
    has_taxonomy: bool
    dataset_count: int
    record_count: int
    annotated_count: int
