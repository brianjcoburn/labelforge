from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ImportColumnMapping:
    text_column: str
    id_column: str | None = None
    label_column: str | None = None
    metadata_columns: list[str] = field(default_factory=list)


@dataclass
class ImportedRecord:
    text: str
    external_id: str | None = None
    existing_label_raw: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class DataImporter(ABC):
    """Abstraction over source file formats (CSV/TSV/JSON/JSONL).

    Only CSVImporter is implemented in v0.1; the others are trivial follow-ons
    against this same interface.
    """

    @abstractmethod
    def sniff_columns(self, file_path: str) -> list[str]: ...

    @abstractmethod
    def preview(
        self, file_path: str, mapping: ImportColumnMapping, limit: int = 20
    ) -> list[ImportedRecord]: ...

    @abstractmethod
    def parse(
        self, file_path: str, mapping: ImportColumnMapping
    ) -> Iterator[ImportedRecord]: ...
