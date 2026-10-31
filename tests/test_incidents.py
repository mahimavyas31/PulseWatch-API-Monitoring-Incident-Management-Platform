from app.models import Incident, Monitor, User
from app.services.health_checker import CheckOutcome
from app.services.incident_manager import record_result

FAIL = CheckOutcome(None, None, False, "timeout")
OK = CheckOutcome(200, 50, True, None)


def make_monitor(db):
    user = User(email="a@example.com", password_hash="x")
    db.add(user)
    db.flush()
    m = Monitor(user_id=user.id, name="svc", url="http://8.8.8.8/")
    db.add(m)
    db.commit()
    return m


def test_no_incident_below_threshold(db):
    m = make_monitor(db)
    record_result(db, m, FAIL)
    record_result(db, m, FAIL)
    assert db.query(Incident).count() == 0


def test_incident_opens_after_three_failures_once(db):
    m = make_monitor(db)
    for _ in range(5):
        record_result(db, m, FAIL)
    incidents = db.query(Incident).all()
    assert len(incidents) == 1 and incidents[0].status == "open"
    assert incidents[0].reason.startswith("timeout")


def test_success_in_between_resets_the_streak(db):
    m = make_monitor(db)
    for outcome in [FAIL, FAIL, OK, FAIL, FAIL]:
        record_result(db, m, outcome)
    assert db.query(Incident).count() == 0


def test_incident_resolves_on_recovery(db):
    m = make_monitor(db)
    for _ in range(3):
        record_result(db, m, FAIL)
    record_result(db, m, OK)
    inc = db.query(Incident).one()
    assert inc.status == "resolved" and inc.resolved_at is not None
    assert inc.duration_seconds >= 0


def test_new_incident_after_recovery(db):
    m = make_monitor(db)
    for outcome in [FAIL, FAIL, FAIL, OK, FAIL, FAIL, FAIL]:
        record_result(db, m, outcome)
    assert db.query(Incident).count() == 2
    assert db.query(Incident).filter_by(status="open").count() == 1


def test_incidents_api_is_scoped_to_owner(client, auth, other, db):
    # create a monitor through the API for Alice and trigger an incident
    from tests.conftest import PUBLIC_URL
    mid = client.post("/monitors", json={"name": "x", "url": PUBLIC_URL}, headers=auth).json()["id"]
    monitor = db.get(Monitor, mid)
    for _ in range(3):
        record_result(db, monitor, FAIL)

    alice = client.get("/incidents", headers=auth).json()
    assert len(alice) == 1 and alice[0]["status"] == "open"
    assert client.get("/incidents", headers=other).json() == []
    assert client.get("/incidents?status=resolved", headers=auth).json() == []
    assert client.get("/incidents?status=bogus", headers=auth).status_code == 422
