from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import CheckResult, Incident, Monitor
from app.services import stats
from app.services.alerts import alert_anomaly, alert_incident
from app.services.anomaly import AnomalyResult, detect, recent_response_times
from app.services.health_checker import CheckOutcome
from app.utils import utcnow


def _recent_failures(db: Session, monitor_id: int, n: int) -> bool:
    rows = db.scalars(
        select(CheckResult.is_success).where(CheckResult.monitor_id == monitor_id)
        .order_by(CheckResult.id.desc()).limit(n)).all()
    return len(rows) == n and not any(rows)


def record_result(db: Session, monitor: Monitor, outcome: CheckOutcome, now=None) -> CheckResult:
    """Store a check, run anomaly detection, then open/resolve incidents.
    An incident opens after `failure_threshold` consecutive failures and resolves
    on the next success. An anomaly alert fires once at the START of a slow streak."""
    now = now or utcnow()

    anomaly, prev_anomalous = AnomalyResult(False, None), False
    if outcome.is_success and outcome.response_ms is not None:
        anomaly = detect(recent_response_times(db, monitor.id), outcome.response_ms)
        prev = stats.latest_check(db, monitor.id)
        prev_anomalous = bool(prev and prev.is_anomaly)

    result = CheckResult(monitor_id=monitor.id, checked_at=now, status_code=outcome.status_code,
                         response_ms=outcome.response_ms, is_success=outcome.is_success,
                         error_type=outcome.error_type, is_anomaly=anomaly.is_anomaly,
                         z_score=anomaly.z_score)
    db.add(result)
    monitor.last_checked_at = now
    db.flush()

    open_incident = db.scalar(select(Incident).where(
        Incident.monitor_id == monitor.id, Incident.status == "open"))
    event, incident = None, open_incident

    if outcome.is_success:
        if open_incident:
            open_incident.status = "resolved"
            open_incident.resolved_at = now
            event = "resolved"
    elif open_incident is None and _recent_failures(db, monitor.id, settings.failure_threshold):
        reason = outcome.error_type or "http_error"
        if outcome.status_code:
            reason = f"{reason} (HTTP {outcome.status_code})"
        incident = Incident(monitor_id=monitor.id, started_at=now, reason=reason, status="open")
        db.add(incident)
        event = "opened"

    db.commit()
    if event:
        alert_incident(monitor, incident, event)
    if anomaly.is_anomaly and not prev_anomalous and event != "resolved":
        alert_anomaly(monitor, result)
    return result
