# Load test results

**Not measured yet.** Run the load test against your running app:

```bash
docker compose up --build -d
python scripts/loadtest.py --base-url http://localhost:8000 --requests 1000 --concurrency 20
```

This file will be overwritten with real measurements (requests/second, average, p50/p95/p99
latency, errors). Only quote numbers that this script generated on your own machine, and state
your setup (CPU/RAM, PostgreSQL vs SQLite, number of uvicorn workers).

Expected finding to discuss: `GET /monitors` does extra queries per monitor to compute status and
uptime (an "N+1 query" pattern), so it should be noticeably slower than `/health`. Measuring this,
then optimising it (e.g. one aggregated query), is a strong before/after story for your report.
