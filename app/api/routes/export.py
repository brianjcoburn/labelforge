from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.services import export_service

router = APIRouter(prefix="/api/projects/{project_id}/export", tags=["export"])


@router.get("/annotations.csv")
def export_annotations(
    project_id: int, include_suggestions: bool = False, db: Session = Depends(get_db)
) -> PlainTextResponse:
    csv_text = export_service.export_annotations_csv(db, project_id, include_suggestions)
    return PlainTextResponse(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=annotations.csv"},
    )


@router.get("/taxonomy.json")
def export_taxonomy(project_id: int, db: Session = Depends(get_db)) -> JSONResponse:
    return JSONResponse(export_service.export_taxonomy_json(db, project_id))


@router.get("/config.json")
def export_config(project_id: int, db: Session = Depends(get_db)) -> JSONResponse:
    return JSONResponse(export_service.export_config_json(db, project_id))
