import httpx

from app.services.health_checker import perform_check
from app.services.stats import classify

URL = "http://8.8.8.8/"


def transport(handler):
    return httpx.MockTransport(handler)


def test_success():
    out = perform_check(URL, 5, transport(lambda req: httpx.Response(200)))
    assert out.is_success and out.status_code == 200 and out.error_type is None
    assert out.response_ms is not None and out.response_ms >= 0


def test_http_500_is_failure():
    out = perform_check(URL, 5, transport(lambda req: httpx.Response(500)))
    assert not out.is_success and out.status_code == 500 and out.error_type == "http_error"


def test_redirect_not_followed_counts_as_success():
    out = perform_check(URL, 5, transport(
        lambda req: httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})))
    assert out.status_code == 302 and out.is_success


def test_timeout():
    def handler(req):
        raise httpx.ConnectTimeout("too slow")
    out = perform_check(URL, 5, transport(handler))
    assert not out.is_success and out.error_type == "timeout" and out.status_code is None


def test_connection_error():
    def handler(req):
        raise httpx.ConnectError("refused")
    out = perform_check(URL, 5, transport(handler))
    assert out.error_type == "connection_error"


def test_blocked_url_never_sends_request():
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(200)

    out = perform_check("http://127.0.0.1/", 5, transport(handler))
    assert out.error_type == "blocked_url" and not out.is_success
    assert calls == []


def test_status_classification():
    assert classify(True, 100) == "up"
    assert classify(True, 99999) == "degraded"
    assert classify(False, None) == "down"
