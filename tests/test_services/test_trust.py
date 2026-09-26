"""Direct tests of app.orchestration.trust, bypassing the API — fast-forwarding
audit history (dozens of records) is much more direct against the service
layer than driving 50+ real HTTP round trips."""

from sqlalchemy.orm import Session

from app.models.annotation import Annotation, AnnotationRevision, annotation_revision_labels
from app.models.enums import (
    AnnotationMode,
    AnnotationOutcome,
    ClassificationType,
    DataType,
    LLMProviderType,
    SuggestionSource,
)
from app.models.project import Project, ProjectSettings
from app.models.record import Record
from app.models.suggestion import LabelSuggestion, label_suggestion_labels
from app.models.taxonomy import Label, Taxonomy, TaxonomyVersion
from app.orchestration.trust import TrustTier, assess_trust


def _make_project(db: Session, *, llm_configured: bool) -> tuple[Project, ProjectSettings, int]:
    project = Project(name="P", classification_type=ClassificationType.BINARY, data_type=DataType.TEXT)
    db.add(project)
    db.flush()
    settings = ProjectSettings(
        project_id=project.id,
        llm_provider=LLMProviderType.LOCAL,
        local_model_id="fake" if llm_configured else None,
    )
    db.add(settings)

    taxonomy = Taxonomy(project_id=project.id, name="T")
    db.add(taxonomy)
    db.flush()
    version = TaxonomyVersion(taxonomy_id=taxonomy.id, version_number=1, is_active=True, created_by="test")
    db.add(version)
    db.flush()
    label_a = Label(taxonomy_version_id=version.id, name="A", display_order=0)
    label_b = Label(taxonomy_version_id=version.id, name="B", display_order=1)
    db.add_all([label_a, label_b])
    db.commit()
    return project, settings, label_a.id


def _add_audit(db: Session, project: Project, label_id: int, *, correct: bool) -> None:
    """Creates one AUDIT-mode confirmed Annotation whose submitted label
    either matches (correct=True) or differs from (correct=False) the
    suggestion it was shown."""
    record = Record(dataset_id=1, project_id=project.id, text="txt")
    db.add(record)
    db.flush()

    version = db.query(TaxonomyVersion).first()
    suggestion = LabelSuggestion(
        record_id=record.id,
        project_id=project.id,
        taxonomy_version_id=version.id,
        source=SuggestionSource.AUTO_LABEL,
    )
    db.add(suggestion)
    db.flush()
    db.execute(label_suggestion_labels.insert().values(suggestion_id=suggestion.id, label_id=label_id))

    other_label_id = db.query(Label).filter(Label.id != label_id).first().id
    submitted_label_id = label_id if correct else other_label_id

    annotation = Annotation(
        project_id=project.id,
        record_id=record.id,
        annotator_id="local",
        taxonomy_version_id=version.id,
        outcome=AnnotationOutcome.SUBMITTED,
        annotation_mode=AnnotationMode.AUDIT,
        suggestion_id=suggestion.id,
        revision_count=1,
    )
    db.add(annotation)
    db.flush()
    revision = AnnotationRevision(
        annotation_id=annotation.id,
        revision_number=1,
        outcome=AnnotationOutcome.SUBMITTED,
        taxonomy_version_id=version.id,
        annotation_mode=AnnotationMode.AUDIT,
        annotator_id="local",
        suggestion_id=suggestion.id,
    )
    db.add(revision)
    db.flush()
    annotation.current_revision_id = revision.id
    db.execute(
        annotation_revision_labels.insert().values(revision_id=revision.id, label_id=submitted_label_id)
    )
    db.commit()


def test_no_predictor_is_manual_tier(db_session: Session) -> None:
    project, settings, _ = _make_project(db_session, llm_configured=False)
    trust = assess_trust(db_session, project.id, settings)
    assert trust.tier == TrustTier.MANUAL
    assert trust.has_classifier is False
    assert trust.has_llm is False


def test_predictor_with_no_audits_is_assisted(db_session: Session, fake_llm) -> None:
    project, settings, _ = _make_project(db_session, llm_configured=True)
    trust = assess_trust(db_session, project.id, settings)
    assert trust.has_llm is True
    assert trust.tier == TrustTier.ASSISTED
    assert trust.audit_rate == 1.0


def test_fifty_accurate_audits_reach_auto_label_tier(db_session: Session, fake_llm) -> None:
    project, settings, label_id = _make_project(db_session, llm_configured=True)
    for _ in range(50):
        _add_audit(db_session, project, label_id, correct=True)

    trust = assess_trust(db_session, project.id, settings)
    assert trust.audit_count == 50
    assert trust.audit_accuracy == 1.0
    assert trust.tier == TrustTier.AUTO_LABEL
    assert trust.audit_rate == 0.20


def test_low_accuracy_stays_assisted_despite_volume(db_session: Session, fake_llm) -> None:
    project, settings, label_id = _make_project(db_session, llm_configured=True)
    for i in range(50):
        _add_audit(db_session, project, label_id, correct=(i % 2 == 0))  # 50% accuracy

    trust = assess_trust(db_session, project.id, settings)
    assert trust.audit_accuracy == 0.5
    assert trust.tier == TrustTier.ASSISTED
    assert trust.audit_rate == 1.0


def test_regression_after_high_trust_snaps_back(db_session: Session, fake_llm) -> None:
    project, settings, label_id = _make_project(db_session, llm_configured=True)
    for _ in range(100):
        _add_audit(db_session, project, label_id, correct=True)
    assert assess_trust(db_session, project.id, settings).tier == TrustTier.HIGH_TRUST

    # A fresh run of 50 wrong audits is the most recent window -> should
    # immediately drag the tier back down, not stay stuck at HIGH_TRUST.
    for _ in range(50):
        _add_audit(db_session, project, label_id, correct=False)

    trust = assess_trust(db_session, project.id, settings)
    assert trust.tier in (TrustTier.ASSISTED, TrustTier.AUTO_LABEL)
    assert trust.tier != TrustTier.HIGH_TRUST
