from sqlalchemy import JSON, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import SourceFormat


class Dataset(Base, TimestampMixin):
    __tablename__ = "dataset"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"))
    name: Mapped[str]
    source_filename: Mapped[str]
    source_format: Mapped[SourceFormat]
    # {"id_column": str | None, "text_column": str, "label_column": str | None, "metadata_columns": [str, ...]}
    column_mapping: Mapped[dict] = mapped_column(JSON)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_by: Mapped[str]
