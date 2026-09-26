from datetime import datetime

from pydantic import BaseModel

from app.models.enums import AnnotationMode, AnnotationOutcome, AnnotationState, SuggestionSource


class AnnotationSubmit(BaseModel):
    outcome: AnnotationOutcome
    label_ids: list[int] = []
    note: str | None = None
    # Usually left unset — the server derives this from annotation_mode. Only
    # meaningful for on_demand mode, where the client knows whether the human
    # actually clicked "show suggestion" before submitting.
    saw_suggestion_before_submit: bool | None = None


class SuggestionOut(BaseModel):
    source: SuggestionSource
    label_ids: list[int]
    label_names: list[str]


class RecordOut(BaseModel):
    id: int
    text: str
    metadata: dict
    existing_label_raw: str | None


class ProgressOut(BaseModel):
    completed: int
    total: int


class ProgressDetailOut(BaseModel):
    total: int
    submitted: int
    skipped: int
    flagged: int
    completed: int
    remaining: int
    label_distribution: dict[str, int]
    llm_agreement: float | None = None
    auto_labeled: int = 0
    trust_tier: str | None = None
    audit_accuracy: float | None = None


class AnnotateNextOut(BaseModel):
    record: RecordOut | None
    suggestion: SuggestionOut | None
    progress: ProgressOut
    # "audit": this record was already auto-labeled (both predictors agreed
    # and the trust tier permitted it) and is being sampled for a human
    # spot-check, not labeled from scratch. Always "annotate" when
    # automation is off. See app/orchestration.
    mode: str = "annotate"


class AnnotationRevisionOut(BaseModel):
    revision_number: int
    outcome: AnnotationOutcome
    label_names: list[str]
    annotator_id: str
    taxonomy_version_id: int
    annotation_mode: AnnotationMode
    saw_suggestion_before_submit: bool | None
    note: str | None
    created_at: datetime


class AnnotationOut(BaseModel):
    record_id: int
    outcome: AnnotationOutcome
    state: AnnotationState
    current_labels: list[str]
    current_label_ids: list[int]
    revisions: list[AnnotationRevisionOut]
    # Populated in human_first mode right after submit, so the UI can reveal
    # the AI's independent prediction now that the human's judgment is locked in.
    revealed_suggestion: SuggestionOut | None = None


class RecordDetailOut(BaseModel):
    """Used when navigating back to review/edit a specific record (Previous),
    as opposed to AnnotateNextOut's forward-sampling flow."""

    record: RecordOut
    suggestion: SuggestionOut | None
    annotation: AnnotationOut | None
