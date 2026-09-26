import os
from datetime import datetime, timezone

from sklearn.model_selection import train_test_split
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.classifiers.tfidf_logistic import TfidfLogisticClassifier
from app.config import get_settings
from app.core.exceptions import NotFoundError, ValidationError
from app.models.annotation import Annotation, annotation_revision_labels
from app.models.enums import (
    AnnotationOutcome,
    ClassificationType,
    ModelState,
    TrainingRunStatus,
    TrainingStrategyType,
)
from app.models.model import ModelVersion, TrainingRun
from app.models.project import Project
from app.models.record import Record
from app.models.taxonomy import Label
from app.services import evaluation_service
from app.services.taxonomy_service import get_active_version

MIN_TOTAL_EXAMPLES = 10
ARTIFACTS_DIR_NAME = "classifiers"


def _artifacts_dir(project_id: int) -> str:
    base = os.path.dirname(get_settings().db_path) or "."
    path = os.path.join(base, ARTIFACTS_DIR_NAME, str(project_id))
    os.makedirs(path, exist_ok=True)
    return path


def _label_names_for_revision(db: Session, revision_id: int | None) -> list[str]:
    if revision_id is None:
        return []
    return list(
        db.scalars(
            select(Label.name)
            .join(
                annotation_revision_labels,
                annotation_revision_labels.c.label_id == Label.id,
            )
            .where(annotation_revision_labels.c.revision_id == revision_id)
        )
    )


def _gather_training_data(
    db: Session, project: Project
) -> tuple[list[str], list, int]:
    """Only human-confirmed (SUBMITTED) annotations are ever training data —
    never AI predictions, per the ground-truth/suggestion separation
    principle that runs through the whole schema."""
    version = get_active_version(db, project.id)
    annotations = db.scalars(
        select(Annotation).where(
            Annotation.project_id == project.id,
            Annotation.outcome == AnnotationOutcome.SUBMITTED,
        )
    ).all()

    texts: list[str] = []
    labels: list = []
    for annotation in annotations:
        record = db.get(Record, annotation.record_id)
        if record is None:
            continue
        names = _label_names_for_revision(db, annotation.current_revision_id)
        if project.classification_type == ClassificationType.MULTILABEL:
            texts.append(record.text)
            labels.append(names)
        elif names:  # binary/multiclass: skip the (shouldn't-happen) empty case
            texts.append(record.text)
            labels.append(names[0])

    return texts, labels, version.id


def _validate_training_data(
    classification_type: ClassificationType, texts: list[str], labels: list
) -> None:
    if len(texts) < MIN_TOTAL_EXAMPLES:
        raise ValidationError(
            f"Need at least {MIN_TOTAL_EXAMPLES} human-confirmed annotations to "
            f"train, have {len(texts)}"
        )
    if classification_type != ClassificationType.MULTILABEL:
        distinct = {label for label in labels}
        if len(distinct) < 2:
            raise ValidationError(
                "Need at least 2 different labels represented among your confirmed "
                f"annotations to train, currently only have: {distinct or '(none)'}"
            )


def _split(classification_type: ClassificationType, texts: list[str], labels: list):
    stratify = labels if classification_type != ClassificationType.MULTILABEL else None
    try:
        return train_test_split(
            texts, labels, test_size=0.2, random_state=42, stratify=stratify
        )
    except ValueError:
        # Stratification needs >=2 examples per class — fall back to a plain
        # random split rather than failing training outright on a small/
        # imbalanced dataset.
        return train_test_split(texts, labels, test_size=0.2, random_state=42)


def _all_label_names(classification_type: ClassificationType, *label_lists: list) -> list[str]:
    names: set[str] = set()
    for labels in label_lists:
        if classification_type == ClassificationType.MULTILABEL:
            for row in labels:
                names.update(row)
        else:
            names.update(labels)
    return sorted(names)


def train_now(db: Session, project_id: int) -> ModelVersion:
    project = db.get(Project, project_id)
    if project is None:
        raise NotFoundError(f"Project {project_id} not found")

    texts, labels, taxonomy_version_id = _gather_training_data(db, project)
    _validate_training_data(project.classification_type, texts, labels)

    started_at = datetime.now(timezone.utc)
    X_train, X_test, y_train, y_test = _split(project.classification_type, texts, labels)

    classifier = TfidfLogisticClassifier(project.classification_type)
    classifier.train(X_train, y_train)

    y_pred = classifier.predict(X_test)
    y_scores = None
    if project.classification_type == ClassificationType.BINARY:
        y_scores = classifier.predict_scores(X_test)

    label_names = _all_label_names(project.classification_type, y_train, y_test)
    metrics = evaluation_service.compute_metrics(
        y_test, y_pred, project.classification_type, label_names, y_scores
    )

    version_number = (
        db.scalar(
            select(func.max(ModelVersion.version_number)).where(
                ModelVersion.project_id == project_id
            )
        )
        or 0
    ) + 1

    artifact_path = os.path.join(_artifacts_dir(project_id), f"model_v{version_number}.joblib")
    classifier.save(artifact_path)

    model_version = ModelVersion(
        project_id=project_id,
        taxonomy_version_id=taxonomy_version_id,
        version_number=version_number,
        classifier_type="tfidf_logistic",
        state=ModelState.INACTIVE,
        artifact_path=artifact_path,
        metrics_json={
            **metrics,
            "n_train": len(X_train),
            "n_held_out": len(X_test),
        },
    )
    db.add(model_version)
    db.flush()

    db.add(
        TrainingRun(
            project_id=project_id,
            taxonomy_version_id=taxonomy_version_id,
            training_strategy=TrainingStrategyType.MANUAL,
            trigger_reason="Train Now",
            status=TrainingRunStatus.SUCCEEDED,
            annotation_count_snapshot=len(texts),
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            resulting_model_version_id=model_version.id,
        )
    )
    db.commit()
    db.refresh(model_version)
    return model_version


def list_models(db: Session, project_id: int) -> list[ModelVersion]:
    return list(
        db.scalars(
            select(ModelVersion)
            .where(ModelVersion.project_id == project_id)
            .order_by(ModelVersion.version_number.desc())
        )
    )


def list_training_runs(db: Session, project_id: int) -> list[TrainingRun]:
    return list(
        db.scalars(
            select(TrainingRun)
            .where(TrainingRun.project_id == project_id)
            .order_by(TrainingRun.id.desc())
        )
    )


def activate_model(db: Session, project_id: int, model_version_id: int) -> ModelVersion:
    target = db.get(ModelVersion, model_version_id)
    if target is None or target.project_id != project_id:
        raise NotFoundError(f"Model version {model_version_id} not found in project {project_id}")

    current_taxonomy_version = get_active_version(db, project_id)
    if target.taxonomy_version_id != current_taxonomy_version.id:
        raise ValidationError(
            "This model was trained under a different taxonomy version and can't "
            "be activated as-is"
        )

    now = datetime.now(timezone.utc)
    others = db.scalars(
        select(ModelVersion).where(
            ModelVersion.project_id == project_id,
            ModelVersion.id != model_version_id,
            ModelVersion.state == ModelState.ACTIVE,
        )
    )
    for other in others:
        other.state = ModelState.INACTIVE
        other.deactivated_at = now

    target.state = ModelState.ACTIVE
    target.activated_at = now
    db.commit()
    db.refresh(target)
    return target
