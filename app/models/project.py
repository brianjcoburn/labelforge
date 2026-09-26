from sqlalchemy import Boolean, Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import (
    AnnotationMode,
    ClassificationType,
    DataType,
    LLMProviderType,
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
    # Turns on the full trust-driven loop: automatic bootstrap/scheduled
    # retraining, comparison-gated auto-activation, and auto-labeling of
    # agreeing high-trust predictions (with audit sampling). Off by default —
    # existing and new projects opt in explicitly rather than this silently
    # starting to train models and auto-label records on its own. When off,
    # everything still works exactly as milestone 1-3 did: manual Train Now,
    # manual Activate, every record shown to a human.
    automation_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Which LLM backs AI predictions for this project. LOCAL with no model_id
    # selected yet (the default) means AI features are simply unavailable —
    # same as ANTHROPIC with no API key configured — never an error state.
    llm_provider: Mapped[LLMProviderType] = mapped_column(
        Enum(LLMProviderType), default=LLMProviderType.LOCAL
    )
    local_model_id: Mapped[str | None] = mapped_column(default=None)  # catalog id
