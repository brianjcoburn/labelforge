from sqlalchemy import Enum, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import (
    AnnotationMode,
    ClassificationType,
    DataType,
    SamplingStrategyType,
    TrainingStrategyType,
)


class Project(Base, TimestampMixin):
    __tablename__ = "project"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    description: Mapped[str | None] = mapped_column(Text)
    classification_type: Mapped[ClassificationType] = mapped_column(
        Enum(ClassificationType)
    )
    data_type: Mapped[DataType] = mapped_column(Enum(DataType), default=DataType.TEXT)


class ProjectSettings(Base, TimestampMixin):
    __tablename__ = "project_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), unique=True)
    annotation_mode: Mapped[AnnotationMode] = mapped_column(
        Enum(AnnotationMode), default=AnnotationMode.ON_DEMAND
    )
    training_strategy: Mapped[TrainingStrategyType] = mapped_column(
        Enum(TrainingStrategyType), default=TrainingStrategyType.MANUAL
    )
    sampling_strategy: Mapped[SamplingStrategyType] = mapped_column(
        Enum(SamplingStrategyType), default=SamplingStrategyType.RANDOM
    )
    batch_training_threshold: Mapped[int] = mapped_column(Integer, default=100)
