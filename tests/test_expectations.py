import httpx
import pytest

from app.services.health_checker import parse_status_spec, perform_check, status_matches
from tests.conftest import PUBLIC_URL

URL = "http://8.8.8.8/"


def t(status=200, text=""):
    return httpx.MockTransport(lambda req: httpx.Response(status, text=text))


@pytest.mark.parametrize("spec,code,expected", [
    ("200", 200, True), ("200", 204, False), ("200,204", 204, True), ("200-299", 299, True),
    ("200-299", 300, False), ("200-299,404", 404, True), ("200-399", 302, True),
])
def test_status_matching(spec, code, expected):
    assert status_matches(code, spec) is expected


@pytest.mark.parametrize("bad", ["", "abc", "99", "600", "300-200", "200,", "200-"])
def test_invalid_specs_rejected(bad):
    with pytest.raises(ValueError):
        parse_status_spec(bad)


def test_custom_status_accepts_404_when_expected():
    out = perform_check(URL, 5, t(404), expected_status="404")
    assert out.is_success and out.status_code == 404


def test_200_fails_when_only_204_expected():
    out = perform_check(URL, 5, t(200), expected_status="204")
    assert not out.is_success and out.error_type == "http_error"


def test_body_check_pass_and_fail():
    ok = perform_check(URL, 5, t(200, '{"status":"healthy"}'), expected_body='"healthy"')
    assert ok.is_success
    bad = perform_check(URL, 5, t(200, '{"status":"degraded"}'), expected_body='"healthy"')
    assert not bad.is_success and bad.error_type == "body_mismatch" and bad.status_code == 200


def test_wrong_status_reported_before_body():
    out = perform_check(URL, 5, t(500, "healthy"), expected_body="healthy")
    assert out.error_type == "http_error"


def test_api_accepts_and_validates_expectations(client, auth):
    body = {"name": "x", "url": PUBLIC_URL, "expected_status": "200,204", "expected_body": "ok"}
    r = client.post("/monitors", json=body, headers=auth)
    assert r.status_code == 201
    assert r.json()["expected_status"] == "200,204" and r.json()["expected_body"] == "ok"
    for bad in ("abc", "700", ""):
        r = client.post("/monitors", json={**body, "expected_status": bad}, headers=auth)
        assert r.status_code == 422, bad
    mid = client.post("/monitors", json=body, headers=auth).json()["id"]
    r = client.patch(f"/monitors/{mid}", json={"expected_body": None}, headers=auth)
    assert r.json()["expected_body"] is None
