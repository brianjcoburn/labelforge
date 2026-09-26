from datetime import datetime

from sqlalchemy import Column, ForeignKey, Table, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import AnnotationMode, AnnotationOutcome, AnnotationState


class Annotation(Base, TimestampMixin):
    """Current/head pointer for one (record, annotator) pair.

    Human-confirmed — authoritative ground truth. Denormalized fields mirror
    `current_revision_id` for fast reads; the append-only AnnotationRevision
    table is the source of truth for history.

    Note: `current_revision_id` and `AnnotationRevision.annotation_id` form a
    mutual FK reference. SQLite tolerates this (forward-referencing FKs are
    allowed at CREATE TABLE time), but a future Postgres migration would need
    one of the two constraints declared with `use_alter=True` (or created via
    a separate ALTER TABLE) to satisfy strict table-creation ordering.
    """

    __tablename__ = "annotation"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"))
    record_id: Mapped[int] = mapped_column(ForeignKey("record.id"))
    annotator_id: Mapped[str]
    taxonomy_version_id: Mapped[int] = mapped_column(ForeignKey("taxonomy_version.id"))
    current_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("annotation_revision.id")
    )
    outcome: Mapped[AnnotationOutcome]
    state: Mapped[AnnotationState] = mapped_column(default=AnnotationState.VALID)
    annotation_mode: Mapped[AnnotationMode]
    suggestion_id: Mapped[int | None] = mapped_column(ForeignKey("label_suggestion.id"))
    saw_suggestion_before_submit: Mapped[bool | None]
    revision_count: Mapped[int] = mapped_column(default=1)

    __table_args__ = (UniqueConstraint("record_id", "annotator_id"),)


class AnnotationRevision(Base):
    """Immutable, append-only. Never updated after insert.

    Editing an annotation always inserts a new revision and repoints
    Annotation.current_revision_id — it never mutates a prior row.
    """

    __tablename__ = "annotation_revision"

    id: Mapped[int] = mapped_column(primary_key=True)
    annotation_id: Mapped[int] = mapped_column(ForeignKey("annotation.id"))
    revision_number: Mapped[int]
    outcome: Mapped[AnnotationOutcome]
    taxonomy_version_id: Mapped[int] = mapped_column(ForeignKey("taxonomy_version.id"))
    annotation_mode: Mapped[AnnotationMode]
    annotator_id: Mapped[str]
    suggestion_id: Mapped[int | None] = mapped_column(ForeignKey("label_suggestion.id"))
    saw_suggestion_before_submit: Mapped[bool | None]
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


# Supports 0..N labels per revision (multilabel) as cleanly as exactly-1 (binary/multiclass).
annotation_revision_labels = Table(
    "annotation_revision_labels",
    Base.metadata,
    Column("revision_id", ForeignKey("annotation_revision.id"), primary_key=True),
    Column("label_id", ForeignKey("label.id"), primary_key=True),
)
