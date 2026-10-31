import pytest

from app.services.url_validator import UnsafeURLError, validate_destination, validate_syntax


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/", "http://127.1.2.3:8080/", "http://10.1.2.3/", "http://172.16.0.1/",
    "http://192.168.0.1/", "http://169.254.169.254/", "http://0.0.0.0/", "http://[::1]/",
    "http://[::ffff:127.0.0.1]/", "http://100.64.0.1/", "http://localhost/",
])
def test_blocks_non_public_destinations(url):
    with pytest.raises(UnsafeURLError):
        validate_destination(url)


def test_allows_public_ip():
    assert validate_destination("https://8.8.8.8/x").hostname == "8.8.8.8"


@pytest.mark.parametrize("url", ["ftp://8.8.8.8", "file:///etc/passwd", "javascript:alert(1)",
                                 "http://", "8.8.8.8", "http://u:p@8.8.8.8/", "http://8.8.8.8:99999/"])
def test_rejects_bad_syntax(url):
    with pytest.raises(UnsafeURLError):
        validate_syntax(url)


def test_allow_private_flag(monkeypatch):
    monkeypatch.setattr("app.services.url_validator.settings.allow_private_targets", True)
    assert validate_destination("http://127.0.0.1:9000/").hostname == "127.0.0.1"
