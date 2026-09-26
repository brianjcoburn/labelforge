import os
import shutil

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.exceptions import NotFoundError
from app.models.annotation import Annotation, AnnotationRevision, annotation_revision_labels
from app.models.dataset import Dataset
from app.models.enums import AnnotationOutcome
from app.models.evaluation import EvaluationRun
from app.models.model import ModelVersion, TrainingRun
from app.models.project import Project, ProjectSettings
from app.models.record import Record
from app.models.suggestion import LabelSuggestion, PromptVersion, label_suggestion_labels
from app.models.taxonomy import Label, Taxonomy, TaxonomyVersion
from app.schemas.project import ProjectCreate, ProjectSettingsUpdate


def create_project(db: Session, data: ProjectCreate) -> Project:
    project = Project(
        name=data.name,
        description=data.description,
        classification_type=data.classification_type,
        data_type=data.data_type,
    )
    db.add(project)
    db.flush()

    db.add(ProjectSettings(project_id=project.id))
    db.commit()
    db.refresh(project)
    return project


def list_projects(db: Session) -> list[Project]:
    return list(db.scalars(select(Project).order_by(Project.id)))


def get_project(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise NotFoundError(f"Project {project_id} not found")
    return project


def get_project_detail(db: Session, project_id: int) -> dict:
    project = get_project(db, project_id)
    settings = db.scalar(
        select(ProjectSettings).where(ProjectSettings.project_id == project_id)
    )
    has_taxonomy = (
        db.scalar(select(Taxonomy.id).where(Taxonomy.project_id == project_id))
        is not None
    )
    dataset_count = (
        db.scalar(
            select(func.count(Dataset.id)).where(Dataset.project_id == project_id)
        )
        or 0
    )
    record_count = (
        db.scalar(select(func.count(Record.id)).where(Record.project_id == project_id))
        or 0
    )
    annotated_count = (
        db.scalar(
            select(func.count(Annotation.id)).where(
                Annotation.project_id == project_id,
                Annotation.outcome == AnnotationOutcome.SUBMITTED,
            )
        )
        or 0
    )

    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "classification_type": project.classification_type,
        "data_type": project.data_type,
        "settings": settings,
        "has_taxonomy": has_taxonomy,
        "dataset_count": dataset_count,
        "record_count": record_count,
        "annotated_count": annotated_count,
    }


def delete_project(db: Session, project_id: int) -> None:
    """Permanently deletes a project and everything under it: dataset(s),
    records, taxonomy (all versions/labels), annotations (all revisions),
    suggestions, prompt versions, model/training/evaluation rows, settings,
    and any uploaded source files on disk. There's no undo — the API layer
    and frontend are both expected to require explicit confirmation before
    calling this.

    No ORM cascade relationships are defined on these models (deliberately —
    see app/models/*.py), so children are deleted before parents, in
    dependency order, rather than relying on cascading deletes.
    """
    project = get_project(db, project_id)  # raises NotFoundError if missing

    revision_ids = select(AnnotationRevision.id).join(
        Annotation, Annotation.id == AnnotationRevision.annotation_id
    ).where(Annotation.project_id == project_id)
    db.execute(
        delete(annotation_revision_labels).where(
            annotation_revision_labels.c.revision_id.in_(revision_ids)
        )
    )
    annotation_ids = select(Annotation.id).where(Annotation.project_id == project_id)
    db.execute(delete(AnnotationRevision).where(AnnotationRevision.annotation_id.in_(annotation_ids)))
    db.execute(delete(Annotation).where(Annotation.project_id == project_id))

    suggestion_ids = select(LabelSuggestion.id).where(LabelSuggestion.project_id == project_id)
    db.execute(
        delete(label_suggestion_labels).where(
            label_suggestion_labels.c.suggestion_id.in_(suggestion_ids)
        )
    )
    db.execute(delete(LabelSuggestion).where(LabelSuggestion.project_id == project_id))

    db.execute(delete(EvaluationRun).where(EvaluationRun.project_id == project_id))
    db.execute(delete(TrainingRun).where(TrainingRun.project_id == project_id))
    db.execute(delete(ModelVersion).where(ModelVersion.project_id == project_id))
    db.execute(delete(PromptVersion).where(PromptVersion.project_id == project_id))

    db.execute(delete(Record).where(Record.project_id == project_id))
    db.execute(delete(Dataset).where(Dataset.project_id == project_id))

    taxonomy = db.scalar(select(Taxonomy).where(Taxonomy.project_id == project_id))
    if taxonomy is not None:
        version_ids = select(TaxonomyVersion.id).where(TaxonomyVersion.taxonomy_id == taxonomy.id)
        db.execute(delete(Label).where(Label.taxonomy_version_id.in_(version_ids)))
        db.execute(delete(TaxonomyVersion).where(TaxonomyVersion.taxonomy_id == taxonomy.id))
        db.execute(delete(Taxonomy).where(Taxonomy.id == taxonomy.id))

    db.execute(delete(ProjectSettings).where(ProjectSettings.project_id == project_id))
    db.execute(delete(Project).where(Project.id == project.id))
    db.commit()

    uploads_dir = os.path.join(os.path.dirname(get_settings().db_path) or ".", "uploads", str(project_id))
    shutil.rmtree(uploads_dir, ignore_errors=True)


def update_settings(
    db: Session, project_id: int, data: ProjectSettingsUpdate
) -> ProjectSettings:
    get_project(db, project_id)  # raises NotFoundError if missing
    settings = db.scalar(
        select(ProjectSettings).where(ProjectSettings.project_id == project_id)
    )
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(settings, field, value)
    db.commit()
    db.refresh(settings)
    return settings
