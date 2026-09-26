import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401  (registers all tables on Base.metadata)
from app.api.deps import get_db
from app.config import get_settings
from app.database import Base
from app.main import app as fastapi_app


@pytest.fixture()
def db_session(monkeypatch: pytest.MonkeyPatch) -> Generator[Session, None, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        # import_service derives its uploads dir from settings.db_path at call
        # time, so pointing this at the same temp dir keeps uploaded files
        # (and anything else settings-derived) out of the real ./data dir.
        monkeypatch.setenv("LABELFORGE_DB_PATH", str(db_path))
        get_settings.cache_clear()

        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = TestSessionLocal()
        try:
            yield session
        finally:
            session.close()
            engine.dispose()
            get_settings.cache_clear()


@pytest.fixture()
def fake_llm(monkeypatch: pytest.MonkeyPatch):
    from tests.fakes import FakeLLMProvider

    provider = FakeLLMProvider()
    monkeypatch.setattr(
        "app.services.annotation_service.get_llm_provider", lambda settings: provider
    )
    monkeypatch.setattr(
        "app.services.prompt_service.get_llm_provider", lambda settings: provider
    )
    return provider


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_get_db
    with TestClient(fastapi_app) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()
