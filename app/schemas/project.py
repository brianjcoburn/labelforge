from pydantic import BaseModel, ConfigDict

from app.models.enums import (
    AnnotationMode,
    ClassificationType,
    DataType,
    SamplingStrategyType,
    TrainingStrategyType,
)


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    classification_type: ClassificationType
    data_type: DataType = DataType.TEXT


class ProjectSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    annotation_mode: AnnotationMode
    training_strategy: TrainingStrategyType
    sampling_strategy: SamplingStrategyType
    batch_training_threshold: int


class ProjectSettingsUpdate(BaseModel):
    annotation_mode: AnnotationMode | None = None
    training_strategy: TrainingStrategyType | None = None
    sampling_strategy: SamplingStrategyType | None = None
    batch_training_threshold: int | None = None


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
