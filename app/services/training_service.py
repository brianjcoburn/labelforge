import os
import shutil
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.classifiers.registry import build_classifier
from app.config import get_settings
from app.core.exceptions import NotFoundError, ValidationError
from app.models.annotation import Annotation, AnnotationRevision, annotation_revision_labels
from app.models.enums import (
    AnnotationOutcome,
    ClassificationType,
    ModelState,
    TrainingRunStatus,
    TrainingTrigger,
)
from app.models.model import ModelVersion, TrainingRun
from app.models.project import Project, ProjectSettings
from app.models.record import Record
from app.models.taxonomy import Label
from app.orchestration.trust import get_active_model
from app.services import evaluation_service
from app.services.taxonomy_service import get_active_version, get_label_specs

ARTIFACTS_DIR_NAME = "classifiers"

# Bootstrap floor: replaces the old flat MIN_TOTAL_EXAMPLES=10, which was far
# too low for fine-tuning a transformer to learn a class boundary at all.
PER_CLASS_MIN = 20
TOTAL_MIN_BASE = 150
TOTAL_MIN_PER_CLASS = 30

# Held-out set sizing at carve time (a fraction of the confirmed set,
# bounded — the plan's 100-500 absolute bounds assume a much larger dataset
# than the bootstrap floor itself, so this is a fraction bounded to a
# reasonable range instead).
HELDOUT_FRACTION = 0.20
HELDOUT_MIN = 20
HELDOUT_MAX = 500

# Retraining trigger threshold: new confirmed annotations since the last
# successful run must clear this OR a relative fraction of that run's size.
SCHEDULED_MIN_NEW = 50
SCHEDULED_RELATIVE_FRACTION = 0.10

# Auto-activation tolerance: a candidate doesn't need to strictly improve,
# just not meaningfully regress (absorbs training-run noise).
ACTIVATION_TOLERANCE = 0.01

_PRIMARY_METRIC = {
    ClassificationType.BINARY: "f1",
    ClassificationType.MULTICLASS: "macro_f1",
    ClassificationType.MULTILABEL: "macro_f1",
}


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
            .join(annotation_revision_labels, annotation_revision_labels.c.label_id == Label.id)
            .where(annotation_revision_labels.c.revision_id == revision_id)
        )
    )


def _gather_confirmed(db: Session, project: Project) -> tuple[list[int], list[str], list, int]:
    """Only human-confirmed (SUBMITTED) annotations are ever training/eval
    data — never AI predictions, per the ground-truth/suggestion separation
    principle that runs through the whole schema. Returns parallel lists
    (record_ids, texts, labels) plus the active taxonomy_version_id."""
    version = get_active_version(db, project.id)
    annotations = db.scalars(
        select(Annotation).where(
            Annotation.project_id == project.id,
            Annotation.outcome == AnnotationOutcome.SUBMITTED,
        )
    ).all()

    record_ids: list[int] = []
    texts: list[str] = []
    labels: list = []
    for annotation in annotations:
        record = db.get(Record, annotation.record_id)
        if record is None:
            continue
        names = _label_names_for_revision(db, annotation.current_revision_id)
        if project.classification_type == ClassificationType.MULTILABEL:
            record_ids.append(record.id)
            texts.append(record.text)
            labels.append(names)
        elif names:  # binary/multiclass: skip the (shouldn't-happen) empty case
            record_ids.append(record.id)
            texts.append(record.text)
            labels.append(names[0])

    return record_ids, texts, labels, version.id


def _per_class_counts(classification_type: ClassificationType, labels: list) -> Counter:
    if classification_type == ClassificationType.MULTILABEL:
        return Counter(name for row in labels for name in row)
    return Counter(labels)


