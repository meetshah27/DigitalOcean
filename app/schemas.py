import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import settings

RESERVED_ALIASES = {"api", "docs", "redoc", "health", "ready", "links", "openapi.json"}
ALIAS_PATTERN = r"^[A-Za-z0-9_-]+$"


class LinkCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    custom_alias: str | None = Field(default=None, min_length=3, max_length=30)
    expires_at: datetime | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if len(v) > settings.max_url_length:
            raise ValueError(f"url must be at most {settings.max_url_length} characters")
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("url must start with http:// or https://")
        if not parsed.netloc:
            raise ValueError("url must include a host")
        return v

    @field_validator("custom_alias")
    @classmethod
    def validate_custom_alias(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not re.match(ALIAS_PATTERN, v):
            raise ValueError("custom_alias may only contain letters, digits, '-' and '_'")
        if v.lower() in RESERVED_ALIASES:
            raise ValueError(f"custom_alias {v!r} is reserved")
        return v

    @field_validator("expires_at", mode="before")
    @classmethod
    def reject_non_string_expires_at(cls, v: object) -> object:
        if v is not None and not isinstance(v, str):
            raise ValueError("expires_at must be an ISO-8601 string, not a number")
        return v

    @field_validator("expires_at")
    @classmethod
    def normalize_expires_at(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        if v.tzinfo is None:
            raise ValueError("expires_at must be a timezone-aware ISO-8601 datetime")
        return v.astimezone(timezone.utc)


class LinkResponse(BaseModel):
    code: str
    original_url: str
    created_at: datetime
    expires_at: datetime | None
    click_count: int


class LinkListResponse(BaseModel):
    items: list[LinkResponse]
    limit: int
    offset: int
