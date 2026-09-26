from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.exceptions import NotFoundError
from app.schemas.annotation import AnnotateNextOut, AnnotationOut, AnnotationSubmit
from app.services import annotation_service

router = APIRouter(tags=["annotations"])


@router.get("/api/projects/{project_id}/annotate/next", response_model=AnnotateNextOut)
def get_next_record(
    project_id: int, reveal_suggestion: bool = False, db: Session = Depends(get_db)
) -> AnnotateNextOut:
    return annotation_service.get_next_record(db, project_id, reveal_suggestion)


@router.post("/api/projects/{project_id}/records/{record_id}/annotations", response_model=AnnotationOut)
def submit_annotation(
    project_id: int, record_id: int, data: AnnotationSubmit, db: Session = Depends(get_db)
) -> AnnotationOut:
    return annotation_service.submit_annotation(db, project_id, record_id, data)


@router.get("/api/projects/{project_id}/records/{record_id}/annotations", response_model=AnnotationOut)
def get_annotation(project_id: int, record_id: int, db: Session = Depends(get_db)) -> AnnotationOut:
    result = annotation_service.get_annotation(db, record_id)
    if result is None:
        raise NotFoundError(f"No annotation yet for record {record_id}")
    return result
