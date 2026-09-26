from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.annotation import Annotation
from app.models.dataset import Dataset
from app.models.enums import AnnotationOutcome
from app.models.project import Project, ProjectSettings
from app.models.record import Record
from app.models.taxonomy import Taxonomy
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
