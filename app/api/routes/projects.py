from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.exceptions import ValidationError
from app.schemas.annotation import ProgressDetailOut
from app.schemas.project import (
    ProjectCreate,
    ProjectDetailOut,
    ProjectOut,
    ProjectSettingsOut,
    ProjectSettingsUpdate,
)
from app.services import annotation_service, project_service

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(data: ProjectCreate, db: Session = Depends(get_db)) -> ProjectOut:
    return project_service.create_project(db, data)


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)) -> list[ProjectOut]:
    return project_service.list_projects(db)


@router.get("/{project_id}", response_model=ProjectDetailOut)
def get_project(project_id: int, db: Session = Depends(get_db)) -> ProjectDetailOut:
    return project_service.get_project_detail(db, project_id)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, confirm_name: str, db: Session = Depends(get_db)) -> None:
    """Permanent, unrecoverable. `confirm_name` must exactly match the
    project's current name — a server-side safety net in addition to
    whatever confirmation the UI already required, so this can't be
    triggered by a bare DELETE with no knowledge of what's being deleted."""
    project = project_service.get_project(db, project_id)
    if confirm_name != project.name:
        raise ValidationError("confirm_name did not match the project's name")
    project_service.delete_project(db, project_id)


@router.patch("/{project_id}/settings", response_model=ProjectSettingsOut)
def update_project_settings(
    project_id: int, data: ProjectSettingsUpdate, db: Session = Depends(get_db)
) -> ProjectSettingsOut:
    return project_service.update_settings(db, project_id, data)


@router.get("/{project_id}/progress", response_model=ProgressDetailOut)
def get_progress(project_id: int, db: Session = Depends(get_db)) -> ProgressDetailOut:
    project_service.get_project(db, project_id)  # 404s if missing
    return annotation_service.get_progress(db, project_id)
