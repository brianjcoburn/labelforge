from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.factory import get_llm_provider
from app.ai.prompt_builder import build_default_prompt
from app.config import get_settings
from app.core.exceptions import NotFoundError, ValidationError
from app.models.project import Project
from app.models.record import Record
from app.models.suggestion import PromptVersion
from app.schemas.prompt import PromptTestOut, PromptTestRequest, PromptVersionCreate
from app.services.taxonomy_service import get_active_version, get_label_specs


def generate_draft_prompt(db: Session, project_id: int) -> str:
    project = db.get(Project, project_id)
    if project is None:
        raise NotFoundError(f"Project {project_id} not found")
    version = get_active_version(db, project_id)
    labels = get_label_specs(db, version.id)
    return build_default_prompt(labels, project.classification_type)


def create_prompt_version(
    db: Session, project_id: int, data: PromptVersionCreate
) -> PromptVersion:
    project = db.get(Project, project_id)
    if project is None:
        raise NotFoundError(f"Project {project_id} not found")

    max_version = (
        db.scalar(
            select(func.max(PromptVersion.version_number)).where(
                PromptVersion.project_id == project_id
            )
        )
        or 0
    )
    settings = get_settings()
    prompt = PromptVersion(
        project_id=project_id,
        version_number=max_version + 1,
        template_text=data.template_text,
        provider="anthropic",
        model_name=settings.anthropic_model,
        is_active=False,
        created_by=settings.user_name,
    )
    db.add(prompt)
    db.commit()
    db.refresh(prompt)
    return prompt


def list_prompt_versions(db: Session, project_id: int) -> list[PromptVersion]:
    return list(
        db.scalars(
            select(PromptVersion)
            .where(PromptVersion.project_id == project_id)
            .order_by(PromptVersion.version_number.desc())
        )
    )


def activate_prompt_version(db: Session, project_id: int, version_id: int) -> PromptVersion:
    version = db.get(PromptVersion, version_id)
    if version is None or version.project_id != project_id:
        raise NotFoundError(f"Prompt version {version_id} not found in project {project_id}")

    others = db.scalars(
        select(PromptVersion).where(
            PromptVersion.project_id == project_id, PromptVersion.id != version_id
        )
    )
    for other in others:
        other.is_active = False
    version.is_active = True
    db.commit()
    db.refresh(version)
    return version


def get_active_prompt_version(db: Session, project_id: int) -> PromptVersion | None:
    return db.scalar(
        select(PromptVersion).where(
            PromptVersion.project_id == project_id, PromptVersion.is_active.is_(True)
        )
    )


def test_prompt(db: Session, project_id: int, data: PromptTestRequest) -> PromptTestOut:
    project = db.get(Project, project_id)
    if project is None:
        raise NotFoundError(f"Project {project_id} not found")

    record = db.get(Record, data.record_id)
    if record is None or record.project_id != project_id:
        raise NotFoundError(f"Record {data.record_id} not found in project {project_id}")

    template = data.template_text
    if template is None and data.version_id is not None:
        version = db.get(PromptVersion, data.version_id)
        if version is None or version.project_id != project_id:
            raise NotFoundError(f"Prompt version {data.version_id} not found")
        template = version.template_text
    if template is None:
        active = get_active_prompt_version(db, project_id)
        template = active.template_text if active else None

    taxonomy_version = get_active_version(db, project_id)
    labels = get_label_specs(db, taxonomy_version.id)

    provider = get_llm_provider()
    if provider is None:
        raise ValidationError(
            "No LLM provider configured — set ANTHROPIC_API_KEY to test prompts"
        )

    result = provider.classify(
        record.text,
        labels,
        classification_type=project.classification_type,
        prompt_template=template,
    )
    by_id = {label.id: label.name for label in labels}
    return PromptTestOut(
        predicted_label_ids=result.label_ids,
        predicted_label_names=[by_id[lid] for lid in result.label_ids if lid in by_id],
        raw_response=result.raw_response,
    )
