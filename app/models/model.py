from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import ModelState, TrainingRunStatus, TrainingStrategyType


class ModelVersion(Base, TimestampMixin):
    """Schema only in v0.1 — no training workflow until milestone 3.

    Immutable once created; state transitions (ACTIVE / INACTIVE /
    INVALID_FOR_CURRENT_TAXONOMY) are the only thing that changes.
    """

    __tablename__ = "model_version"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"))
    taxonomy_version_id: Mapped[int] = mapped_column(ForeignKey("taxonomy_version.id"))
    version_number: Mapped[int]
    classifier_type: Mapped[str]
    state: Mapped[ModelState] = mapped_column(default=ModelState.INACTIVE)
    artifact_path: Mapped[str | None]
    metrics_json: Mapped[dict | None] = mapped_column(JSON)
    activated_at: Mapped[datetime | None]
    deactivated_at: Mapped[datetime | None]


class TrainingRun(Base, TimestampMixin):
    """Schema only in v0.1 — no concrete training strategy implementation yet."""

    __tablename__ = "training_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"))
    taxonomy_version_id: Mapped[int] = mapped_column(ForeignKey("taxonomy_version.id"))
    training_strategy: Mapped[TrainingStrategyType]
    trigger_reason: Mapped[str] = mapped_column(Text)
    status: Mapped[TrainingRunStatus]
    annotation_count_snapshot: Mapped[int]
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    error_message: Mapped[str | None] = mapped_column(Text)
    resulting_model_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_version.id")
    )
