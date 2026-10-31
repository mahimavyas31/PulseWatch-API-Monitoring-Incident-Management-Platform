import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.health_checker import parse_status_spec
from app.services.url_validator import UnsafeURLError, validate_syntax

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _check_email(v: str) -> str:
    v = v.strip().lower()
    if len(v) > 255 or not EMAIL_RE.match(v):
        raise ValueError("invalid email address")
    return v


def _check_url(v: str) -> str:
    try:
        validate_syntax(v)
    except UnsafeURLError as exc:
        raise ValueError(str(exc))
    return v.strip()


def _check_status_spec(v: str) -> str:
    v = v.strip()
    parse_status_spec(v)  # raises ValueError with a helpful message
    return v


def _blank_to_none(v):
    return None if v is None or not str(v).strip() else str(v).strip()


class UserCreate(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return _check_email(v)


class LoginIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str


class MonitorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(max_length=2048)
    interval_seconds: int = Field(60, ge=30, le=86400)
    timeout_seconds: int = Field(10, ge=1, le=30)
    expected_status: str = Field("200-399", max_length=50)
    expected_body: str | None = Field(None, max_length=255)
    webhook_url: str | None = Field(None, max_length=2048)
    is_public: bool = False

    @field_validator("url")
    @classmethod
    def check_url(cls, v: str) -> str:
        return _check_url(v)

    @field_validator("expected_status")
    @classmethod
    def check_status(cls, v: str) -> str:
        return _check_status_spec(v)

    @field_validator("expected_body", "webhook_url", mode="before")
    @classmethod
    def blank_to_none(cls, v):
        return _blank_to_none(v)

    @field_validator("webhook_url")
    @classmethod
    def check_webhook(cls, v):
        return None if v is None else _check_url(v)


class MonitorUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    url: str | None = Field(None, max_length=2048)
    interval_seconds: int | None = Field(None, ge=30, le=86400)
    timeout_seconds: int | None = Field(None, ge=1, le=30)
    is_active: bool | None = None
    expected_status: str | None = Field(None, max_length=50)
    expected_body: str | None = Field(None, max_length=255)
    webhook_url: str | None = Field(None, max_length=2048)
    is_public: bool | None = None

    @field_validator("url", "webhook_url")
    @classmethod
    def check_url(cls, v):
        return None if v is None else _check_url(v)

    @field_validator("expected_status")
    @classmethod
    def check_status(cls, v):
        return None if v is None else _check_status_spec(v)


class MonitorOut(BaseModel):
    id: int
    name: str
    url: str
    interval_seconds: int
    timeout_seconds: int
    is_active: bool
    expected_status: str
    expected_body: str | None
    has_webhook: bool  # the URL itself may contain a secret, so it is never returned
    is_public: bool
    last_checked_at: datetime | None
    created_at: datetime
    status: str  # up | degraded | down | unknown | paused
    uptime_24h: float | None


class CheckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    checked_at: datetime
    status_code: int | None
    response_ms: int | None
    is_success: bool
    error_type: str | None
    is_anomaly: bool
    z_score: float | None


class CheckPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[CheckOut]


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    monitor_id: int
    started_at: datetime
    resolved_at: datetime | None
    reason: str
    status: str
    duration_seconds: int
