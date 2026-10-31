# ⚡ PulseWatch — API Monitoring & Incident Management

Register HTTP endpoints, check them on a schedule, track uptime and response times,
and get incidents + email alerts when a service goes down and when it recovers.

**Stack:** Python 3.12 · FastAPI · SQLAlchemy 2 · PostgreSQL (SQLite for quick local use) ·
HTTPX · APScheduler · Jinja2 + Bootstrap · Pytest · Docker · GitHub Actions

## Features
- Register/login (scrypt password hashing, JWT for the API, HttpOnly cookie for the dashboard)
- Monitor CRUD (pause / resume / delete), per-monitor interval and timeout
- **Anomaly detection**: flags unusually slow responses (rolling mean + std-dev z-score) and alerts once per slow streak
- **Custom expectations**: accepted status codes (`200`, `200,204`, `200-299`) and "body must contain" text
- **Slack-compatible webhooks** (and email) for incidents, recoveries and anomalies
- **Public status page** at `/status/<your-slug>` — shows only monitors you mark public, names only
- **Alembic migrations**; load-test script; architecture diagrams and a project report in `docs/`
- Status: **UP / DEGRADED / DOWN / UNKNOWN / PAUSED**, uptime % (24h, 7d), average response time
- Response-time chart, check history with pagination and filters (`since`, `success`)
- **Incidents**: opens after 3 consecutive failures (configurable), resolves on recovery, records duration
- Email alerts on open/resolve (optional SMTP; logs when not configured)
- Separate scheduler process; checks never overlap; one failing check never stops the others
- Old results pruned after 30 days (configurable)
- `GET /health` verifies the database connection
- **SSRF protection**: loopback, private, link-local (cloud metadata), reserved ranges are blocked;
  redirects are not followed; non-http(s) schemes and URLs with credentials are rejected
- Ownership enforced on every query (other users' IDs return 404)

## Quick start A — Docker (recommended)
```bash
cp .env.example .env              # optional; set SECRET_KEY to a long random string
docker compose up --build         # the web container runs `alembic upgrade head` first
```
Open http://localhost:8000 (dashboard) and http://localhost:8000/docs (API docs).
Compose runs Postgres, the web app, and the scheduler as three separate services.

## Quick start B — no Docker (SQLite)
```bash
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env
alembic upgrade head                                    # create/upgrade tables
uvicorn app.main:app --reload                           # terminal 1
# (shortcut for throw-away dev: AUTO_CREATE_TABLES=true skips alembic)
python -m scheduler.runner                              # terminal 2
```
Want to monitor something on `localhost`? Set `ALLOW_PRIVATE_TARGETS=true` (local dev only).

## Tests
```bash
pytest                                       # uses an isolated in-memory DB, no network
pytest --cov=app --cov=scheduler --cov-report=term-missing
```
Covers: auth, ownership/authorization, validation, SSRF blocking, checker failure modes
(timeout, connection error, HTTP 500, blocked URL) via mocked HTTP, incident open/resolve
logic, scheduler selection, pruning, health endpoint (incl. 503), and dashboard behaviour.

## Migrations
```bash
alembic upgrade head                                   # apply
alembic revision --autogenerate -m "describe change"   # after editing app/models.py
```
A test (`tests/test_migrations.py`) fails if the migrations and the models drift apart.

## Load test
```bash
python scripts/loadtest.py --base-url http://localhost:8000 --requests 1000 --concurrency 20
```
Writes measured results to `docs/loadtest_results.md`.

## Anomaly detection
Each successful check is compared with the last 30 successful response times:
`z = (x - mean) / std`. It is flagged when `z >= 3` **and** it is at least 200 ms slower than the
mean (tunable via `ANOMALY_*` settings). Flagged checks show ⚠️ in the dashboard and red points on
the chart; an alert is sent once at the start of a slow streak.

## API overview
| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/register`, `/auth/login` | Create account / get JWT |
| GET | `/auth/me` | Current user |
| GET/POST | `/monitors` | List / create |
| GET/PATCH/DELETE | `/monitors/{id}` | Detail / edit or pause / delete |
| GET | `/monitors/{id}/checks?limit&offset&since&success` | Paginated history |
| POST | `/monitors/{id}/check` | Run a check now |
| (body fields) | `expected_status`, `expected_body`, `webhook_url`, `is_public` | Set on create / PATCH |
| GET | `/status/{slug}` | Public status page (no login) |
| GET | `/incidents?status&monitor_id&limit&offset` | Incidents |
| GET | `/health` | App + DB health |

In `/docs`, click **Authorize** and paste the token from `/auth/login`.

## Architecture
Full diagrams: [`docs/architecture.md`](docs/architecture.md) · report: [`docs/REPORT.md`](docs/REPORT.md)

```
Browser ─► FastAPI (REST + dashboard) ─► PostgreSQL ◄─ Scheduler process (APScheduler)
                                                          └► health_checker ─► target URLs
                                                          └► incident_manager ─► alerts (SMTP)
```
```
app/
  api/         REST routers (auth, monitors, incidents, health)
  services/    health_checker, incident_manager, url_validator (SSRF), stats, alerts, scheduler_jobs
  web.py       Jinja2 dashboard routes      models.py / schemas.py / security.py / config.py
scheduler/runner.py   separate process
tests/
```

## Deploy
- **Any Docker host:** use `compose.yaml` as a reference; set a strong `SECRET_KEY`, `COOKIE_SECURE=true` behind HTTPS.
- **Render:** `render.yaml` is a Blueprint (web + worker + Postgres). Workers are a paid instance type;
  on the free tier remove the worker and set `EMBEDDED_SCHEDULER=true` — but free web services
  sleep when idle, so checks pause while asleep.

## Known limitations (be upfront about these in interviews)
- Hostname is validated and then resolved again by HTTPX, so a DNS-rebinding attack is theoretically possible. Mitigation: pin the resolved IP.
- No login rate limiting, no CSRF tokens (SameSite=Lax cookie only), no email verification.
- Each check does a single GET; no custom headers/methods/expected-body assertions.

## Ideas to extend
login rate limiting · pinned-IP requests (DNS-rebinding fix) · median/MAD anomaly detection ·
multi-region probes · Redis-backed job queue.
