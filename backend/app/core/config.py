"""Application settings, loaded from environment variables / a ``.env`` file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
INSECURE_DEFAULT_SECRET = "change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- General -----------------------------------------------------------------------
    app_name: str = "Real Estate AI Platform"
    environment: Literal["development", "test", "production"] = "development"
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    company_name: str = "Our Real Estate Team"

    # --- Database ----------------------------------------------------------------------
    database_url: str = f"sqlite:///{BACKEND_DIR / 'dev.db'}"
    auto_seed: bool = False  # seed demo (synthetic) data on startup if the DB is empty

    # --- Security ----------------------------------------------------------------------
    secret_key: SecretStr = SecretStr(INSECURE_DEFAULT_SECRET)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    cors_origins: list[str] = ["http://localhost:5173"]
    trust_proxy_headers: bool = False  # only enable behind a proxy you control
    seed_password: SecretStr | None = None  # password for seeded demo users

    # --- Rate limits (requests per minute, per client IP) ------------------------------
    rate_limit_global_per_minute: int = 300
    rate_limit_login_per_minute: int = 10
    rate_limit_chat_per_minute: int = 20

    # --- Machine learning --------------------------------------------------------------
    model_path: Path = BACKEND_DIR / "ml" / "artifacts" / "lead_model.joblib"
    hot_threshold: float = Field(0.50, gt=0, lt=1)  # at least a coin flip
    warm_threshold: float = Field(0.25, gt=0, lt=1)  # about the base conversion rate

    # --- LLM (optional) ----------------------------------------------------------------
    llm_provider: Literal["none", "anthropic"] = "none"
    anthropic_api_key: SecretStr | None = None
    llm_model: str = "claude-sonnet-5-5"
    llm_timeout_seconds: float = 30.0
    llm_max_tokens: int = 700

    # --- Retrieval ---------------------------------------------------------------------
    embedding_backend: Literal["tfidf", "sentence-transformers"] = "tfidf"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    @model_validator(mode="after")
    def _validate(self) -> Settings:
        if self.warm_threshold >= self.hot_threshold:
            raise ValueError("WARM_THRESHOLD must be lower than HOT_THRESHOLD")
        if self.environment == "production":
            secret = self.secret_key.get_secret_value()
            if secret == INSECURE_DEFAULT_SECRET or len(secret) < 32:
                raise ValueError("SECRET_KEY must be set to a random string of 32+ characters")
        return self

    @property
    def llm_enabled(self) -> bool:
        return self.llm_provider == "anthropic" and self.anthropic_api_key is not None


@lru_cache
def get_settings() -> Settings:
    return Settings()
