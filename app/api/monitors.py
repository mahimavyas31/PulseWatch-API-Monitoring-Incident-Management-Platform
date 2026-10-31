from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CheckResult, Monitor, User
from app.schemas import CheckOut, CheckPage, MonitorCreate, MonitorOut, MonitorUpdate
from app.security import current_user
from app.services import stats
from app.services.checking import run_check
from app.services.incident_manager import record_result
from app.services.url_validator import UnsafeURLError, validate_destination

router = APIRouter(prefix="/monitors", tags=["monitors"])


def owned_monitor(db: Session, user: User, monitor_id: int) -> Monitor:
    """Ownership check. Returns 404 (not 403) so IDs of other users' data don't leak."""
    monitor = db.get(Monitor, monitor_id)
    if monitor is None or monitor.user_id != user.id:
        raise HTTPException(404, "Monitor not found")
    return monitor


def to_out(db: Session, m: Monitor) -> MonitorOut:
    return MonitorOut(
        id=m.id, name=m.name, url=m.url, interval_seconds=m.interval_seconds,
        timeout_seconds=m.timeout_seconds, is_active=m.is_active,
        expected_status=m.expected_status, expected_body=m.expected_body,
        has_webhook=bool(m.webhook_url), is_public=m.is_public,
        last_checked_at=m.last_checked_at, created_at=m.created_at,
        status=stats.current_status(db, m), uptime_24h=stats.uptime_percent(db, m.id))


def check_destination_or_422(url: str) -> None:
    try:
        validate_destination(url)
    except UnsafeURLError as exc:
        raise HTTPException(422, str(exc))


@router.get("", response_model=list[MonitorOut])
def list_monitors(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(select(Monitor).where(Monitor.user_id == user.id)
                      .order_by(Monitor.id)).all()
    return [to_out(db, m) for m in rows]


@router.post("", response_model=MonitorOut, status_code=201)
def create_monitor(body: MonitorCreate, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    check_destination_or_422(body.url)
    if body.webhook_url:
        check_destination_or_422(body.webhook_url)
    m = Monitor(user_id=user.id, **body.model_dump())
    db.add(m)
    db.commit()
    db.refresh(m)
    return to_out(db, m)


@router.get("/{monitor_id}", response_model=MonitorOut)
def get_monitor(monitor_id: int, db: Session = Depends(get_db),
                user: User = Depends(current_user)):
    return to_out(db, owned_monitor(db, user, monitor_id))


@router.patch("/{monitor_id}", response_model=MonitorOut)
def update_monitor(monitor_id: int, body: MonitorUpdate, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    m = owned_monitor(db, user, monitor_id)
    clearable = ("webhook_url", "expected_body")  # sending null clears these
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items()
               if v is not None or k in clearable}
    for key in ("url", "webhook_url"):
        if changes.get(key):
            check_destination_or_422(changes[key])
    for key, value in changes.items():
        setattr(m, key, value)
    db.commit()
    db.refresh(m)
    return to_out(db, m)


@router.delete("/{monitor_id}", status_code=204)
def delete_monitor(monitor_id: int, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    db.delete(owned_monitor(db, user, monitor_id))
    db.commit()


@router.get("/{monitor_id}/checks", response_model=CheckPage)
def list_checks(monitor_id: int, limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
                since: datetime | None = None, success: bool | None = None,
                anomaly: bool | None = None,
                db: Session = Depends(get_db), user: User = Depends(current_user)):
    owned_monitor(db, user, monitor_id)
    conditions = [CheckResult.monitor_id == monitor_id]
    if since is not None:
        conditions.append(CheckResult.checked_at >= since)
    if success is not None:
        conditions.append(CheckResult.is_success.is_(success))
    if anomaly is not None:
        conditions.append(CheckResult.is_anomaly.is_(anomaly))
    total = db.scalar(select(func.count(CheckResult.id)).where(*conditions))
    items = db.scalars(select(CheckResult).where(*conditions)
                       .order_by(CheckResult.id.desc()).limit(limit).offset(offset)).all()
    return CheckPage(total=total, limit=limit, offset=offset,
                     items=[CheckOut.model_validate(i) for i in items])


@router.post("/{monitor_id}/check", response_model=CheckOut)
def run_check_now(monitor_id: int, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    """Run a check immediately (handy for demos and debugging)."""
    m = owned_monitor(db, user, monitor_id)
    return record_result(db, m, run_check(m))
