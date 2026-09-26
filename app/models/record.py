from sqlalchemy import JSON, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


class Record(Base, TimestampMixin):
    __tablename__ = "record"

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("dataset.id"))
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"))
    external_id: Mapped[str | None]
    text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    # Raw value from an existing label column at import time, kept for visibility only.
    # Never auto-promoted to ground truth — see SuggestionSource.IMPORTED in suggestion.py.
    existing_label_raw: Mapped[str | None]
