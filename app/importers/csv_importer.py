import csv
from collections.abc import Iterator
from itertools import islice

from app.importers.base import DataImporter, ImportColumnMapping, ImportedRecord


class CSVImporter(DataImporter):
    def sniff_columns(self, file_path: str) -> list[str]:
        with open(file_path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, [])
        return header

    def preview(
        self, file_path: str, mapping: ImportColumnMapping, limit: int = 20
    ) -> list[ImportedRecord]:
        return list(islice(self.parse(file_path, mapping), limit))

    def parse(
        self, file_path: str, mapping: ImportColumnMapping
    ) -> Iterator[ImportedRecord]:
        with open(file_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if mapping.text_column not in row:
                    raise ValueError(
                        f"Text column '{mapping.text_column}' not found in row"
                    )
                metadata = {
                    col: row[col] for col in mapping.metadata_columns if col in row
                }
                yield ImportedRecord(
                    text=row[mapping.text_column],
                    external_id=(
                        row.get(mapping.id_column) if mapping.id_column else None
                    ),
                    existing_label_raw=(
                        row.get(mapping.label_column) if mapping.label_column else None
                    ),
                    metadata=metadata,
                )
