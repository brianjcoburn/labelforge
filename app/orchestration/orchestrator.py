"""The one component that decides "what should a human do next for this
project" once automation is turned on. Everything it needs to decide with
(trust tier, existing suggestions) comes from app.orchestration.trust and
app.services.suggestion_service — this module composes those into a single
decision, rather than that decision being scattered across services.
"""

import random
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.annotation import Annotation
from app.models.enums import SuggestionSource
from app.models.project import Project, ProjectSettings
from app.models.record import Record
from app.models.suggestion import LabelSuggestion
from app.orchestration.trust import TrustTier, assess_trust
from app.services import suggestion_service

# How many never-yet-decided records to evaluate (generate predictions for,
# fuse, triage) in a single call before giving up and returning "done" for
# now. Bounds worst-case request latency — a real transformer/LLM inference
# per candidate is not free. The next call simply resumes past whatever was
# already decided (auto-labeled candidates are excluded from future scans).
MAX_SCAN_PER_CALL = 20


@dataclass
class NextAction:
    kind: Literal["annotate", "audit", "done"]
    record_id: int | None


def _fused_agreement(
    classifier_suggestion: LabelSuggestion | None, llm_suggestion: LabelSuggestion | None, db: Session
) -> Literal["agree", "disagree", "single", "none"]:
    if classifier_suggestion is None and llm_suggestion is None:
        return "none"
    if classifier_suggestion is None or llm_suggestion is None:
        return "single"
    a = set(suggestion_service.label_ids_for_suggestion(db, classifier_suggestion.id))
    b = set(suggestion_service.label_ids_for_suggestion(db, llm_suggestion.id))
    return "agree" if a == b else "disagree"


def _create_auto_label(db: Session, record: Record, source_suggestion: LabelSuggestion) -> None:
    """Records the fused, applied decision as its own suggestion row (never
    an Annotation — that would silently promote a prediction to ground
    truth, which nothing in this system ever does). Copies the winning
    suggestion's labels; the winning suggestion is the classifier's when
    both predictors exist and agree (it's the calibrated, project-specific
    signal), otherwise whichever single predictor produced it."""
    from app.models.suggestion import label_suggestion_labels

    label_ids = suggestion_service.label_ids_for_suggestion(db, source_suggestion.id)
    auto = LabelSuggestion(
        record_id=record.id,
        project_id=record.project_id,
        taxonomy_version_id=source_suggestion.taxonomy_version_id,
        model_version_id=source_suggestion.model_version_id,
        prompt_version_id=source_suggestion.prompt_version_id,
        source=SuggestionSource.AUTO_LABEL,
        scores_json=source_suggestion.scores_json,
    )
    db.add(auto)
    db.flush()
    for label_id in label_ids:
        db.execute(label_suggestion_labels.insert().values(suggestion_id=auto.id, label_id=label_id))
    db.commit()


def _pick_audit_candidate(db: Session, project_id: int, audit_rate: float) -> int | None:
    """Records that have been auto-labeled but never reviewed by a human are
    the audit pool. Deterministic order (lowest id first) within that pool;
    whether one gets served as an audit *this call* is a coin flip at the
    current trust tier's rate — this is what makes the audit rate an actual
    sampling rate rather than "audit everything until you stop.\""""
    annotated_ids = select(Annotation.record_id).where(Annotation.project_id == project_id)
    pending_audit_ids = list(
        db.scalars(
            select(LabelSuggestion.record_id)
            .where(
                LabelSuggestion.project_id == project_id,
                LabelSuggestion.source == SuggestionSource.AUTO_LABEL,
                LabelSuggestion.record_id.not_in(annotated_ids),
            )
            .order_by(LabelSuggestion.record_id)
        )
    )
    if not pending_audit_ids:
        return None
    if random.random() < audit_rate:
        return pending_audit_ids[0]
    return None


def decide_next_action(
    db: Session, project: Project, settings: ProjectSettings, candidate_record_ids: list[int]
) -> NextAction:
    """`candidate_record_ids` are records with no Annotation yet (the caller
    already filters that), in ascending id order. Records that already have
    an AUTO_LABEL suggestion are excluded by the caller too — they're the
    audit pool, handled separately here, not part of the fresh-candidate scan.
    """
    trust = assess_trust(db, project.id, settings)

    audit_id = _pick_audit_candidate(db, project.id, trust.audit_rate)
    if audit_id is not None:
        return NextAction(kind="audit", record_id=audit_id)

    fresh_candidates = [
        rid
        for rid in candidate_record_ids
        if db.scalar(
            select(LabelSuggestion.id).where(
                LabelSuggestion.record_id == rid, LabelSuggestion.source == SuggestionSource.AUTO_LABEL
            )
        )
        is None
    ]

    for record_id in fresh_candidates[:MAX_SCAN_PER_CALL]:
        record = db.get(Record, record_id)
        if record is None:
            continue

        classifier_suggestion = (
            suggestion_service.get_or_generate_classifier_suggestion(db, project, record)
            if trust.has_classifier
            else None
        )
        llm_suggestion = (
            suggestion_service.get_or_generate_llm_suggestion(db, project, settings, record)
            if trust.has_llm
            else None
        )
        agreement = _fused_agreement(classifier_suggestion, llm_suggestion, db)

        eligible = (
            (agreement == "agree" and trust.tier >= TrustTier.AUTO_LABEL)
            or (agreement == "single" and trust.tier >= TrustTier.AUTO_LABEL)
        )
        if eligible:
            winner = classifier_suggestion or llm_suggestion
            _create_auto_label(db, record, winner)
            continue  # handled without a human — keep scanning

        # Disagreement, or trust doesn't yet permit auto-labeling: show a
        # human this record. Disagreements are also the most informative
        # thing a human could label right now, but within the bounded scan
        # window rather than a full-pool uncertainty ranking (see module
        # docstring on MAX_SCAN_PER_CALL for the scope cut this implies).
        return NextAction(kind="annotate", record_id=record_id)

    return NextAction(kind="done", record_id=None)
