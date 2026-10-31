from tests.conftest import PUBLIC_URL


def register(client, email="web@example.com"):
    return client.post("/register", data={"email": email, "password": "password123"},
                       follow_redirects=False)


def test_dashboard_requires_login(client):
    r = client.get("/dashboard", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_register_login_and_add_monitor(client):
    r = register(client)
    assert r.status_code == 303 and "access_token" in r.headers["set-cookie"]
    assert "httponly" in r.headers["set-cookie"].lower()

    page = client.get("/dashboard")
    assert page.status_code == 200 and "Monitors" in page.text

    r = client.post("/dashboard/monitors", data={"name": "My API", "url": PUBLIC_URL,
                                                 "interval_seconds": 60, "timeout_seconds": 10},
                    follow_redirects=False)
    assert r.status_code == 303
    assert "My API" in client.get("/dashboard").text


def test_dashboard_rejects_private_url(client):
    register(client)
    r = client.post("/dashboard/monitors", data={"name": "x", "url": "http://127.0.0.1/"})
    assert r.status_code == 422 and "not allowed" in r.text


def test_html_is_escaped(client):
    register(client)
    client.post("/dashboard/monitors", data={"name": "<script>alert(1)</script>", "url": PUBLIC_URL})
    assert "<script>alert(1)</script>" not in client.get("/dashboard").text


def test_cannot_open_other_users_monitor_page(client):
    from fastapi.testclient import TestClient
    from app.main import app
    register(client, "one@example.com")
    client.post("/dashboard/monitors", data={"name": "secret-monitor", "url": PUBLIC_URL})
    other = TestClient(app)
    register(other, "two@example.com")
    r = other.get("/dashboard/monitors/1", follow_redirects=False)
    assert r.status_code == 303 and "secret-monitor" not in r.text


def test_login_logout(client):
    register(client)
    client.post("/logout")
    r = client.post("/login", data={"email": "web@example.com", "password": "bad-password"})
    assert r.status_code == 401
    r = client.post("/login", data={"email": "web@example.com", "password": "password123"},
                    follow_redirects=False)
    assert r.status_code == 303
