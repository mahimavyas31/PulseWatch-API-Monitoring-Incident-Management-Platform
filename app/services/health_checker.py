import time
from dataclasses import dataclass

import httpx

from app.services.url_validator import UnresolvableHostError, UnsafeURLError, validate_destination

DEFAULT_STATUS_SPEC = "200-399"
BODY_READ_LIMIT = 64 * 1024


@dataclass
class CheckOutcome:
    status_code: int | None
    response_ms: int | None
    is_success: bool
    # timeout | connection_error | dns_error | blocked_url | http_error | body_mismatch
    error_type: str | None


def parse_status_spec(spec: str) -> list[tuple[int, int]]:
    """'200' | '200,204' | '200-299' | '200-299,404' -> list of (low, high)."""
    ranges: list[tuple[int, int]] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            raise ValueError("empty entry in expected status list")
        lo_s, sep, hi_s = part.partition("-")
        if sep and not hi_s:
            raise ValueError(f"invalid status range '{part}'")
        try:
            lo = int(lo_s)
            hi = int(hi_s) if hi_s else lo
        except ValueError:
            raise ValueError(f"invalid status code '{part}'")
        if not (100 <= lo <= hi <= 599):
            raise ValueError(f"status codes must be within 100-599 (got '{part}')")
        ranges.append((lo, hi))
    return ranges


def status_matches(status: int, spec: str) -> bool:
    try:
        ranges = parse_status_spec(spec)
    except ValueError:
        ranges = parse_status_spec(DEFAULT_STATUS_SPEC)
    return any(lo <= status <= hi for lo, hi in ranges)


def _read_body(resp: httpx.Response) -> str:
    buf = bytearray()
    for chunk in resp.iter_bytes():
        buf += chunk
        if len(buf) >= BODY_READ_LIMIT:
            break
    return bytes(buf[:BODY_READ_LIMIT]).decode("utf-8", "replace")


def perform_check(url: str, timeout_seconds: float, transport: httpx.BaseTransport | None = None,
                  expected_status: str = DEFAULT_STATUS_SPEC,
                  expected_body: str | None = None) -> CheckOutcome:
    """Send one GET request. Redirects are NOT followed (a redirect could point at
    an internal address and bypass validation)."""
    try:
        validate_destination(url)
    except UnresolvableHostError:
        return CheckOutcome(None, None, False, "dns_error")
    except UnsafeURLError:
        return CheckOutcome(None, None, False, "blocked_url")

    start = time.perf_counter()
    body = ""
    try:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=False, transport=transport,
                          headers={"User-Agent": "PulseWatch/1.0"}) as client:
            # stream(): stop at headers (or 64 KB of body) instead of downloading everything
            with client.stream("GET", url) as resp:
                status = resp.status_code
                if expected_body and status_matches(status, expected_status):
                    body = _read_body(resp)
                elapsed = int((time.perf_counter() - start) * 1000)
    except httpx.TimeoutException:
        return CheckOutcome(None, None, False, "timeout")
    except httpx.RequestError:
        return CheckOutcome(None, None, False, "connection_error")

    if not status_matches(status, expected_status):
        return CheckOutcome(status, elapsed, False, "http_error")
    if expected_body and expected_body not in body:
        return CheckOutcome(status, elapsed, False, "body_mismatch")
    return CheckOutcome(status, elapsed, True, None)
