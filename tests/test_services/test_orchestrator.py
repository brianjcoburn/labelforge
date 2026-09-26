"""Direct tests of app.orchestration.orchestrator's decision logic, with
suggestion generation monkeypatched to controlled agree/disagree outcomes —
the ML pipeline itself is already exercised in test_training_api.py; this
file is purely about the orchestration decision, not prediction quality."""

from sqlalchemy.orm import Session

from app.models.enums import (
    ClassificationType,
    DataType,
    LLMProviderType,
    SuggestionSource,
)
from app.models.project import Project, ProjectSettings
from app.models.record import Record
from app.models.suggestion import LabelSuggestion, label_suggestion_labels
from app.models.taxonomy import Label, Taxonomy, TaxonomyVersion
from app.orchestration import orchestrator
from app.orchestration.trust import TrustState, TrustTier


def _make_project_with_records(db: Session, n_records: int = 3) -> tuple[Project, ProjectSettings, list[int], int]:
    project = Project(name="P", classification_type=ClassificationType.BINARY, data_type=DataType.TEXT)
    db.add(project)
    db.flush()
    settings = ProjectSettings(project_id=project.id, llm_provider=LLMProviderType.LOCAL, local_model_id="fake")
    db.add(settings)

    taxonomy = Taxonomy(project_id=project.id, name="T")
    db.add(taxonomy)
    db.flush()
    version = TaxonomyVersion(taxonomy_id=taxonomy.id, version_number=1, is_active=True, created_by="test")
    db.add(version)
    db.flush()
    label_a = Label(taxonomy_version_id=version.id, name="A", display_order=0)
    db.add(label_a)
    db.flush()

    record_ids = []
    for i in range(n_records):
        record = Record(dataset_id=1, project_id=project.id, text=f"text {i}")
        db.add(record)
        db.flush()
        record_ids.append(record.id)
    db.commit()
    return project, settings, record_ids, label_a.id


def _make_suggestion(db: Session, record_id: int, project_id: int, taxonomy_version_id: int, label_id: int, source) -> LabelSuggestion:
    s = LabelSuggestion(record_id=record_id, project_id=project_id, taxonomy_version_id=taxonomy_version_id, source=source)
    db.add(s)
    db.flush()
    db.execute(label_suggestion_labels.insert().values(suggestion_id=s.id, label_id=label_id))
    db.commit()
    return s


def test_agreeing_predictors_auto_label_when_trust_permits(db_session: Session, monkeypatch) -> None:
    project, settings, record_ids, label_id = _make_project_with_records(db_session, n_records=1)
    version_id = db_session.query(TaxonomyVersion).first().id

    def fake_classifier_sugg(db, proj, record):
        return _make_suggestion(db, record.id, proj.id, version_id, label_id, SuggestionSource.CLASSIFIER)

    def fake_llm_sugg(db, proj, settings, record):
        return _make_suggestion(db, record.id, proj.id, version_id, label_id, SuggestionSource.LLM)

    monkeypatch.setattr("app.services.suggestion_service.get_or_generate_classifier_suggestion", fake_classifier_sugg)
    monkeypatch.setattr("app.services.suggestion_service.get_or_generate_llm_suggestion", fake_llm_sugg)
    monkeypatch.setattr(
        "app.orchestration.orchestrator.assess_trust",
        lambda db, pid, s: TrustState(True, True, 50, 1.0, TrustTier.AUTO_LABEL, 0.0),  # audit_rate=0 -> never audit this call
    )

    action = orchestrator.decide_next_action(db_session, project, settings, record_ids)
    assert action.kind == "done"  # the only record got auto-labeled, nothing left to show a human

    auto_label = db_session.query(LabelSuggestion).filter_by(
        record_id=record_ids[0], source=SuggestionSource.AUTO_LABEL
    ).first()
    assert auto_label is not None


def test_disagreeing_predictors_never_auto_label(db_session: Session, monkeypatch) -> None:
    project, settings, record_ids, label_id = _make_project_with_records(db_session, n_records=1)
    version_id = db_session.query(TaxonomyVersion).first().id
    other_label = Label(taxonomy_version_id=version_id, name="B", display_order=1)
    db_session.add(other_label)
    db_session.commit()

    def fake_classifier_sugg(db, proj, record):
        return _make_suggestion(db, record.id, proj.id, version_id, label_id, SuggestionSource.CLASSIFIER)

    def fake_llm_sugg(db, proj, settings, record):
        return _make_suggestion(db, record.id, proj.id, version_id, other_label.id, SuggestionSource.LLM)

    monkeypatch.setattr("app.services.suggestion_service.get_or_generate_classifier_suggestion", fake_classifier_sugg)
    monkeypatch.setattr("app.services.suggestion_service.get_or_generate_llm_suggestion", fake_llm_sugg)
    monkeypatch.setattr(
        "app.orchestration.orchestrator.assess_trust",
        lambda db, pid, s: TrustState(True, True, 100, 0.99, TrustTier.HIGH_TRUST, 0.0),
    )

    action = orchestrator.decide_next_action(db_session, project, settings, record_ids)
    assert action.kind == "annotate"
    assert action.record_id == record_ids[0]

    auto_label = db_session.query(LabelSuggestion).filter_by(
        record_id=record_ids[0], source=SuggestionSource.AUTO_LABEL
    ).first()
    assert auto_label is None  # never auto-labeled, no matter how high trust is


def test_low_trust_shows_agreeing_record_to_human_anyway(db_session: Session, monkeypatch) -> None:
    project, settings, record_ids, label_id = _make_project_with_records(db_session, n_records=1)
    version_id = db_session.query(TaxonomyVersion).first().id

    def fake_sugg(db, proj, *rest):
        record = rest[-1]
        return _make_suggestion(db, record.id, proj.id, version_id, label_id, SuggestionSource.CLASSIFIER)

    monkeypatch.setattr("app.services.suggestion_service.get_or_generate_classifier_suggestion", fake_sugg)
    monkeypatch.setattr("app.services.suggestion_service.get_or_generate_llm_suggestion", fake_sugg)
    monkeypatch.setattr(
        "app.orchestration.orchestrator.assess_trust",
        lambda db, pid, s: TrustState(True, True, 10, None, TrustTier.ASSISTED, 1.0),
    )

    action = orchestrator.decide_next_action(db_session, project, settings, record_ids)
    assert action.kind == "annotate"
    assert action.record_id == record_ids[0]


def test_pending_audit_is_served_before_fresh_candidates(db_session: Session, monkeypatch) -> None:
    project, settings, record_ids, label_id = _make_project_with_records(db_session, n_records=2)
    version_id = db_session.query(TaxonomyVersion).first().id
    # record_ids[0] already has an AUTO_LABEL suggestion pending audit.
    _make_suggestion(db_session, record_ids[0], project.id, version_id, label_id, SuggestionSource.AUTO_LABEL)

    monkeypatch.setattr(
        "app.orchestration.orchestrator.assess_trust",
        lambda db, pid, s: TrustState(True, False, 50, 1.0, TrustTier.AUTO_LABEL, 1.0),  # rate=1.0 -> always audit
    )

    action = orchestrator.decide_next_action(db_session, project, settings, record_ids)
    assert action.kind == "audit"
    assert action.record_id == record_ids[0]
