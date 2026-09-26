from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.llm_provider import LabelSpec
from app.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.enums import ClassificationType, TaxonomyChangeType
from app.models.project import Project
from app.models.taxonomy import Label, Taxonomy, TaxonomyVersion
from app.schemas.taxonomy import LabelUpdate, TaxonomyCreate


def _validate_label_count(classification_type: ClassificationType, count: int) -> None:
    if classification_type == ClassificationType.BINARY and count != 2:
        raise ValidationError(
            f"Binary classification requires exactly 2 labels, got {count}"
        )
    if classification_type == ClassificationType.MULTICLASS and count < 2:
        raise ValidationError(
            f"Multi-class classification requires at least 2 labels, got {count}"
        )
    if classification_type == ClassificationType.MULTILABEL and count < 1:
        raise ValidationError("Multi-label classification requires at least 1 label")


def create_taxonomy(db: Session, project_id: int, data: TaxonomyCreate) -> Taxonomy:
    project = db.get(Project, project_id)
    if project is None:
        raise NotFoundError(f"Project {project_id} not found")

    existing = db.scalar(select(Taxonomy).where(Taxonomy.project_id == project_id))
    if existing is not None:
        raise ConflictError(f"Project {project_id} already has a taxonomy")

    names = [label.name.strip().lower() for label in data.labels]
    if len(names) != len(set(names)):
        raise ValidationError("Label names must be unique within a taxonomy version")

    _validate_label_count(project.classification_type, len(data.labels))

    taxonomy = Taxonomy(project_id=project_id, name=data.name)
    db.add(taxonomy)
    db.flush()

    version = TaxonomyVersion(
        taxonomy_id=taxonomy.id,
        version_number=1,
        change_type=TaxonomyChangeType.INITIAL,
        is_active=True,
        created_by=get_settings().user_name,
    )
    db.add(version)
    db.flush()

    for order, label_data in enumerate(data.labels):
        db.add(
            Label(
                taxonomy_version_id=version.id,
                name=label_data.name,
                description=label_data.description,
                include_criteria=label_data.include_criteria,
                exclude_criteria=label_data.exclude_criteria,
                examples=label_data.examples,
                display_order=order,
            )
        )

    db.commit()
    db.refresh(taxonomy)
    return taxonomy


def get_taxonomy_detail(db: Session, project_id: int) -> dict:
    taxonomy = db.scalar(select(Taxonomy).where(Taxonomy.project_id == project_id))
    if taxonomy is None:
        raise NotFoundError(f"Project {project_id} has no taxonomy yet")

    version = db.scalar(
        select(TaxonomyVersion).where(
            TaxonomyVersion.taxonomy_id == taxonomy.id,
            TaxonomyVersion.is_active.is_(True),
        )
    )
    labels = list(
        db.scalars(
            select(Label)
            .where(Label.taxonomy_version_id == version.id)
            .order_by(Label.display_order)
        )
    )

    return {
        "id": taxonomy.id,
        "name": taxonomy.name,
        "active_version_number": version.version_number,
        "labels": labels,
    }


def get_active_version(db: Session, project_id: int) -> TaxonomyVersion:
    taxonomy = db.scalar(select(Taxonomy).where(Taxonomy.project_id == project_id))
    if taxonomy is None:
        raise NotFoundError(f"Project {project_id} has no taxonomy yet")
    version = db.scalar(
        select(TaxonomyVersion).where(
            TaxonomyVersion.taxonomy_id == taxonomy.id,
            TaxonomyVersion.is_active.is_(True),
        )
    )
    if version is None:
        raise NotFoundError(f"Project {project_id} has no active taxonomy version")
    return version


def update_label(db: Session, project_id: int, label_id: int, data: LabelUpdate) -> Label:
    version = get_active_version(db, project_id)  # 404s if project has no taxonomy
    label = db.get(Label, label_id)
    if label is None or label.taxonomy_version_id != version.id:
        raise NotFoundError(f"Label {label_id} not found in project {project_id}'s taxonomy")

    updates = data.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"] is not None:
        new_name = updates["name"].strip().lower()
        collision = db.scalar(
            select(Label).where(
                Label.taxonomy_version_id == version.id,
                Label.id != label_id,
                func.lower(Label.name) == new_name,
            )
        )
        if collision is not None:
            raise ValidationError(f"Another label is already named '{updates['name']}'")

    for field, value in updates.items():
        setattr(label, field, value)

    db.commit()
    db.refresh(label)
    return label


def get_label_specs(db: Session, taxonomy_version_id: int) -> list[LabelSpec]:
    """Labels for a taxonomy version, in the shape LLMProvider expects."""
    labels = db.scalars(
        select(Label)
        .where(Label.taxonomy_version_id == taxonomy_version_id)
        .order_by(Label.display_order)
    )
    return [
        LabelSpec(
            id=label.id,
            name=label.name,
            description=label.description,
            include_criteria=label.include_criteria,
            exclude_criteria=label.exclude_criteria,
            examples=label.examples,
        )
        for label in labels
    ]
