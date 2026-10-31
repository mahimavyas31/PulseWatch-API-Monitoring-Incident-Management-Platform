import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import models  # noqa: F401  (registers tables)
from app import web
from app.api import auth, health, incidents, monitors
from app.config import settings
from app.database import Base, engine

logging.basicConfig(level=settings.log_level,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_create_tables:  # dev shortcut; production runs `alembic upgrade head`
        Base.metadata.create_all(engine)
    sched = None
    if settings.embedded_scheduler:
        # Optional: run checks inside the web process (e.g. free hosting tiers).
        from apscheduler.schedulers.background import BackgroundScheduler
        from app.services.scheduler_jobs import run_due_checks
        sched = BackgroundScheduler(timezone="UTC")
        sched.add_job(run_due_checks, "interval", seconds=settings.scheduler_tick_seconds,
                      max_instances=1, coalesce=True)
        sched.start()
    yield
    if sched:
        sched.shutdown(wait=False)


app = FastAPI(title="PulseWatch", version="1.0.0",
              description="API monitoring & incident management", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(monitors.router)
app.include_router(incidents.router)
app.include_router(web.router)
