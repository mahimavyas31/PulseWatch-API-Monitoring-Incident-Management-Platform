# PulseWatch: API Monitoring and Incident Management Platform with Anomaly Detection

**Project report — B.Tech (Final Year)**
Name: [YOUR NAME] · Roll no.: [ROLL NO] · Guide: [GUIDE NAME] · Department: [DEPARTMENT] · Year: [YEAR]

---

## Abstract
Modern applications depend on many HTTP services, and an outage or slowdown in any of them must be
detected quickly. PulseWatch is a web platform that periodically checks user-registered endpoints,
stores their history, detects failures and unusual slowdowns, manages incidents from start to
recovery, and notifies owners by email or Slack-compatible webhooks. A public status page lets
service owners share health information without exposing internal details. The system is built
with Python, FastAPI, PostgreSQL and APScheduler, and is covered by an automated test suite.

## 1. Problem statement
When a payment API, login service or website stops responding, developers need to know which
service failed, when it failed and recovered, whether it is merely slow, and how often it happens.
Checking manually is unreliable, and simple "is it up?" scripts produce false alarms and no history.
**Objective:** build a secure, tested monitoring platform that (a) checks endpoints on a schedule,
(b) records history, (c) opens and resolves incidents without alert spam, (d) flags abnormal
response times, and (e) is safe to run when users supply arbitrary URLs.

## 2. Existing approaches and gap
Hosted uptime services and self-hosted tools such as Prometheus-based probes already exist. They
are powerful but are configuration-heavy or commercial, and their internals are opaque to a
student. This project does not aim to replace them; it implements the core ideas end to end
(scheduling, incident lifecycle, anomaly detection, SSRF-safe probing) in a small codebase that can
be understood, tested and extended.

## 3. System design
See `docs/architecture.md` and `docs/architecture.svg`.

- **Web process (FastAPI):** REST API, server-rendered dashboard, public status page.
- **Scheduler process (APScheduler):** selects due monitors every 10 s, runs checks in a thread pool,
  stores results, runs anomaly detection and incident logic.
- **PostgreSQL:** users, monitors, check results, incidents. Schema managed with Alembic migrations.
- **Alerting:** email (SMTP) and Slack-compatible webhooks.

### Key design decisions
| Decision | Reason |
|---|---|
| Separate scheduler process | Checks involve slow network calls and must never block API requests; each process can be restarted or scaled independently. Both share one codebase and database for simplicity (a modular monolith rather than microservices). |
| `max_instances=1`, `coalesce` | A slow tick must not overlap with the next one, which would duplicate checks. |
| Incident opens after 3 consecutive failures | One failed request is often a transient network glitch; requiring a streak reduces false alarms. Threshold is configurable. |
| One incident per outage | An open incident suppresses duplicates; the first success resolves it and records duration. |
| SSRF protection | The server fetches URLs chosen by users. Without validation a user could make it probe `localhost`, internal networks or cloud metadata (169.254.169.254). All non-public addresses are blocked, URLs with credentials and non-HTTP schemes are rejected, and redirects are not followed (a redirect could point to an internal address). Webhook URLs get the same validation, both when saved and when sent. |
| 404 instead of 403 for other users' data | Does not reveal that an ID exists. Ownership is enforced inside queries. |
| scrypt password hashing, JWT (API), HttpOnly cookie (dashboard) | Standard, salted, memory-hard hashing; no plaintext secrets; the browser session cannot be read by JavaScript. |
| Webhook URL never returned by the API | Slack webhook URLs act as secrets; the API only exposes `has_webhook`. |
| Public status page uses an unguessable slug and shows names only | Shares health without leaking monitored URLs. |

## 4. Anomaly detection
For each successful check with response time *x*, the baseline is the last *N* = 30 successful
response times. With mean μ and standard deviation σ (floored at 1 ms):

    z = (x − μ) / σ

A check is flagged as an anomaly if **z ≥ 3** and **x − μ ≥ 200 ms**. The second condition
prevents false alarms on very stable endpoints where σ is tiny. Only slowdowns are flagged. At
least 10 samples are required before detection starts. An alert is sent once at the start of a slow
streak, not for every slow check. Parameters are configurable.

**Limitation:** mean and standard deviation are sensitive to outliers in the baseline; a robust
alternative is median and MAD (median absolute deviation). A permanent level shift is gradually
absorbed into the baseline, which is intended.

## 5. Implementation summary
- Check expectations: accepted status codes (`200`, `200,204`, `200-299`) and an optional text the
  response body must contain (first 64 KB is read).
- Error classification: `timeout`, `connection_error`, `dns_error`, `blocked_url`, `http_error`,
  `body_mismatch`.
- Status model: UP, DEGRADED (slower than threshold), DOWN, UNKNOWN, PAUSED.
- Data retention: results older than 30 days are pruned.
- Tooling: Docker Compose (database, web, scheduler), GitHub Actions CI, Alembic migrations.

## 6. Testing
Automated tests with pytest (isolated in-memory database, external HTTP mocked so tests are
repeatable and offline). Categories: authentication; authorization (cross-user access denied);
input validation; SSRF blocking; failure modes (timeout, connection error, HTTP 500, blocked URL);
status/body expectations; anomaly detection; incident open/resolve logic; scheduler selection;
webhooks; public status page; migrations match models.

| Metric | Result |
|---|---|
| Total tests / passing | [RUN `pytest` AND FILL IN] |
| Code coverage | [RUN `pytest --cov=app --cov=scheduler` AND FILL IN] |

## 7. Performance
Load test with `scripts/loadtest.py` (see `docs/loadtest_results.md`).

| Scenario | Req/s | p95 latency | Errors |
|---|---|---|---|
| [FILL IN FROM loadtest_results.md] | | | |

Test setup: [CPU, RAM, PostgreSQL/SQLite, uvicorn workers].
Discussion: [Explain the slowest endpoint. `GET /monitors` runs extra queries per monitor — the
N+1 pattern — and could be optimised with a single aggregated query.]

## 8. Limitations
- The hostname is validated and then resolved again by the HTTP client, so DNS rebinding is
  theoretically possible; mitigation is to connect to the validated IP.
- No login rate limiting, CSRF tokens (only SameSite cookies) or email verification.
- Only HTTP GET checks; no custom headers, methods or multi-step checks.
- Anomaly detection is statistical, not learned, and uses one global setting per deployment.
- Single scheduler instance; running several would need job locking or a queue.

## 9. Future work
Rate limiting and e-mail verification · pinned-IP connections · robust (median/MAD) detection ·
per-monitor sensitivity · multi-region probes · Redis or Celery job queue · SLA reports.

## 10. Conclusion
PulseWatch demonstrates a complete backend system: secure authentication, a scheduled worker, a
carefully designed incident lifecycle, statistical anomaly detection, safe handling of
user-supplied URLs, migrations, containerised deployment and automated tests.

## References
1. FastAPI documentation — https://fastapi.tiangolo.com
2. SQLAlchemy and Alembic documentation — https://docs.sqlalchemy.org , https://alembic.sqlalchemy.org
3. APScheduler documentation — https://apscheduler.readthedocs.io
4. OWASP, *Server-Side Request Forgery Prevention Cheat Sheet* — https://cheatsheetseries.owasp.org
5. OWASP, *Password Storage Cheat Sheet* — https://cheatsheetseries.owasp.org
