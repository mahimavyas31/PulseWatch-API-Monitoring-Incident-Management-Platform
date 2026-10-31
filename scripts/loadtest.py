"""Load test for PulseWatch (no extra dependencies beyond httpx).

Usage (app must be running):
    python scripts/loadtest.py --base-url http://localhost:8000 --requests 1000 --concurrency 20

It registers a throw-away user, seeds some monitors, hits several endpoints concurrently,
and writes MEASURED results to docs/loadtest_results.md. Nothing is hard-coded: quote
only the numbers this script produced on your machine.
"""
import argparse
import asyncio
import platform
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import httpx


def pct(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, max(0, round(p / 100 * len(sorted_values)) - 1))
    return sorted_values[idx]


async def run_scenario(base_url, name, method, path, headers, total, concurrency, json=None):
    latencies: list[float] = []
    counters = {"errors": 0}
    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=30) as client:

        async def one():
            async with sem:
                start = time.perf_counter()
                try:
                    r = await client.request(method, path, json=json)
                    ok = r.status_code < 400
                except httpx.HTTPError:
                    ok = False
                latencies.append((time.perf_counter() - start) * 1000)
                if not ok:
                    counters["errors"] += 1

        wall_start = time.perf_counter()
        await asyncio.gather(*[one() for _ in range(total)])
        wall = time.perf_counter() - wall_start

    latencies.sort()
    return {"name": name, "requests": total, "errors": counters["errors"],
            "rps": total / wall, "avg": sum(latencies) / len(latencies),
            "p50": pct(latencies, 50), "p95": pct(latencies, 95), "p99": pct(latencies, 99),
            "max": latencies[-1]}


async def main(args):
    async with httpx.AsyncClient(base_url=args.base_url, timeout=30) as c:
        email = f"load-{uuid.uuid4().hex[:8]}@example.com"
        creds = {"email": email, "password": "loadtest-password"}
        r = await c.post("/auth/register", json=creds)
        r.raise_for_status()
        token = (await c.post("/auth/login", json=creds)).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        for i in range(args.monitors):  # seed data so list endpoints do real work
            await c.post("/monitors", headers=headers,
                         json={"name": f"load-{i}", "url": f"http://8.8.8.{i % 200 + 1}/"})

    scenarios = [
        ("GET /health (DB ping)", "GET", "/health", {}, None),
        ("GET /auth/me (JWT verify + DB)", "GET", "/auth/me", headers, None),
        (f"GET /monitors ({args.monitors} monitors)", "GET", "/monitors", headers, None),
        ("GET /incidents", "GET", "/incidents", headers, None),
    ]
    results = []
    for name, method, path, hdrs, body in scenarios:
        print(f"running: {name} ...", flush=True)
        results.append(await run_scenario(args.base_url, name, method, path, hdrs,
                                          args.requests, args.concurrency, body))

    lines = [
        "# Load test results (measured)", "",
        f"- Date: {datetime.now():%Y-%m-%d %H:%M}",
        f"- Target: `{args.base_url}`",
        f"- Requests per scenario: {args.requests}, concurrency: {args.concurrency}",
        f"- Seeded monitors: {args.monitors}",
        f"- Client machine: {platform.platform()}, Python {sys.version.split()[0]}",
        "- Note: record your server setup here (CPU/RAM, SQLite vs PostgreSQL, uvicorn workers, "
        "Docker or not). Results are only meaningful with that context.", "",
        "| Scenario | Req/s | Avg ms | p50 ms | p95 ms | p99 ms | Max ms | Errors |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        lines.append(f"| {r['name']} | {r['rps']:.1f} | {r['avg']:.1f} | {r['p50']:.1f} | "
                     f"{r['p95']:.1f} | {r['p99']:.1f} | {r['max']:.1f} | {r['errors']}/{r['requests']} |")
    out = Path(__file__).resolve().parent.parent / "docs" / "loadtest_results.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nWritten to {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--requests", type=int, default=500)
    ap.add_argument("--concurrency", type=int, default=20)
    ap.add_argument("--monitors", type=int, default=20)
    asyncio.run(main(ap.parse_args()))
