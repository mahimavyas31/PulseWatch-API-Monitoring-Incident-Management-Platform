from app.services.health_checker import CheckOutcome
from tests.conftest import PUBLIC_URL


def create(client, headers, **over):
    body = {"name": "API", "url": PUBLIC_URL, **over}
    return client.post("/monitors", json=body, headers=headers)


def test_crud_flow(client, auth):
    r = create(client, auth)
    assert r.status_code == 201
    mid = r.json()["id"]
    assert r.json()["status"] == "unknown" and r.json()["is_active"] is True

    assert len(client.get("/monitors", headers=auth).json()) == 1
    assert client.get(f"/monitors/{mid}", headers=auth).json()["name"] == "API"

    r = client.patch(f"/monitors/{mid}", json={"name": "Renamed", "is_active": False}, headers=auth)
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed" and r.json()["status"] == "paused"

    assert client.delete(f"/monitors/{mid}", headers=auth).status_code == 204
    assert client.get(f"/monitors/{mid}", headers=auth).status_code == 404


def test_validation_errors(client, auth):
    assert create(client, auth, url="not-a-url").status_code == 422
    assert create(client, auth, url="ftp://8.8.8.8/").status_code == 422
    assert create(client, auth, url="http://user:pw@8.8.8.8/").status_code == 422
    assert create(client, auth, interval_seconds=5).status_code == 422
    assert create(client, auth, timeout_seconds=500).status_code == 422
    assert create(client, auth, name="").status_code == 422


def test_ssrf_targets_blocked(client, auth):
    for url in ["http://127.0.0.1/", "http://localhost/", "http://10.0.0.5/",
                "http://192.168.1.1/", "http://169.254.169.254/latest/meta-data/",
                "http://[::1]/"]:
        r = create(client, auth, url=url)
        assert r.status_code == 422, url


def test_cannot_update_to_blocked_url(client, auth):
    mid = create(client, auth).json()["id"]
    r = client.patch(f"/monitors/{mid}", json={"url": "http://127.0.0.1/"}, headers=auth)
    assert r.status_code == 422


def test_ownership_is_enforced(client, auth, other):
    mid = create(client, auth).json()["id"]
    assert client.get("/monitors", headers=other).json() == []
    assert client.get(f"/monitors/{mid}", headers=other).status_code == 404
    assert client.patch(f"/monitors/{mid}", json={"name": "x"}, headers=other).status_code == 404
    assert client.delete(f"/monitors/{mid}", headers=other).status_code == 404
    assert client.get(f"/monitors/{mid}/checks", headers=other).status_code == 404
    assert client.post(f"/monitors/{mid}/check", headers=other).status_code == 404
    # still intact for the owner
    assert client.get(f"/monitors/{mid}", headers=auth).status_code == 200


def test_run_check_now_and_history(client, auth, monkeypatch):
    mid = create(client, auth).json()["id"]
    monkeypatch.setattr("app.services.checking.perform_check",
                        lambda url, timeout, **kw: CheckOutcome(200, 120, True, None))
    r = client.post(f"/monitors/{mid}/check", headers=auth)
    assert r.status_code == 200 and r.json()["is_success"] is True

    page = client.get(f"/monitors/{mid}/checks", headers=auth).json()
    assert page["total"] == 1 and page["items"][0]["response_ms"] == 120
    mon = client.get(f"/monitors/{mid}", headers=auth).json()
    assert mon["status"] == "up" and mon["uptime_24h"] == 100.0


def test_check_history_pagination_and_filter(client, auth, monkeypatch):
    mid = create(client, auth).json()["id"]
    results = iter([CheckOutcome(200, 50, True, None), CheckOutcome(None, None, False, "timeout"),
                    CheckOutcome(200, 60, True, None)])
    monkeypatch.setattr("app.services.checking.perform_check",
                        lambda url, timeout, **kw: next(results))
    for _ in range(3):
        client.post(f"/monitors/{mid}/check", headers=auth)

    page = client.get(f"/monitors/{mid}/checks?limit=2", headers=auth).json()
    assert page["total"] == 3 and len(page["items"]) == 2
    page2 = client.get(f"/monitors/{mid}/checks?limit=2&offset=2", headers=auth).json()
    assert len(page2["items"]) == 1
    failed = client.get(f"/monitors/{mid}/checks?success=false", headers=auth).json()
    assert failed["total"] == 1 and failed["items"][0]["error_type"] == "timeout"
    assert client.get(f"/monitors/{mid}/checks?limit=0", headers=auth).status_code == 422
