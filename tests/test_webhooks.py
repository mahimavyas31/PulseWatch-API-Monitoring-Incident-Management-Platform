from types import SimpleNamespace

from app.services import alerts
from app.services.health_checker import CheckOutcome
from app.services.incident_manager import record_result
from tests.conftest import PUBLIC_URL, make_monitor

FAIL = CheckOutcome(None, None, False, "timeout")
OK = CheckOutcome(200, 50, True, None)


def fake_monitor(webhook):
    return SimpleNamespace(name="svc", url="http://x", webhook_url=webhook,
                           owner=SimpleNamespace(email="a@example.com"))


def test_incident_sends_webhook_on_open_and_recovery(db, monkeypatch):
    sent = []
    monkeypatch.setattr(alerts, "_post_webhook", lambda url, payload: sent.append((url, payload)))
    m = make_monitor(db, webhook_url="http://8.8.8.8/hook")
    for _ in range(3):
        record_result(db, m, FAIL)
    record_result(db, m, OK)
    assert len(sent) == 2
    assert "DOWN" in sent[0][1]["text"] and "RECOVERED" in sent[1][1]["text"]
    assert sent[0][0] == "http://8.8.8.8/hook"


def test_no_webhook_means_no_post(db, monkeypatch):
    sent = []
    monkeypatch.setattr(alerts, "_post_webhook", lambda url, payload: sent.append(url))
    m = make_monitor(db)
    for _ in range(3):
        record_result(db, m, FAIL)
    assert sent == []


def test_webhook_to_internal_address_is_never_called(monkeypatch):
    sent = []
    monkeypatch.setattr(alerts, "_post_webhook", lambda url, payload: sent.append(url))
    alerts.notify(fake_monitor("http://169.254.169.254/latest"), "s", "b")
    assert sent == []


def test_webhook_failure_does_not_raise(monkeypatch):
    def boom(url, payload):
        raise RuntimeError("slack is down")
    monkeypatch.setattr(alerts, "_post_webhook", boom)
    alerts.notify(fake_monitor("http://8.8.8.8/hook"), "s", "b")  # must not raise


def test_api_validates_webhook_and_hides_url(client, auth):
    base = {"name": "x", "url": PUBLIC_URL}
    assert client.post("/monitors", json={**base, "webhook_url": "http://127.0.0.1/h"},
                       headers=auth).status_code == 422
    assert client.post("/monitors", json={**base, "webhook_url": "nonsense"},
                       headers=auth).status_code == 422
    r = client.post("/monitors", json={**base, "webhook_url": "https://8.8.8.8/secret-token"},
                    headers=auth)
    assert r.status_code == 201
    assert r.json()["has_webhook"] is True
    assert "secret-token" not in r.text
