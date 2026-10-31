from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.database import Base

ROOT = Path(__file__).resolve().parent.parent


def test_migrations_match_models(tmp_path):
    """`alembic upgrade head` must produce exactly the tables/columns/indexes the models define."""
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    insp = inspect(create_engine(url))
    tables = {t for t in insp.get_table_names() if t != "alembic_version"}
    assert tables == set(Base.metadata.tables)
    for name, table in Base.metadata.tables.items():
        assert {c["name"] for c in insp.get_columns(name)} == {c.name for c in table.columns}, name
        model_idx = {i.name for i in table.indexes}
        db_idx = {i["name"] for i in insp.get_indexes(name)}
        assert model_idx <= db_idx, f"{name}: missing indexes {model_idx - db_idx}"

    command.downgrade(cfg, "base")
    assert not [t for t in inspect(create_engine(url)).get_table_names() if t != "alembic_version"]
