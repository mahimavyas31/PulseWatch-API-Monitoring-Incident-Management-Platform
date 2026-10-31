from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings

_url = make_url(settings.database_url)
_kwargs: dict = {"pool_pre_ping": True}
if _url.get_backend_name() == "sqlite":
    _kwargs["connect_args"] = {"check_same_thread": False}
    if _url.database in (None, "", ":memory:"):
        _kwargs["poolclass"] = StaticPool  # keep one in-memory DB (tests)

engine = create_engine(settings.database_url, **_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
