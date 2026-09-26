import csv
import os
from itertools import islice

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.importers.base import ImportColumnMapping
from app.importers.csv_importer import CSVImporter
from app.models.dataset import Dataset
from app.models.enums import SourceFormat, SuggestionSource
from app.models.project import Project
from app.models.record import Record
from app.models.suggestion import LabelSuggestion, label_suggestion_labels
from app.models.taxonomy import Label
from app.schemas.dataset import DatasetImportOut, DatasetImportRequest, DatasetUploadOut
from app.services.taxonomy_service import get_active_version

UPLOAD_DIR_NAME = "uploads"


def _uploads_dir(project_id: int) -> str:
    base = os.path.dirname(get_settings().db_path) or "."
    path = os.path.join(base, UPLOAD_DIR_NAME, str(project_id))
    os.makedirs(path, exist_ok=True)
    return path


def _stored_path(project_id: int, dataset_id: int, filename: str) -> str:
    return os.path.join(_uploads_dir(project_id), f"{dataset_id}_{filename}")


def upload_dataset(
    db: Session, project_id: int, filename: str, contents: bytes
) -> DatasetUploadOut:
    project = db.get(Project, project_id)
    if project is None:
        raise NotFoundError(f"Project {project_id} not found")

    if not filename.lower().endswith(".csv"):
        raise ValidationError("Only CSV files are supported in this version")

    dataset = Dataset(
        project_id=project_id,
        name=filename.rsplit(".", 1)[0],
        source_filename=filename,
        source_format=SourceFormat.CSV,
        column_mapping={},
        record_count=0,
        imported_by=get_settings().user_name,
    )
    db.add(dataset)
    db.flush()

    path = _stored_path(project_id, dataset.id, filename)
    with open(path, "wb") as f:
        f.write(contents)
    db.commit()

    importer = CSVImporter()
    columns = importer.sniff_columns(path)
    with open(path, newline="", encoding="utf-8") as f:
        preview_rows = list(islice(csv.DictReader(f), 20))

    return DatasetUploadOut(
        dataset_id=dataset.id, columns=columns, preview_rows=preview_rows
    )


def finalize_import(
    db: Session, project_id: int, dataset_id: int, data: DatasetImportRequest
) -> DatasetImportOut:
    dataset = db.get(Dataset, dataset_id)
    if dataset is None or dataset.project_id != project_id:
        raise NotFoundError(f"Dataset {dataset_id} not found in project {project_id}")
    if dataset.record_count > 0:
        raise ConflictError(f"Dataset {dataset_id} has already been imported")

    path = _stored_path(project_id, dataset_id, dataset.source_filename)
    mapping = ImportColumnMapping(
        text_column=data.text_column,
        id_column=data.id_column,
        label_column=data.label_column,
        metadata_columns=data.metadata_columns,
    )

    # Active taxonomy is optional at import time: if absent (or the label
    # column's values don't match any label), imported values are still kept
    # on Record.existing_label_raw for visibility, just without a suggestion.
    label_lookup: dict[str, int] = {}
    taxonomy_version_id: int | None = None
    try:
        version = get_active_version(db, project_id)
        taxonomy_version_id = version.id
        labels = db.scalars(
            select(Label).where(Label.taxonomy_version_id == version.id)
        )
        label_lookup = {label.name.strip().lower(): label.id for label in labels}
    except NotFoundError:
        pass

    importer = CSVImporter()
    pending: list[tuple[Record, str | None]] = []
    try:
        for imported in importer.parse(path, mapping):
            record = Record(
                dataset_id=dataset_id,
                project_id=project_id,
                external_id=imported.external_id,
                text=imported.text,
                metadata_json=imported.metadata,
                existing_label_raw=imported.existing_label_raw,
            )
            db.add(record)
            pending.append((record, imported.existing_label_raw))
    except ValueError as e:
        raise ValidationError(str(e)) from e

    db.flush()

    matched_count = 0
    unmatched_count = 0
    for record, raw_label in pending:
        if raw_label is None or raw_label == "":
            continue
        label_id = label_lookup.get(raw_label.strip().lower())
        if label_id is None or taxonomy_version_id is None:
            unmatched_count += 1
            continue
        suggestion = LabelSuggestion(
            record_id=record.id,
            project_id=project_id,
            taxonomy_version_id=taxonomy_version_id,
            source=SuggestionSource.IMPORTED,
        )
        db.add(suggestion)
        db.flush()
        db.execute(
            label_suggestion_labels.insert().values(
                suggestion_id=suggestion.id, label_id=label_id
            )
        )
        matched_count += 1

    dataset.column_mapping = {
        "id_column": data.id_column,
        "text_column": data.text_column,
        "label_column": data.label_column,
        "metadata_columns": data.metadata_columns,
    }
    dataset.name = data.name
    dataset.record_count = len(pending)
    db.commit()

    return DatasetImportOut(
        dataset_id=dataset_id,
        record_count=len(pending),
        matched_label_count=matched_count,
        unmatched_label_count=unmatched_count,
    )


def list_datasets(db: Session, project_id: int) -> list[Dataset]:
    return list(db.scalars(select(Dataset).where(Dataset.project_id == project_id)))
