def creds(email="a@example.com", password="password123"):
    return {"email": email, "password": password}


def test_register_and_login(client):
    r = client.post("/auth/register", json=creds())
    assert r.status_code == 201
    assert r.json()["email"] == "a@example.com"
    assert "password" not in r.json() and "password_hash" not in r.json()
    r = client.post("/auth/login", json=creds())
    assert r.status_code == 200 and r.json()["access_token"]


def test_duplicate_email_rejected(client):
    client.post("/auth/register", json=creds())
    assert client.post("/auth/register", json=creds()).status_code == 409


def test_email_is_case_insensitive(client):
    client.post("/auth/register", json=creds("Mixed@Example.com"))
    assert client.post("/auth/login", json=creds("mixed@example.com")).status_code == 200


def test_weak_password_and_bad_email_rejected(client):
    assert client.post("/auth/register", json=creds(password="short")).status_code == 422
    assert client.post("/auth/register", json=creds(email="nope")).status_code == 422


def test_wrong_password_and_unknown_user(client):
    client.post("/auth/register", json=creds())
    assert client.post("/auth/login", json=creds(password="wrongpass1")).status_code == 401
    assert client.post("/auth/login", json=creds("ghost@example.com")).status_code == 401


def test_protected_routes_need_token(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/monitors").status_code == 401
    assert client.get("/monitors", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_me(client, auth):
    r = client.get("/auth/me", headers=auth)
    assert r.status_code == 200 and r.json()["email"] == "alice@example.com"


def test_password_is_hashed_in_db(client, db):
    from app.models import User
    client.post("/auth/register", json=creds())
    user = db.query(User).one()
    assert user.password_hash != "password123"
    assert user.password_hash.startswith("scrypt$")
