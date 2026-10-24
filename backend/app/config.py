"""Minimal environment-based configuration."""
from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    app_env: str = "production"
    log_level: str = "INFO"


def get_settings() -> Settings:
    # Fail closed for hosted deployments if APP_ENV is accidentally omitted.
    app_env = os.getenv("APP_ENV", "production").strip().lower()
    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    allowed_envs = {"development", "test", "production"}
    allowed_levels = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
    if app_env not in allowed_envs:
        raise ValueError("APP_ENV must be development, test, or production")
    if log_level not in allowed_levels:
        raise ValueError("LOG_LEVEL is invalid")
    return Settings(app_env=app_env, log_level=log_level)
