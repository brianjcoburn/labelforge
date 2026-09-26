from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.dataset import (
    DatasetImportOut,
    DatasetImportRequest,
    DatasetOut,
    DatasetUploadOut,
)
from app.services import import_service

router = APIRouter(prefix="/api/projects/{project_id}/datasets", tags=["datasets"])


@router.post("/upload", response_model=DatasetUploadOut)
async def upload_dataset(
    project_id: int, file: UploadFile, db: Session = Depends(get_db)
) -> DatasetUploadOut:
    contents = await file.read()
    return import_service.upload_dataset(db, project_id, file.filename or "upload.csv", contents)


@router.post("/{dataset_id}/import", response_model=DatasetImportOut)
def import_dataset(
    project_id: int,
    dataset_id: int,
    data: DatasetImportRequest,
    db: Session = Depends(get_db),
) -> DatasetImportOut:
    return import_service.finalize_import(db, project_id, dataset_id, data)


@router.get("", response_model=list[DatasetOut])
def list_datasets(project_id: int, db: Session = Depends(get_db)) -> list[DatasetOut]:
    return import_service.list_datasets(db, project_id)
