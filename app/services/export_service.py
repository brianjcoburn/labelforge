import csv
import io
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.annotation import Annotation, AnnotationRevision, annotation_revision_labels
from app.models.project import Project, ProjectSettings
from app.models.record import Record
from app.models.suggestion import LabelSuggestion, label_suggestion_labels
from app.models.taxonomy import Label, Taxonomy, TaxonomyVersion


def _label_names_for_revision(db: Session, revision_id: int) -> list[str]:
    return list(
        db.scalars(
            select(Label.name)
            .join(
                annotation_revision_labels,
                annotation_revision_labels.c.label_id == Label.id,
            )
            .where(annotation_revision_labels.c.revision_id == revision_id)
        )
    )


def _suggestion_labels(db: Session, record_id: int) -> tuple[str, list[str]] | None:
    suggestion = db.scalar(
        select(LabelSuggestion).where(LabelSuggestion.record_id == record_id)
    )
    if suggestion is None:
        return None
    names = list(
        db.scalars(
            select(Label.name)
            .join(
                label_suggestion_labels, label_suggestion_labels.c.label_id == Label.id
            )
            .where(label_suggestion_labels.c.suggestion_id == suggestion.id)
        )
    )
    return suggestion.source.value, names


def export_annotations_csv(
    db: Session, project_id: int, include_suggestions: bool = False
) -> str:
    project = db.get(Project, project_id)
    if project is None:
        raise NotFoundError(f"Project {project_id} not found")

    records = list(
        db.scalars(select(Record).where(Record.project_id == project_id).order_by(Record.id))
    )
    annotations_by_record = {
        a.record_id: a
        for a in db.scalars(select(Annotation).where(Annotation.project_id == project_id))
    }

    output = io.StringIO()
    fieldnames = [
        "record_id",
        "external_id",
        "text",
        "metadata",
        "human_labels",
        "annotation_outcome",
        "annotation_state",
        "taxonomy_version",
    ]
    if include_suggestions:
        fieldnames += ["suggestion_source", "suggestion_labels"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for record in records:
        annotation = annotations_by_record.get(record.id)
        row = {
            "record_id": record.id,
            "external_id": record.external_id or "",
            "text": record.text,
            "metadata": json.dumps(record.metadata_json),
            "human_labels": "",
            "annotation_outcome": "",
            "annotation_state": "",
            "taxonomy_version": "",
        }
        if annotation is not None:
            names = (
                _label_names_for_revision(db, annotation.current_revision_id)
                if annotation.current_revision_id
                else []
            )
            row.update(
                {
                    "human_labels": ";".join(names),
                    "annotation_outcome": annotation.outcome.value,
                    "annotation_state": annotation.state.value,
                    "taxonomy_version": annotation.taxonomy_version_id,
                }
            )
        if include_suggestions:
            suggestion = _suggestion_labels(db, record.id)
            row["suggestion_source"] = suggestion[0] if suggestion else ""
            row["suggestion_labels"] = ";".join(suggestion[1]) if suggestion else ""
        writer.writerow(row)

    return output.getvalue()


def export_taxonomy_json(db: Session, project_id: int) -> dict:
    taxonomy = db.scalar(select(Taxonomy).where(Taxonomy.project_id == project_id))
    if taxonomy is None:
        raise NotFoundError(f"Project {project_id} has no taxonomy yet")
    version = db.scalar(
        select(TaxonomyVersion).where(
            TaxonomyVersion.taxonomy_id == taxonomy.id, TaxonomyVersion.is_active.is_(True)
        )
    )
    labels = list(
        db.scalars(
            select(Label)
            .where(Label.taxonomy_version_id == version.id)
            .order_by(Label.display_order)
        )
    )
    return {
        "name": taxonomy.name,
        "version_number": version.version_number,
        "labels": [
            {
                "name": label.name,
                "description": label.description,
                "include_criteria": label.include_criteria,
                "exclude_criteria": label.exclude_criteria,
                "examples": label.examples,
            }
            for label in labels
        ],
    }


def export_config_json(db: Session, project_id: int) -> dict:
    """Project configuration only — never includes secrets (there are none in
    this schema by design; API keys live in environment variables, never in
    project settings or exports)."""
    project = db.get(Project, project_id)
    if project is None:
        raise NotFoundError(f"Project {project_id} not found")
    settings = db.scalar(
        select(ProjectSettings).where(ProjectSettings.project_id == project_id)
    )
    return {
        "name": project.name,
        "description": project.description,
        "classification_type": project.classification_type.value,
        "data_type": project.data_type.value,
        "annotation_mode": settings.annotation_mode.value,
        "training_strategy": settings.training_strategy.value,
        "sampling_strategy": settings.sampling_strategy.value,
        "batch_training_threshold": settings.batch_training_threshold,
    }
