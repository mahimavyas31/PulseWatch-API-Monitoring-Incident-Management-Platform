"""Anomaly detection on response times using a rolling mean and standard deviation.

For each new successful check we compare its response time with the last N
successful checks (the baseline):

    z = (value - mean) / std

A check is flagged when it is both statistically unusual (z >= threshold) AND
meaningfully slower in absolute terms (value - mean >= min_delta_ms). The second
condition avoids false alarms on very stable endpoints where std is tiny.
Only slowdowns are flagged (faster is not a problem).
"""
import statistics
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import CheckResult


@dataclass
class AnomalyResult:
    is_anomaly: bool
    z_score: float | None


def detect(history: list[int], value: int, z_threshold: float | None = None,
           min_samples: int | None = None, min_delta_ms: int | None = None) -> AnomalyResult:
    z_threshold = settings.anomaly_z_threshold if z_threshold is None else z_threshold
    min_samples = settings.anomaly_min_samples if min_samples is None else min_samples
    min_delta_ms = settings.anomaly_min_delta_ms if min_delta_ms is None else min_delta_ms

    if len(history) < min_samples:
        return AnomalyResult(False, None)  # not enough data to know what "normal" is
    mean = statistics.fmean(history)
    std = max(statistics.pstdev(history), 1.0)  # floor avoids division by ~0
    z = (value - mean) / std
    return AnomalyResult(z >= z_threshold and (value - mean) >= min_delta_ms, round(z, 2))


def recent_response_times(db: Session, monitor_id: int) -> list[int]:
    rows = db.scalars(
        select(CheckResult.response_ms)
        .where(CheckResult.monitor_id == monitor_id, CheckResult.is_success.is_(True),
               CheckResult.response_ms.is_not(None))
        .order_by(CheckResult.id.desc()).limit(settings.anomaly_window)).all()
    return list(rows)