def bootstrap_status(db: Session, project: Project) -> dict:
    """How close this project is to its first automatic training run —
    surfaced to the user by name, not just a pass/fail floor."""
    taxonomy_version = get_active_version(db, project.id)
    all_labels = [label.name for label in get_label_specs(db, taxonomy_version.id)]
    _, texts, labels, _ = _gather_confirmed(db, project)
    counts = _per_class_counts(project.classification_type, labels)

    total_floor = max(TOTAL_MIN_BASE, TOTAL_MIN_PER_CLASS * max(len(all_labels), 1))
    under_floor = {name: counts.get(name, 0) for name in all_labels if counts.get(name, 0) < PER_CLASS_MIN}

    return {
        "total_confirmed": len(texts),
        "total_floor": total_floor,
        "per_class_counts": dict(counts),
        "per_class_floor": PER_CLASS_MIN,
        "classes_under_floor": under_floor,
        "ready": len(texts) >= total_floor and not under_floor,
    }


def _validate_training_data(db: Session, project: Project, labels: list) -> None:
    status = bootstrap_status(db, project)
    if not status["ready"]:
        under = ", ".join(f"{name} ({count}/{PER_CLASS_MIN})" for name, count in status["classes_under_floor"].items())
        raise ValidationError(
            f"Not enough confirmed data to train yet: have {status['total_confirmed']} "
            f"confirmed annotations (need {status['total_floor']}); classes below the "
            f"per-class floor: {under or 'none — just need more total volume'}"
        )
    if project.classification_type != ClassificationType.MULTILABEL:
        if len({label for label in labels}) < 2:
            raise ValidationError("Need at least 2 different labels represented to train")


