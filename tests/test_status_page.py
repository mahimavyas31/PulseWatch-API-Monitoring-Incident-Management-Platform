from app.models import User
from tests.conftest import PUBLIC_URL


def slug_of(db, email):
    return db.query(User).filter_by(email=email).one().status_slug


def test_public_page_shows_only_public_monitors_without_urls(client, auth, db):
    client.post("/monitors", json={"name": "Public API", "url": PUBLIC_URL, "is_public": True},
                headers=auth)
    client.post("/monitors", json={"name": "Secret Internal", "url": "http://8.8.4.4/private-path"},
                headers=auth)
    r = TestClientNoAuth(client).get(f"/status/{slug_of(db, 'alice@example.com')}")
    assert r.status_code == 200
    assert "Public API" in r.text
    assert "Secret Internal" not in r.text
    assert "8.8.8.8" not in r.text and "private-path" not in r.text


def TestClientNoAuth(client):
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)  # no cookies, no token


def test_unknown_slug_is_404(client):
    assert client.get("/status/does-not-exist").status_code == 404


def test_slugs_are_unique_and_unguessable(client, db):
    client.post("/auth/register", json={"email": "a@example.com", "password": "password123"})
    client.post("/auth/register", json={"email": "b@example.com", "password": "password123"})
    a, b = slug_of(db, "a@example.com"), slug_of(db, "b@example.com")
    assert a != b and len(a) >= 8


def test_toggle_public_from_dashboard(client, db):
    client.post("/register", data={"email": "w@example.com", "password": "password123"})
    client.post("/dashboard/monitors", data={"name": "Toggle Me", "url": PUBLIC_URL})
    slug = slug_of(db, "w@example.com")
    assert "Toggle Me" not in client.get(f"/status/{slug}").text
    client.post("/dashboard/monitors/1/public")
    assert "Toggle Me" in client.get(f"/status/{slug}").text
