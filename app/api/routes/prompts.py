from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.prompt import (
    PromptDraftOut,
    PromptTestOut,
    PromptTestRequest,
    PromptVersionCreate,
    PromptVersionOut,
)
from app.services import prompt_service

router = APIRouter(prefix="/api/projects/{project_id}/prompts", tags=["prompts"])


@router.post("/generate", response_model=PromptDraftOut)
def generate_draft(project_id: int, db: Session = Depends(get_db)) -> PromptDraftOut:
    return PromptDraftOut(template_text=prompt_service.generate_draft_prompt(db, project_id))


@router.post("", response_model=PromptVersionOut, status_code=201)
def create_prompt_version(
    project_id: int, data: PromptVersionCreate, db: Session = Depends(get_db)
) -> PromptVersionOut:
    return prompt_service.create_prompt_version(db, project_id, data)


@router.get("", response_model=list[PromptVersionOut])
def list_prompt_versions(project_id: int, db: Session = Depends(get_db)) -> list[PromptVersionOut]:
    return prompt_service.list_prompt_versions(db, project_id)


@router.post("/{version_id}/activate", response_model=PromptVersionOut)
def activate_prompt_version(
    project_id: int, version_id: int, db: Session = Depends(get_db)
) -> PromptVersionOut:
    return prompt_service.activate_prompt_version(db, project_id, version_id)


@router.post("/test", response_model=PromptTestOut)
def test_prompt(
    project_id: int, data: PromptTestRequest, db: Session = Depends(get_db)
) -> PromptTestOut:
    return prompt_service.test_prompt(db, project_id, data)
