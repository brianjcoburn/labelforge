from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.taxonomy import TaxonomyCreate, TaxonomyOut
from app.services import taxonomy_service

router = APIRouter(prefix="/api/projects/{project_id}/taxonomy", tags=["taxonomy"])


@router.post("", response_model=TaxonomyOut, status_code=201)
def create_taxonomy(
    project_id: int, data: TaxonomyCreate, db: Session = Depends(get_db)
) -> TaxonomyOut:
    taxonomy_service.create_taxonomy(db, project_id, data)
    return taxonomy_service.get_taxonomy_detail(db, project_id)


@router.get("", response_model=TaxonomyOut)
def get_taxonomy(project_id: int, db: Session = Depends(get_db)) -> TaxonomyOut:
    return taxonomy_service.get_taxonomy_detail(db, project_id)
