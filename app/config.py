import sys

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    db_path: str = Field(default="./data/app.db")
    base_url: str = Field(default="http://localhost:8000")
    code_length: int = Field(default=7, ge=4, le=32)
    max_url_length: int = Field(default=2048, ge=1, le=8192)
    log_level: str = Field(default="INFO")
    port: int = Field(default=8000, ge=1, le=65535)

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}, got {v!r}")
        return upper

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError(f"BASE_URL must start with http:// or https://, got {v!r}")
        return v.rstrip("/")


def load_settings() -> Settings:
    try:
        return Settings()
    except Exception as exc:
        sys.stderr.write(f"Invalid configuration: {exc}\n")
        raise SystemExit(1) from exc


settings = load_settings()
