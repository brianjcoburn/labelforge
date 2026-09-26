from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.exceptions import NotFoundError, ValidationError
from app.models.annotation import Annotation, AnnotationRevision, annotation_revision_labels
from app.models.enums import (
    AnnotationMode,
    AnnotationOutcome,
    AnnotationState,
    ClassificationType,
)
from app.models.project import Project, ProjectSettings
from app.models.record import Record
from app.models.suggestion import LabelSuggestion, label_suggestion_labels
from app.models.taxonomy import Label
from app.sampling.base import SamplingContext, SequentialSamplingStrategy
from app.schemas.annotation import (
    AnnotateNextOut,
    AnnotationOut,
    AnnotationRevisionOut,
    AnnotationSubmit,
    ProgressOut,
    RecordOut,
    SuggestionOut,
)
from app.services.taxonomy_service import get_active_version


def _annotator_id() -> str:
    return get_settings().user_name


def _project_and_settings(db: Session, project_id: int) -> tuple[Project, ProjectSettings]:
    project = db.get(Project, project_id)
    if project is None:
        raise NotFoundError(f"Project {project_id} not found")
    settings = db.scalar(
        select(ProjectSettings).where(ProjectSettings.project_id == project_id)
    )
    return project, settings


def _label_names(db: Session, label_ids: list[int]) -> list[str]:
    if not label_ids:
        return []
    rows = db.scalars(select(Label).where(Label.id.in_(label_ids)))
    by_id = {label.id: label.name for label in rows}
    return [by_id[lid] for lid in label_ids if lid in by_id]


def _load_suggestion(db: Session, record_id: int) -> LabelSuggestion | None:
    return db.scalar(
        select(LabelSuggestion).where(LabelSuggestion.record_id == record_id)
    )


def _suggestion_out(db: Session, suggestion: LabelSuggestion) -> SuggestionOut:
    label_ids = list(
        db.scalars(
            select(label_suggestion_labels.c.label_id).where(
                label_suggestion_labels.c.suggestion_id == suggestion.id
            )
        )
    )
    return SuggestionOut(
        source=suggestion.source,
        label_ids=label_ids,
        label_names=_label_names(db, label_ids),
    )


def get_progress(db: Session, project_id: int) -> dict:
    total = (
        db.scalar(select(func.count(Record.id)).where(Record.project_id == project_id))
        or 0
    )
    annotator_id = _annotator_id()
    rows = db.execute(
        select(Annotation.outcome, func.count(Annotation.id))
        .where(Annotation.project_id == project_id, Annotation.annotator_id == annotator_id)
        .group_by(Annotation.outcome)
    ).all()
    counts = {outcome: count for outcome, count in rows}
    submitted = counts.get(AnnotationOutcome.SUBMITTED, 0)
    skipped = counts.get(AnnotationOutcome.SKIPPED, 0)
    flagged = counts.get(AnnotationOutcome.FLAGGED, 0)
    completed = submitted + skipped + flagged

    label_rows = db.execute(
        select(Label.name, func.count(annotation_revision_labels.c.revision_id))
        .join(
            annotation_revision_labels,
            annotation_revision_labels.c.label_id == Label.id,
        )
        .join(
            AnnotationRevision,
            AnnotationRevision.id == annotation_revision_labels.c.revision_id,
        )
        .join(Annotation, Annotation.current_revision_id == AnnotationRevision.id)
        .where(Annotation.project_id == project_id)
        .group_by(Label.name)
    ).all()

    return {
        "total": total,
        "submitted": submitted,
        "skipped": skipped,
        "flagged": flagged,
        "completed": completed,
        "remaining": max(total - completed, 0),
        "label_distribution": dict(label_rows),
    }


def get_next_record(
    db: Session, project_id: int, reveal_suggestion: bool = False
) -> AnnotateNextOut:
    project, settings = _project_and_settings(db, project_id)
    annotator_id = _annotator_id()

    annotated_subquery = select(Annotation.record_id).where(
        Annotation.project_id == project_id, Annotation.annotator_id == annotator_id
    )
    candidate_ids = list(
        db.scalars(
            select(Record.id).where(
                Record.project_id == project_id, Record.id.not_in(annotated_subquery)
            )
        )
    )

    progress = get_progress(db, project_id)
    next_id = SequentialSamplingStrategy().select_next(
        project_id=project_id,
        candidate_record_ids=candidate_ids,
        context=SamplingContext(),
    )

    if next_id is None:
        return AnnotateNextOut(
            record=None,
            suggestion=None,
            progress=ProgressOut(completed=progress["completed"], total=progress["total"]),
        )

    record = db.get(Record, next_id)
    suggestion = _load_suggestion(db, next_id)

    show_suggestion = suggestion is not None and (
        settings.annotation_mode == AnnotationMode.AI_FIRST
        or (settings.annotation_mode == AnnotationMode.ON_DEMAND and reveal_suggestion)
    )
    # human_first: suggestion (and the raw imported label) stay hidden until
    # after the human submits, to avoid anchoring the independent judgment.
    hide_existing_label = settings.annotation_mode == AnnotationMode.HUMAN_FIRST

    return AnnotateNextOut(
        record=RecordOut(
            id=record.id,
            text=record.text,
            metadata=record.metadata_json,
            existing_label_raw=None if hide_existing_label else record.existing_label_raw,
        ),
        suggestion=_suggestion_out(db, suggestion) if show_suggestion else None,
        progress=ProgressOut(completed=progress["completed"], total=progress["total"]),
    )


