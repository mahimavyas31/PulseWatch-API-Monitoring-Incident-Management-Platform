from datetime import timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import CheckResult
from app.utils import utcnow


def classify(is_success: bool, response_ms: int | None) -> str:
    if not is_success:
        return "down"
    if response_ms is not None and response_ms > settings.degraded_ms:
        return "degraded"
    return "up"


def latest_check(db: Session, monitor_id: int) -> CheckResult | None:
    return db.scalar(select(CheckResult).where(CheckResult.monitor_id == monitor_id)
                     .order_by(CheckResult.id.desc()).limit(1))


def current_status(db: Session, monitor) -> str:
    if not monitor.is_active:
        return "paused"
    last = latest_check(db, monitor.id)
    return "unknown" if last is None else classify(last.is_success, last.response_ms)


def uptime_percent(db: Session, monitor_id: int, hours: int = 24) -> float | None:
    since = utcnow() - timedelta(hours=hours)
    total, ok = db.execute(
        select(func.count(CheckResult.id),
               func.coalesce(func.sum(case((CheckResult.is_success, 1), else_=0)), 0))
        .where(CheckResult.monitor_id == monitor_id, CheckResult.checked_at >= since)).one()
    return None if not total else round(ok * 100 / total, 2)


def avg_response_ms(db: Session, monitor_id: int, hours: int = 24) -> int | None:
    since = utcnow() - timedelta(hours=hours)
    v = db.scalar(select(func.avg(CheckResult.response_ms)).where(
        CheckResult.monitor_id == monitor_id, CheckResult.is_success.is_(True),
        CheckResult.checked_at >= since))
    return None if v is None else int(v)
