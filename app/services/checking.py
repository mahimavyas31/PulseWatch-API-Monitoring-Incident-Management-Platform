from app.models import Monitor
from app.services.health_checker import CheckOutcome, perform_check


def run_check(monitor: Monitor) -> CheckOutcome:
    """Run a check using the monitor's own settings (single place used by API, web, scheduler)."""
    return perform_check(monitor.url, monitor.timeout_seconds,
                         expected_status=monitor.expected_status,
                         expected_body=monitor.expected_body)
