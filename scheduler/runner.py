"""Separate scheduler process:  python -m scheduler.runner
Start the web app first (it creates the tables)."""
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler

from app.config import settings
from app.services.scheduler_jobs import prune_old_results, run_due_checks


def main() -> None:
    logging.basicConfig(level=settings.log_level,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    sched = BlockingScheduler(timezone="UTC")
    sched.add_job(run_due_checks, "interval", seconds=settings.scheduler_tick_seconds,
                  max_instances=1, coalesce=True, next_run_time=datetime.now(timezone.utc))
    sched.add_job(prune_old_results, "interval", hours=6, max_instances=1, coalesce=True)
    logging.getLogger(__name__).info("PulseWatch scheduler started")
    sched.start()


if __name__ == "__main__":
    main()
