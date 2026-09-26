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


class AnnotateNextOut(BaseModel):
    record: RecordOut | None
    suggestion: SuggestionOut | None
    progress: ProgressOut


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
    revisions: list[AnnotationRevisionOut]
