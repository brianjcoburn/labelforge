from sqlalchemy import JSON, Boolean, Column, ForeignKey, Table, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import SuggestionSource


class PromptVersion(Base, TimestampMixin):
    """Schema only in v0.1 — no prompt-generation workflow until milestone 2."""

    __tablename__ = "prompt_version"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"))
    version_number: Mapped[int]
    template_text: Mapped[str] = mapped_column(Text)
    provider: Mapped[str]
    model_name: Mapped[str]
    parameters_json: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str]


class LabelSuggestion(Base, TimestampMixin):
    """A non-authoritative label shown alongside a record.

    Distinguished from ground truth (Annotation/AnnotationRevision) by design:
    a suggestion is never treated as human-confirmed, regardless of its source.
    `source` distinguishes where it came from:
      - IMPORTED: dataset's existing label column at import time (prompt/model ids null)
      - LLM / CLASSIFIER: generated later (milestones 2/3)
    """

    __tablename__ = "label_suggestion"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(ForeignKey("record.id"))
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"))
    taxonomy_version_id: Mapped[int] = mapped_column(ForeignKey("taxonomy_version.id"))
    prompt_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("prompt_version.id")
    )
    model_version_id: Mapped[int | None] = mapped_column(ForeignKey("model_version.id"))
    source: Mapped[SuggestionSource]
    scores_json: Mapped[dict] = mapped_column(JSON, default=dict)  # {label_id: score}


label_suggestion_labels = Table(
    "label_suggestion_labels",
    Base.metadata,
    Column("suggestion_id", ForeignKey("label_suggestion.id"), primary_key=True),
    Column("label_id", ForeignKey("label.id"), primary_key=True),
)
