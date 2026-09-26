from fastapi import APIRouter

from app.services import model_service

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("/local/catalog")
def list_local_catalog() -> list[dict]:
    return model_service.list_catalog()


@router.post("/local/{catalog_id}/download")
def download_local_model(catalog_id: str) -> dict:
    return model_service.download_model(catalog_id)
