import pytest
from app.config import get_settings


def test_defaults_fail_closed_to_production(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    settings = get_settings()
    assert settings.app_env == "production"
    assert settings.log_level == "INFO"


def test_invalid_environment_fails_closed(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production-ish")
    with pytest.raises(ValueError):
        get_settings()


def test_invalid_log_level_fails_closed(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LOG_LEVEL", "LOUD")
    with pytest.raises(ValueError):
        get_settings()
