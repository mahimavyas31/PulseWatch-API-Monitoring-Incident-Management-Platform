from datetime import timedelta

from app.models import CheckResult, Monitor, User
from app.services import scheduler_jobs
from app.services.health_checker import CheckOutcome
from app.utils import utcnow


def test_due_monitor_selection(db):
    now = utcnow()
    user = User(email="a@example.com", password_hash="x")
    db.add(user)
    db.flush()

    def mon(name, **kw):
        m = Monitor(user_id=user.id, name=name, url="http://8.8.8.8/", interval_seconds=60, **kw)
        db.add(m)
        return m

    paused = mon("paused", is_active=False)
    never = mon("never")
    fresh = mon("fresh", last_checked_at=now - timedelta(seconds=5))
    stale = mon("stale", last_checked_at=now - timedelta(seconds=120))
    db.commit()

    due = {m.id for m in scheduler_jobs.due_monitors(db, now)}
    assert due == {never.id, stale.id}
    assert paused.id not in due and fresh.id not in due


def test_run_due_checks_records_results_and_skips_inactive(db, monkeypatch):
    user = User(email="a@example.com", password_hash="x")
    db.add(user)
    db.flush()
    active = Monitor(user_id=user.id, name="a", url="http://8.8.8.8/")
    paused = Monitor(user_id=user.id, name="p", url="http://8.8.4.4/", is_active=False)
    db.add_all([active, paused])
    db.commit()
    active_id = active.id

    monkeypatch.setattr("app.services.checking.perform_check",
                        lambda url, timeout, **kw: CheckOutcome(200, 10, True, None))
    assert scheduler_jobs.run_due_checks() == 1
    # immediately after, nothing is due (interval not elapsed) -> no overlap/duplicate checks
    assert scheduler_jobs.run_due_checks() == 0

    db.expire_all()
    results = db.query(CheckResult).all()
    assert len(results) == 1 and results[0].monitor_id == active_id


def test_one_failing_check_does_not_break_others(db, monkeypatch):
    user = User(email="a@example.com", password_hash="x")
    db.add(user)
    db.flush()
    db.add_all([Monitor(user_id=user.id, name="boom", url="http://8.8.8.8/"),
                Monitor(user_id=user.id, name="fine", url="http://8.8.4.4/")])
    db.commit()

    def fake(url, timeout, **kw):
        if "8.8.8.8" in url:
            raise RuntimeError("unexpected")
        return CheckOutcome(200, 10, True, None)

    monkeypatch.setattr("app.services.checking.perform_check", fake)
    scheduler_jobs.run_due_checks()
    assert db.query(CheckResult).count() == 1


def test_prune_old_results(db):
    user = User(email="a@example.com", password_hash="x")
    db.add(user)
    db.flush()
    m = Monitor(user_id=user.id, name="m", url="http://8.8.8.8/")
    db.add(m)
    db.flush()
    db.add_all([CheckResult(monitor_id=m.id, checked_at=utcnow() - timedelta(days=90), is_success=True),
                CheckResult(monitor_id=m.id, checked_at=utcnow(), is_success=True)])
    db.commit()
    scheduler_jobs.prune_old_results()
    db.expire_all()
    assert db.query(CheckResult).count() == 1
