import secrets
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils import as_utc, utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    status_slug: Mapped[str] = mapped_column(
        String(32), unique=True, index=True, default=lambda: secrets.token_urlsafe(8))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    monitors: Mapped[list["Monitor"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan")


class Monitor(Base):
    __tablename__ = "monitors"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    url: Mapped[str] = mapped_column(String(2048))
    interval_seconds: Mapped[int] = mapped_column(Integer, default=60)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=10)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expected_status: Mapped[str] = mapped_column(String(50), default="200-399")
    expected_body: Mapped[str | None] = mapped_column(String(255), nullable=True)
    webhook_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    owner: Mapped[User] = relationship(back_populates="monitors")
    checks: Mapped[list["CheckResult"]] = relationship(
        back_populates="monitor", cascade="all, delete-orphan")
    incidents: Mapped[list["Incident"]] = relationship(
        back_populates="monitor", cascade="all, delete-orphan")


class CheckResult(Base):
    __tablename__ = "check_results"
    __table_args__ = (Index("ix_check_monitor_time", "monitor_id", "checked_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    monitor_id: Mapped[int] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_success: Mapped[bool] = mapped_column(Boolean)
    error_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False)
    z_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    monitor: Mapped[Monitor] = relationship(back_populates="checks")


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    monitor_id: Mapped[int] = mapped_column(
        ForeignKey("monitors.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)  # open|resolved

    monitor: Mapped[Monitor] = relationship(back_populates="incidents")

    @property
    def duration_seconds(self) -> int:
        end = as_utc(self.resolved_at) or utcnow()
        return max(0, int((end - as_utc(self.started_at)).total_seconds()))
