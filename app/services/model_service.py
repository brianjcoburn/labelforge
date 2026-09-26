import os

from huggingface_hub import hf_hub_download

from app.ai.model_catalog import LOCAL_MODEL_CATALOG, get_model_spec
from app.config import get_settings
from app.core.exceptions import NotFoundError

MODELS_DIR_NAME = "models"


def _models_dir() -> str:
    base = os.path.dirname(get_settings().db_path) or "."
    path = os.path.join(base, MODELS_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def get_model_path(catalog_id: str) -> str | None:
    spec = get_model_spec(catalog_id)
    if spec is None:
        return None
    path = os.path.join(_models_dir(), spec.filename)
    return path if os.path.exists(path) else None


def list_catalog() -> list[dict]:
    return [
        {
            "id": spec.id,
            "display_name": spec.display_name,
            "brand": spec.brand,
            "size_gb": spec.size_gb,
            "notes": spec.notes,
            "downloaded": get_model_path(spec.id) is not None,
        }
        for spec in LOCAL_MODEL_CATALOG
    ]


def download_model(catalog_id: str) -> dict:
    """Blocking download — this is a one-time, explicitly user-triggered
    action (multi-GB files, can take minutes), not something that needs
    background job infrastructure for a local single-user tool."""
    spec = get_model_spec(catalog_id)
    if spec is None:
        raise NotFoundError(f"Unknown local model '{catalog_id}'")

    hf_hub_download(
        repo_id=spec.repo_id,
        filename=spec.filename,
        local_dir=_models_dir(),
    )
    return {
        "id": spec.id,
        "display_name": spec.display_name,
        "brand": spec.brand,
        "size_gb": spec.size_gb,
        "notes": spec.notes,
        "downloaded": True,
    }
