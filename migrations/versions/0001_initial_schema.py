"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("status_slug", sa.String(32), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_status_slug", "users", ["status_slug"], unique=True)

    op.create_table(
        "monitors",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("interval_seconds", sa.Integer, nullable=False),
        sa.Column("timeout_seconds", sa.Integer, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("expected_status", sa.String(50), nullable=False, server_default="200-399"),
        sa.Column("expected_body", sa.String(255), nullable=True),
        sa.Column("webhook_url", sa.String(2048), nullable=True),
        sa.Column("is_public", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("last_checked_at", TZ, nullable=True),
        sa.Column("created_at", TZ, nullable=False),
    )
    op.create_index("ix_monitors_user_id", "monitors", ["user_id"])

    op.create_table(
        "check_results",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("monitor_id", sa.Integer, sa.ForeignKey("monitors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("checked_at", TZ, nullable=False),
        sa.Column("status_code", sa.Integer, nullable=True),
        sa.Column("response_ms", sa.Integer, nullable=True),
        sa.Column("is_success", sa.Boolean, nullable=False),
        sa.Column("error_type", sa.String(50), nullable=True),
        sa.Column("is_anomaly", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("z_score", sa.Float, nullable=True),
    )
    op.create_index("ix_check_monitor_time", "check_results", ["monitor_id", "checked_at"])

    op.create_table(
        "incidents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("monitor_id", sa.Integer, sa.ForeignKey("monitors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", TZ, nullable=False),
        sa.Column("resolved_at", TZ, nullable=True),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
    )
    op.create_index("ix_incidents_monitor_id", "incidents", ["monitor_id"])
    op.create_index("ix_incidents_status", "incidents", ["status"])


def downgrade() -> None:
    op.drop_table("incidents")
    op.drop_table("check_results")
    op.drop_table("monitors")
    op.drop_table("users")