def _get_or_create_frozen_holdout(
    db: Session, project: Project, taxonomy_version_id: int, record_ids: list[int]
) -> set[int]:
    """The held-out set is carved exactly once per taxonomy version, from
    whatever's confirmed at that moment, and never touched again — this is
    what makes two models trained weeks apart genuinely comparable, unlike
    a fresh random split on every run."""
    already_frozen = set(
        db.scalars(
            select(Record.id).where(Record.held_out_for_taxonomy_version_id == taxonomy_version_id)
        )
    )
    if already_frozen:
        return already_frozen

    n = len(record_ids)
    heldout_size = min(HELDOUT_MAX, max(HELDOUT_MIN, round(HELDOUT_FRACTION * n)))
    heldout_size = min(heldout_size, n - 1) if n > 1 else 0
    # Deterministic (not random) so re-running this in tests/dev is
    # reproducible: every Nth record by id, spread across the whole set.
    step = max(1, n // max(heldout_size, 1))
    chosen = set(sorted(record_ids)[::step][:heldout_size])

    for record_id in chosen:
        record = db.get(Record, record_id)
        record.held_out_for_taxonomy_version_id = taxonomy_version_id
    db.commit()
    return chosen


def train_now(
    db: Session,
    project_id: int,
    trigger: TrainingTrigger = TrainingTrigger.MANUAL,
    trigger_reason: str = "Train Now",
    classifier_type: str = "transformer",
) -> ModelVersion:
    project = db.get(Project, project_id)
    if project is None:
        raise NotFoundError(f"Project {project_id} not found")

    record_ids, texts, labels, taxonomy_version_id = _gather_confirmed(db, project)
    _validate_training_data(db, project, labels)

    heldout_ids = _get_or_create_frozen_holdout(db, project, taxonomy_version_id, record_ids)

    X_train, y_train, X_eval, y_eval = [], [], [], []
    for rid, text, label in zip(record_ids, texts, labels, strict=True):
        if rid in heldout_ids:
            X_eval.append(text)
            y_eval.append(label)
        else:
            X_train.append(text)
            y_train.append(label)

    if not X_train or not X_eval:
        raise ValidationError(
            "Not enough data to form both a training set and the frozen held-out "
            "evaluation set — label more records and try again"
        )

    started_at = datetime.now(timezone.utc)
    classifier = build_classifier(classifier_type, project.classification_type)
    classifier.train(X_train, y_train)

    y_pred = classifier.predict(X_eval)
    y_scores = classifier.predict_scores(X_eval) if project.classification_type == ClassificationType.BINARY else None

    label_names = sorted(
        {name for row in (y_train + y_eval) for name in row}
        if project.classification_type == ClassificationType.MULTILABEL
        else {*y_train, *y_eval}
    )
    metrics = evaluation_service.compute_metrics(
        y_eval, y_pred, project.classification_type, label_names, y_scores
    )

    version_number = (
        db.scalar(
            select(func.max(ModelVersion.version_number)).where(ModelVersion.project_id == project_id)
        )
        or 0
    ) + 1

    artifact_path = os.path.join(_artifacts_dir(project_id), f"model_v{version_number}")
    try:
        classifier.save(artifact_path)
    except Exception as e:
        db.add(
            TrainingRun(
                project_id=project_id,
                taxonomy_version_id=taxonomy_version_id,
                trigger=trigger,
                trigger_reason=trigger_reason,
                status=TrainingRunStatus.FAILED,
                annotation_count_snapshot=len(texts),
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                error_message=str(e),
            )
        )
        db.commit()
        raise

    model_version = ModelVersion(
        project_id=project_id,
        taxonomy_version_id=taxonomy_version_id,
        version_number=version_number,
        classifier_type=classifier_type,
        state=ModelState.INACTIVE,
        artifact_path=artifact_path,
        metrics_json={**metrics, "n_train": len(X_train), "n_held_out": len(X_eval)},
    )
    db.add(model_version)
    db.flush()

    db.add(
        TrainingRun(
            project_id=project_id,
            taxonomy_version_id=taxonomy_version_id,
            trigger=trigger,
            trigger_reason=trigger_reason,
            status=TrainingRunStatus.SUCCEEDED,
            annotation_count_snapshot=len(texts),
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            resulting_model_version_id=model_version.id,
        )
    )
    db.commit()
    db.refresh(model_version)

    settings = db.scalar(select(ProjectSettings).where(ProjectSettings.project_id == project_id))
    if settings and settings.automation_enabled:
        _maybe_auto_activate(db, project, model_version)
        db.refresh(model_version)

    _prune_old_artifacts(db, project_id)
    return model_version


def _maybe_auto_activate(db: Session, project: Project, candidate: ModelVersion) -> None:
    metric_key = _PRIMARY_METRIC[project.classification_type]
    candidate_score = candidate.metrics_json.get(metric_key, 0.0)
    current = get_active_model(db, project.id)

    if current is None:
        _do_activate(db, project.id, candidate.id)
        return

    current_score = (current.metrics_json or {}).get(metric_key, 0.0)
    regressed = candidate_score < current_score - ACTIVATION_TOLERANCE
    candidate.metrics_json = {
        **candidate.metrics_json,
        "comparison": {
            "vs_active_model_id": current.id,
            "active_score": current_score,
            "candidate_score": candidate_score,
            "metric": metric_key,
            "regressed": regressed,
        },
    }
    db.commit()
    if not regressed:
        _do_activate(db, project.id, candidate.id)
    # else: candidate stays INACTIVE, comparison recorded for the user to review.


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


def _do_activate(db: Session, project_id: int, model_version_id: int) -> ModelVersion:
    target = db.get(ModelVersion, model_version_id)
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


def activate_model(db: Session, project_id: int, model_version_id: int) -> ModelVersion:
    """Manual override — always available regardless of automation_enabled,
    e.g. to activate a candidate that auto-activation left inactive after a
    measured regression, once a human has reviewed it and decided it's fine."""
    target = db.get(ModelVersion, model_version_id)
    if target is None or target.project_id != project_id:
        raise NotFoundError(f"Model version {model_version_id} not found in project {project_id}")

    current_taxonomy_version = get_active_version(db, project_id)
    if target.taxonomy_version_id != current_taxonomy_version.id:
        raise ValidationError(
            "This model was trained under a different taxonomy version and can't "
            "be activated as-is"
        )
    result = _do_activate(db, project_id, model_version_id)
    _prune_old_artifacts(db, project_id)
    return result


def _prune_old_artifacts(db: Session, project_id: int) -> None:
    """Disk is tight — keep the active model's artifact and the most
    recently deactivated one (rollback/comparison); delete artifacts for
    models that were once active and have since been superseded, beyond
    that one.

    Deliberately never prunes a model that has never been activated
    (activated_at is None) — that's either a freshly trained candidate
    awaiting a decision (the normal case when automation is off — every
    model starts this way) or one a human rejected via the regression path
    and might still choose to force-activate. Pruning those was a real bug
    caught during live verification: it deleted a model's artifact
    immediately after training, before anyone had a chance to activate it.
    """
    models = list_models(db, project_id)
    keep_ids: set[int] = set()
    active = next((m for m in models if m.state == ModelState.ACTIVE), None)
    if active:
        keep_ids.add(active.id)
    ever_active_now_superseded = sorted(
        (m for m in models if m.state != ModelState.ACTIVE and m.activated_at is not None),
        key=lambda m: m.deactivated_at or m.activated_at,
        reverse=True,
    )
    if ever_active_now_superseded:
        keep_ids.add(ever_active_now_superseded[0].id)

    for model in models:
        if model.id in keep_ids or not model.artifact_path or model.activated_at is None:
            continue  # never-activated candidates are never auto-pruned
        if os.path.isdir(model.artifact_path):
            shutil.rmtree(model.artifact_path, ignore_errors=True)
        elif os.path.exists(model.artifact_path):
            os.remove(model.artifact_path)


def maybe_trigger_training(db: Session, project_id: int) -> ModelVersion | None:
    """Called after a human confirms an annotation, when automation is on.
    Training stays synchronous even here (a submit that happens to cross a
    retraining threshold takes as long as training takes — seconds to a
    couple minutes on this hardware for realistic dataset sizes) rather than
    adding background-job infrastructure this local single-user tool doesn't
    otherwise need. Returns the new model version if a run happened."""
    project = db.get(Project, project_id)
    if project is None:
        return None

    in_flight = db.scalar(
        select(TrainingRun.id).where(
            TrainingRun.project_id == project_id,
            TrainingRun.status.in_([TrainingRunStatus.PENDING, TrainingRunStatus.RUNNING]),
        )
    )
    if in_flight is not None:
        return None

    active = get_active_model(db, project_id)
    current_taxonomy_version = get_active_version(db, project_id)

    if active is not None and active.taxonomy_version_id != current_taxonomy_version.id:
        return train_now(
            db, project_id, trigger=TrainingTrigger.TAXONOMY_INVALIDATED,
            trigger_reason="Active model's taxonomy version no longer matches the current one",
        )

    last_run = db.scalar(
        select(TrainingRun)
        .where(TrainingRun.project_id == project_id, TrainingRun.status == TrainingRunStatus.SUCCEEDED)
        .order_by(TrainingRun.completed_at.desc())
    )

    if last_run is None:
        status = bootstrap_status(db, project)
        if status["ready"]:
            return train_now(
                db, project_id, trigger=TrainingTrigger.BOOTSTRAP,
                trigger_reason=f"Bootstrap floor cleared: {status['total_confirmed']} confirmed annotations",
            )
        return None

    since = last_run.completed_at
    new_confirmed = (
        db.scalar(
            select(func.count(func.distinct(Annotation.record_id)))
            .join(AnnotationRevision, AnnotationRevision.id == Annotation.current_revision_id)
            .where(
                Annotation.project_id == project_id,
                Annotation.outcome == AnnotationOutcome.SUBMITTED,
                AnnotationRevision.created_at > since,
            )
        )
        or 0
    )
    threshold = max(SCHEDULED_MIN_NEW, round(SCHEDULED_RELATIVE_FRACTION * last_run.annotation_count_snapshot))
    if new_confirmed >= threshold:
        return train_now(
            db, project_id, trigger=TrainingTrigger.SCHEDULED,
            trigger_reason=f"{new_confirmed} new confirmed annotations since the last training run",
        )
    return None
