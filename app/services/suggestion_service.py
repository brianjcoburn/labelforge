"""Suggestion generation/lookup shared between annotation_service (per-record,
human-facing flow) and app/orchestration (the automation loop) — pulled out
of annotation_service to avoid a circular import between the two.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.factory import get_llm_provider, invalidate_provider
from app.models.enums import SuggestionSource
from app.models.project import Project, ProjectSettings
from app.models.record import Record
from app.models.suggestion import LabelSuggestion, label_suggestion_labels
from app.models.taxonomy import Label
from app.schemas.annotation import SuggestionOut
from app.services.prompt_service import get_active_prompt_version
from app.services.taxonomy_service import get_active_version, get_label_specs

logger = logging.getLogger(__name__)


def label_names_for_ids(db: Session, label_ids: list[int]) -> list[str]:
    if not label_ids:
        return []
    rows = db.scalars(select(Label).where(Label.id.in_(label_ids)))
    by_id = {label.id: label.name for label in rows}
    return [by_id[lid] for lid in label_ids if lid in by_id]


def label_ids_for_suggestion(db: Session, suggestion_id: int) -> list[int]:
    return list(
        db.scalars(
            select(label_suggestion_labels.c.label_id).where(
                label_suggestion_labels.c.suggestion_id == suggestion_id
            )
        )
    )


def suggestion_out(db: Session, suggestion: LabelSuggestion) -> SuggestionOut:
    label_ids = label_ids_for_suggestion(db, suggestion.id)
    return SuggestionOut(
        source=suggestion.source,
        label_ids=label_ids,
        label_names=label_names_for_ids(db, label_ids),
    )


def load_suggestion(db: Session, record_id: int) -> LabelSuggestion | None:
    """Display precedence for "the" suggestion shown to a human: an
    AUTO_LABEL (the orchestrator's own fused decision) is the most
    informative thing to show if one exists, then CLASSIFIER, then LLM, then
    IMPORTED (a dataset's pre-existing label column at import time)."""
    for source in (
        SuggestionSource.AUTO_LABEL,
        SuggestionSource.CLASSIFIER,
        SuggestionSource.LLM,
        SuggestionSource.IMPORTED,
    ):
        suggestion = db.scalar(
            select(LabelSuggestion).where(
                LabelSuggestion.record_id == record_id, LabelSuggestion.source == source
            )
        )
        if suggestion is not None:
            return suggestion
    return None


def get_or_generate_llm_suggestion(
    db: Session, project: Project, settings: ProjectSettings, record: Record
) -> LabelSuggestion | None:
    """Lazily generates and caches an LLM prediction for a record.

    Returns None whenever AI isn't available or fails — callers must treat
    that as ordinary (falls back to whatever suggestion already exists, or no
    suggestion at all), never as an error. Generates once per record and
    reuses it afterward; it does not regenerate if the prompt is edited later
    (that kind of invalidation is a taxonomy/prompt-revision workflow, out of
    scope here).
    """
    existing = db.scalar(
        select(LabelSuggestion).where(
            LabelSuggestion.record_id == record.id, LabelSuggestion.source == SuggestionSource.LLM
        )
    )
    if existing is not None:
        return existing

    provider = get_llm_provider(settings)
    if provider is None:
        return None

    try:
        taxonomy_version = get_active_version(db, project.id)
        labels = get_label_specs(db, taxonomy_version.id)
        prompt_version = get_active_prompt_version(db, project.id)
        result = provider.classify(
            record.text,
            labels,
            classification_type=project.classification_type,
            prompt_template=prompt_version.template_text if prompt_version else None,
        )
    except Exception:
        logger.warning("LLM prediction failed for record %s", record.id, exc_info=True)
        invalidate_provider(settings)
        return None

    suggestion = LabelSuggestion(
        record_id=record.id,
        project_id=project.id,
        taxonomy_version_id=taxonomy_version.id,
        prompt_version_id=prompt_version.id if prompt_version else None,
        source=SuggestionSource.LLM,
    )
    db.add(suggestion)
    db.flush()
    for label_id in result.label_ids:
        db.execute(
            label_suggestion_labels.insert().values(suggestion_id=suggestion.id, label_id=label_id)
        )
    db.commit()
    return suggestion


def get_or_generate_classifier_suggestion(
    db: Session, project: Project, record: Record
) -> LabelSuggestion | None:
    """Same lazy-generate-and-cache contract as the LLM version, backed by
    the project's currently ACTIVE trained model instead of a prompt."""
    from app.orchestration.trust import get_active_model  # local: avoid import cycle

    existing = db.scalar(
        select(LabelSuggestion).where(
            LabelSuggestion.record_id == record.id,
            LabelSuggestion.source == SuggestionSource.CLASSIFIER,
        )
    )
    if existing is not None:
        return existing

    active_model = get_active_model(db, project.id)
    if active_model is None:
        return None

    try:
        from app.ai.classifiers.registry import load_classifier

        classifier = load_classifier(active_model.classifier_type, active_model.artifact_path)
        scores = classifier.predict_scores([record.text])[0]
    except Exception:
        logger.warning("Classifier prediction failed for record %s", record.id, exc_info=True)
        return None

    predicted_names = [name for name, score in scores.items() if score > 0.5] or (
        [max(scores, key=scores.get)] if scores else []
    )
    taxonomy_version = get_active_version(db, project.id)
    name_to_id = {label.name: label.id for label in get_label_specs(db, taxonomy_version.id)}

    suggestion = LabelSuggestion(
        record_id=record.id,
        project_id=project.id,
        taxonomy_version_id=taxonomy_version.id,
        model_version_id=active_model.id,
        source=SuggestionSource.CLASSIFIER,
        scores_json=scores,
    )
    db.add(suggestion)
    db.flush()
    for name in predicted_names:
        if name in name_to_id:
            db.execute(
                label_suggestion_labels.insert().values(
                    suggestion_id=suggestion.id, label_id=name_to_id[name]
                )
            )
    db.commit()
    return suggestion
