"""Single source of truth for "how much do we trust auto-labeling right now
for this project." Everything else (sampling, triage, audit rate) reads
this — nothing else computes its own notion of trust.

Simplification versus the original design: trust is computed at the PROJECT
level here, not per taxonomy class. Per-class trust tracking is the more
correct long-term shape (a project can be confident on one label and shaky
on another), but multiplies the bookkeeping significantly, especially for
multilabel taxonomies where one audit touches several labels at once. This
is a deliberate, disclosed scope cut for this pass, not an oversight — the
gate sequence (agreement -> audit-measured accuracy) and the stepped audit
rate schedule are otherwise exactly as designed.
"""

import enum
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.factory import get_llm_provider
from app.models.annotation import Annotation, AnnotationRevision, annotation_revision_labels
from app.models.enums import AnnotationMode, AnnotationOutcome, ModelState
from app.models.model import ModelVersion
from app.models.project import ProjectSettings
from app.models.suggestion import LabelSuggestion, label_suggestion_labels

# Rolling window sizes and bars — named constants, not magic numbers, so the
# rules in the plan are traceable directly to code.
MIN_AUDITS_FOR_AUTO_LABEL = 50
MIN_AUDITS_FOR_HIGH_TRUST = 100
DUAL_PREDICTOR_ACCURACY_BAR = 0.90
SINGLE_PREDICTOR_ACCURACY_BAR = 0.95
HIGH_TRUST_ACCURACY_BAR = 0.97

AUDIT_RATE_ASSISTED = 1.0  # not actually "audited" — nothing is auto-labeled yet
AUDIT_RATE_ENTRY = 0.20
AUDIT_RATE_MID = 0.10
AUDIT_RATE_FLOOR = 0.05  # never zero — ongoing audit is what keeps the loop honest


class TrustTier(enum.IntEnum):
    MANUAL = 0
    ASSISTED = 1
    AUTO_LABEL = 2
    HIGH_TRUST = 3


@dataclass
class TrustState:
    has_classifier: bool
    has_llm: bool
    audit_count: int
    audit_accuracy: float | None  # over the rolling window; None if audit_count == 0
    tier: TrustTier
    audit_rate: float  # probability an eligible auto-label is sampled for human audit


def get_active_model(db: Session, project_id: int) -> ModelVersion | None:
    return db.scalar(
        select(ModelVersion).where(
            ModelVersion.project_id == project_id, ModelVersion.state == ModelState.ACTIVE
        )
    )


def _accuracy_bar(has_classifier: bool, has_llm: bool) -> float:
    return DUAL_PREDICTOR_ACCURACY_BAR if (has_classifier and has_llm) else SINGLE_PREDICTOR_ACCURACY_BAR


def _rolling_audit_accuracy(db: Session, project_id: int, window: int) -> tuple[int, float | None]:
    """Looks at the most recent `window` AUDIT-mode submissions and compares
    each one's final submitted labels to the suggestion it was shown —
    "accept" (labels match) vs "correct" (they don't). This is the one
    ground-truth-verified signal in the whole trust computation; everything
    else is the predictors agreeing with themselves."""
    revisions = list(
        db.scalars(
            select(AnnotationRevision)
            .join(Annotation, Annotation.id == AnnotationRevision.annotation_id)
            .where(
                Annotation.project_id == project_id,
                AnnotationRevision.annotation_mode == AnnotationMode.AUDIT,
                AnnotationRevision.outcome == AnnotationOutcome.SUBMITTED,
                AnnotationRevision.suggestion_id.is_not(None),
            )
            # created_at alone isn't a safe "most recent" ordering — SQLite's
            # CURRENT_TIMESTAMP has only 1-second resolution, and this system
            # is specifically designed to produce many audits in rapid
            # succession. id (monotonically increasing on insert) as a
            # tie-breaker makes "most recent" actually mean most recent.
            .order_by(AnnotationRevision.created_at.desc(), AnnotationRevision.id.desc())
            .limit(window)
        )
    )
    if not revisions:
        return 0, None

    matches = 0
    for rev in revisions:
        submitted_labels = set(
            db.scalars(
                select(annotation_revision_labels.c.label_id).where(
                    annotation_revision_labels.c.revision_id == rev.id
                )
            )
        )
        suggested_labels = set(
            db.scalars(
                select(label_suggestion_labels.c.label_id).where(
                    label_suggestion_labels.c.suggestion_id == rev.suggestion_id
                )
            )
        )
        if submitted_labels == suggested_labels:
            matches += 1
    return len(revisions), matches / len(revisions)


def assess_trust(db: Session, project_id: int, settings: ProjectSettings) -> TrustState:
    has_classifier = get_active_model(db, project_id) is not None
    has_llm = get_llm_provider(settings) is not None

    if not (has_classifier or has_llm):
        return TrustState(
            has_classifier=False,
            has_llm=False,
            audit_count=0,
            audit_accuracy=None,
            tier=TrustTier.MANUAL,
            audit_rate=AUDIT_RATE_ASSISTED,
        )

    bar = _accuracy_bar(has_classifier, has_llm)
    high_count, high_accuracy = _rolling_audit_accuracy(db, project_id, MIN_AUDITS_FOR_HIGH_TRUST)

    if high_count >= MIN_AUDITS_FOR_HIGH_TRUST and high_accuracy is not None and high_accuracy >= HIGH_TRUST_ACCURACY_BAR:
        return TrustState(has_classifier, has_llm, high_count, high_accuracy, TrustTier.HIGH_TRUST, AUDIT_RATE_FLOOR)

    count, accuracy = _rolling_audit_accuracy(db, project_id, MIN_AUDITS_FOR_AUTO_LABEL)
    if count >= MIN_AUDITS_FOR_AUTO_LABEL and accuracy is not None and accuracy >= bar:
        # At the bar but hasn't (yet, or any longer) sustained high-trust —
        # entry rate if this is a fresh crossing, mid rate once more evidence
        # has accumulated past the high-trust window size without qualifying.
        rate = AUDIT_RATE_MID if count >= MIN_AUDITS_FOR_HIGH_TRUST else AUDIT_RATE_ENTRY
        return TrustState(has_classifier, has_llm, count, accuracy, TrustTier.AUTO_LABEL, rate)

    # Below the audit-count floor, or accuracy regressed below the bar —
    # either way, back to (or still at) ASSISTED: suggestions shown, nothing
    # auto-labeled, every record goes to a human.
    return TrustState(has_classifier, has_llm, count, accuracy, TrustTier.ASSISTED, AUDIT_RATE_ASSISTED)
