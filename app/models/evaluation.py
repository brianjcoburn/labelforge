from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


class EvaluationRun(Base, TimestampMixin):
    """Schema only in v0.1 — no evaluation workflow until milestone 3."""

    __tablename__ = "evaluation_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"))
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_version.id"))
    taxonomy_version_id: Mapped[int] = mapped_column(ForeignKey("taxonomy_version.id"))
    dataset_slice_description: Mapped[str | None]
    metrics_json: Mapped[dict] = mapped_column(JSON, default=dict)