def _validate_labels_for_submit(
    classification_type: ClassificationType, label_ids: list[int]
) -> None:
    count = len(label_ids)
    if classification_type in (ClassificationType.BINARY, ClassificationType.MULTICLASS):
        if count != 1:
            raise ValidationError(
                f"{classification_type.value} annotations require exactly 1 label, got {count}"
            )
    # multilabel: zero or more — nothing further to check


def submit_annotation(
    db: Session, project_id: int, record_id: int, data: AnnotationSubmit
) -> AnnotationOut:
    project, settings = _project_and_settings(db, project_id)
    record = db.get(Record, record_id)
    if record is None or record.project_id != project_id:
        raise NotFoundError(f"Record {record_id} not found in project {project_id}")

    version = get_active_version(db, project_id)
    valid_label_ids = set(
        db.scalars(select(Label.id).where(Label.taxonomy_version_id == version.id))
    )
    if not set(data.label_ids).issubset(valid_label_ids):
        raise ValidationError("One or more label_ids are not part of the active taxonomy")

    if data.outcome == AnnotationOutcome.SKIPPED and data.label_ids:
        raise ValidationError("Skipped annotations cannot include labels")
    if data.outcome == AnnotationOutcome.SUBMITTED:
        _validate_labels_for_submit(project.classification_type, data.label_ids)

    annotator_id = _annotator_id()
    existing = db.scalar(
        select(Annotation).where(
            Annotation.record_id == record_id, Annotation.annotator_id == annotator_id
        )
    )

    suggestion = _load_suggestion(db, record_id)
    if data.saw_suggestion_before_submit is not None:
        saw_suggestion = data.saw_suggestion_before_submit
    elif suggestion is None:
        saw_suggestion = False
    else:
        saw_suggestion = settings.annotation_mode == AnnotationMode.AI_FIRST

    if data.outcome == AnnotationOutcome.FLAGGED:
        new_state = AnnotationState.NEEDS_REVIEW
    elif data.outcome == AnnotationOutcome.SUBMITTED:
        new_state = (
            AnnotationState.REVIEWED
            if existing and existing.state == AnnotationState.NEEDS_REVIEW
            else AnnotationState.VALID
        )
    else:  # SKIPPED — no taxonomy-relevant labels to validate
        new_state = existing.state if existing else AnnotationState.VALID

    revision_number = (existing.revision_count + 1) if existing else 1

    revision = AnnotationRevision(
        annotation_id=existing.id if existing else None,  # set below if new
        revision_number=revision_number,
        outcome=data.outcome,
        taxonomy_version_id=version.id,
        annotation_mode=settings.annotation_mode,
        annotator_id=annotator_id,
        suggestion_id=suggestion.id if suggestion else None,
        saw_suggestion_before_submit=saw_suggestion,
        note=data.note,
    )

    if existing is None:
        annotation = Annotation(
            project_id=project_id,
            record_id=record_id,
            annotator_id=annotator_id,
            taxonomy_version_id=version.id,
            outcome=data.outcome,
            state=new_state,
            annotation_mode=settings.annotation_mode,
            suggestion_id=suggestion.id if suggestion else None,
            saw_suggestion_before_submit=saw_suggestion,
            revision_count=1,
        )
        db.add(annotation)
        db.flush()
        revision.annotation_id = annotation.id
    else:
        annotation = existing

    db.add(revision)
    db.flush()

    for label_id in data.label_ids:
        db.execute(
            annotation_revision_labels.insert().values(
                revision_id=revision.id, label_id=label_id
            )
        )

    annotation.current_revision_id = revision.id
    annotation.outcome = data.outcome
    annotation.state = new_state
    annotation.annotation_mode = settings.annotation_mode
    annotation.suggestion_id = suggestion.id if suggestion else None
    annotation.saw_suggestion_before_submit = saw_suggestion
    annotation.revision_count = revision_number

    db.commit()
    return get_annotation(db, record_id)


def get_annotation(db: Session, record_id: int) -> AnnotationOut | None:
    annotator_id = _annotator_id()
    annotation = db.scalar(
        select(Annotation).where(
            Annotation.record_id == record_id, Annotation.annotator_id == annotator_id
        )
    )
    if annotation is None:
        return None

    revisions = list(
        db.scalars(
            select(AnnotationRevision)
            .where(AnnotationRevision.annotation_id == annotation.id)
            .order_by(AnnotationRevision.revision_number)
        )
    )

    revision_outs = []
    current_labels: list[str] = []
    for rev in revisions:
        label_ids = list(
            db.scalars(
                select(annotation_revision_labels.c.label_id).where(
                    annotation_revision_labels.c.revision_id == rev.id
                )
            )
        )
        names = _label_names(db, label_ids)
        if rev.id == annotation.current_revision_id:
            current_labels = names
        revision_outs.append(
            AnnotationRevisionOut(
                revision_number=rev.revision_number,
                outcome=rev.outcome,
                label_names=names,
                annotator_id=rev.annotator_id,
                taxonomy_version_id=rev.taxonomy_version_id,
                annotation_mode=rev.annotation_mode,
                saw_suggestion_before_submit=rev.saw_suggestion_before_submit,
                note=rev.note,
                created_at=rev.created_at,
            )
        )

    return AnnotationOut(
        record_id=record_id,
        outcome=annotation.outcome,
        state=annotation.state,
        current_labels=current_labels,
        revisions=revision_outs,
    )
