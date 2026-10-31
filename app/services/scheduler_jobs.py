import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import CheckResult, Monitor
from app.services.checking import run_check
from app.services.incident_manager import record_result
from app.utils import as_utc, utcnow

logger = logging.getLogger(__name__)


def due_monitors(db: Session, now=None) -> list[Monitor]:
    now = now or utcnow()
    monitors = db.scalars(select(Monitor).where(Monitor.is_active.is_(True))).all()
    return [m for m in monitors
            if m.last_checked_at is None
            or (now - as_utc(m.last_checked_at)).total_seconds() >= m.interval_seconds]


def check_monitor(monitor_id: int) -> None:
    with SessionLocal() as db:
        monitor = db.get(Monitor, monitor_id)
        if monitor is None or not monitor.is_active:
            return
        record_result(db, monitor, run_check(monitor))


def _safe_check(monitor_id: int) -> None:
    try:
        check_monitor(monitor_id)
    except Exception:
        logger.exception("Check failed for monitor %s", monitor_id)


def run_due_checks() -> int:
    """One scheduler tick. Run with max_instances=1 so ticks never overlap."""
    with SessionLocal() as db:
        ids = [m.id for m in due_monitors(db)]
    if ids:
        with ThreadPoolExecutor(max_workers=settings.max_workers) as pool:
            list(pool.map(_safe_check, ids))
        logger.info("Ran %d checks", len(ids))
    return len(ids)


def prune_old_results() -> None:
    cutoff = utcnow() - timedelta(days=settings.retention_days)
    with SessionLocal() as db:
        db.execute(delete(CheckResult).where(CheckResult.checked_at < cutoff))
        db.commit()
