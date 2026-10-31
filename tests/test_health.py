from app.database import get_db
from app.main import app


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_returns_503_when_db_down(client):
    class BrokenDB:
        def execute(self, *a, **k):
            raise RuntimeError("db down")

    app.dependency_overrides[get_db] = lambda: BrokenDB()
    try:
        assert client.get("/health").status_code == 503
    finally:
        app.dependency_overrides.clear()
