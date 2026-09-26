from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.exceptions import NotFoundError
from app.models.project import Project
from app.schemas.model import ModelVersionOut, TrainingRunOut
from app.services import training_service

router = APIRouter(prefix="/api/projects/{project_id}", tags=["training"])


@router.post("/models/train", response_model=ModelVersionOut, status_code=201)
def train_now(project_id: int, db: Session = Depends(get_db)) -> ModelVersionOut:
    return training_service.train_now(db, project_id)


@router.get("/models/bootstrap-status")
def bootstrap_status(project_id: int, db: Session = Depends(get_db)) -> dict:
    project = db.get(Project, project_id)
    if project is None:
        raise NotFoundError(f"Project {project_id} not found")
    return training_service.bootstrap_status(db, project)


@router.get("/models", response_model=list[ModelVersionOut])
def list_models(project_id: int, db: Session = Depends(get_db)) -> list[ModelVersionOut]:
    return training_service.list_models(db, project_id)


@router.post("/models/{model_version_id}/activate", response_model=ModelVersionOut)
def activate_model(
    project_id: int, model_version_id: int, db: Session = Depends(get_db)
) -> ModelVersionOut:
    return training_service.activate_model(db, project_id, model_version_id)


@router.get("/training-runs", response_model=list[TrainingRunOut])
def list_training_runs(project_id: int, db: Session = Depends(get_db)) -> list[TrainingRunOut]:
    return training_service.list_training_runs(db, project_id)
