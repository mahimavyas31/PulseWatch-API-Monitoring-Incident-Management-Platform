import os

# Must be set BEFORE the app is imported.
os.environ["DATABASE_URL"] = "sqlite://"  # in-memory, isolated from any real DB
os.environ["SECRET_KEY"] = "test-secret"
os.environ["ALLOW_PRIVATE_TARGETS"] = "false"
os.environ["SMTP_HOST"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

PUBLIC_URL = "http://8.8.8.8/health"  # IP literal: passes SSRF check without DNS


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client():
    return TestClient(app)  # not used as context manager -> lifespan not run


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def make_headers(client, email):
    client.post("/auth/register", json={"email": email, "password": "password123"})
    r = client.post("/auth/login", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def auth(client):
    return make_headers(client, "alice@example.com")


@pytest.fixture
def other(client):
    return make_headers(client, "bob@example.com")


def make_monitor(db, **kw):
    from app.models import Monitor, User
    user = db.query(User).first()
    if user is None:
        user = User(email="owner@example.com", password_hash="x")
        db.add(user)
        db.flush()
    m = Monitor(user_id=user.id, name=kw.pop("name", "svc"), url="http://8.8.8.8/", **kw)
    db.add(m)
    db.commit()
    return m
