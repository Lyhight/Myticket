import pytest
from pydantic import ValidationError

from app.core.config import Settings


def settings_for_test(**overrides) -> Settings:
    values = {
        "database_url": "sqlite+aiosqlite://",
        "jwt_secret": "test-secret-that-is-longer-than-32-characters",
        "embedding_enabled": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_invalid_rag_depth_is_rejected_at_startup() -> None:
    with pytest.raises(ValidationError, match="rag_candidate_k"):
        settings_for_test(rag_top_k=8, rag_candidate_k=5)


def test_weak_jwt_secret_is_rejected_at_startup() -> None:
    with pytest.raises(ValidationError, match="jwt_secret"):
        settings_for_test(jwt_secret="too-short")


def test_debug_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEBUG", raising=False)

    assert settings_for_test().debug is False


def test_worker_lease_bounds_are_validated() -> None:
    with pytest.raises(ValidationError, match="agent_task_lease_seconds"):
        settings_for_test(agent_task_lease_seconds=5)
