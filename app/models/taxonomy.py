from sqlalchemy import JSON, Boolean, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import TaxonomyChangeType


class Taxonomy(Base, TimestampMixin):
    __tablename__ = "taxonomy"

    id: Mapped[int] = mapped_column(primary_key=True)
    # One taxonomy per project, versioned over time.
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), unique=True)
    name: Mapped[str]


class TaxonomyVersion(Base, TimestampMixin):
    __tablename__ = "taxonomy_version"

    id: Mapped[int] = mapped_column(primary_key=True)
    taxonomy_id: Mapped[int] = mapped_column(ForeignKey("taxonomy.id"))
    version_number: Mapped[int] = mapped_column(Integer)
    change_type: Mapped[TaxonomyChangeType | None]
    change_description: Mapped[str | None] = mapped_column(Text)
    parent_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("taxonomy_version.id")
    )
    # Exactly one active version per taxonomy at a time.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str]


class Label(Base, TimestampMixin):
    __tablename__ = "label"

    id: Mapped[int] = mapped_column(primary_key=True)
    taxonomy_version_id: Mapped[int] = mapped_column(ForeignKey("taxonomy_version.id"))
    name: Mapped[str]
    description: Mapped[str | None] = mapped_column(Text)
    include_criteria: Mapped[str | None] = mapped_column(Text)
    exclude_criteria: Mapped[str | None] = mapped_column(Text)
    examples: Mapped[list[str]] = mapped_column(JSON, default=list)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
