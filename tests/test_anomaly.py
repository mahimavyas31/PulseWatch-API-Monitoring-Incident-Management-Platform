from app.services import incident_manager
from app.services.anomaly import detect
from app.services.health_checker import CheckOutcome
from app.services.incident_manager import record_result
from tests.conftest import make_monitor

STABLE = [95, 105] * 10  # mean 100, std 5


def test_normal_value_is_not_anomalous():
    r = detect(STABLE, 108)
    assert r.is_anomaly is False and r.z_score is not None


def test_large_spike_is_anomalous():
    r = detect(STABLE, 1000)
    assert r.is_anomaly is True and r.z_score > 3


def test_not_enough_history_never_flags():
    r = detect([100] * 5, 5000)
    assert r.is_anomaly is False and r.z_score is None


def test_small_absolute_change_ignored_even_if_z_is_high():
    # std floor is 1 ms, so z for +50ms is huge, but 50ms < min_delta (200ms)
    assert detect([100] * 20, 150).is_anomaly is False


def test_faster_than_normal_is_not_flagged():
    assert detect(STABLE, 5).is_anomaly is False


def test_record_result_flags_and_alerts_once_per_streak(db, monkeypatch):
    alerts = []
    monkeypatch.setattr(incident_manager, "alert_anomaly", lambda m, r: alerts.append(r))
    m = make_monitor(db)
    for ms in STABLE:
        record_result(db, m, CheckOutcome(200, ms, True, None))
    assert alerts == []

    first = record_result(db, m, CheckOutcome(200, 1500, True, None))
    assert first.is_anomaly is True and first.z_score > 3
    record_result(db, m, CheckOutcome(200, 1600, True, None))
    assert len(alerts) == 1  # same slow streak -> no alert spam

    record_result(db, m, CheckOutcome(200, 100, True, None))  # back to normal ends the streak


def test_failed_checks_are_never_anomalies(db):
    m = make_monitor(db)
    r = record_result(db, m, CheckOutcome(None, None, False, "timeout"))
    assert r.is_anomaly is False and r.z_score is None
