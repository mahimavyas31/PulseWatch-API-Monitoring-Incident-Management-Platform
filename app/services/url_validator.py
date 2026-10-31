"""SSRF protection: PulseWatch makes requests to user-supplied URLs, so we must
refuse loopback, private, link-local (incl. cloud metadata 169.254.169.254) and
other non-public destinations."""
import ipaddress
import socket
from urllib.parse import ParseResult, urlparse

from app.config import settings


class UnsafeURLError(ValueError):
    pass


class UnresolvableHostError(UnsafeURLError):
    pass


def validate_syntax(url: str) -> ParseResult:
    try:
        parsed = urlparse(url.strip())
        parsed.port  # raises ValueError on a bad port
    except ValueError:
        raise UnsafeURLError("Invalid URL")
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError("URL must start with http:// or https://")
    if not parsed.hostname:
        raise UnsafeURLError("URL must include a host name")
    if parsed.username or parsed.password:
        raise UnsafeURLError("Credentials inside the URL are not allowed")
    return parsed


def _blocked(ip: ipaddress._BaseAddress) -> bool:
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return not ip.is_global or ip.is_multicast


def validate_destination(url: str) -> ParseResult:
    parsed = validate_syntax(url)
    if settings.allow_private_targets:
        return parsed
    host = parsed.hostname
    try:
        ips = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, parsed.port or 443, proto=socket.IPPROTO_TCP)
        except socket.gaierror:
            raise UnresolvableHostError(f"Cannot resolve host '{host}'")
        ips = [ipaddress.ip_address(i[4][0].split("%")[0]) for i in infos]
    for ip in ips:
        if _blocked(ip):
            raise UnsafeURLError(
                f"Destination {ip} is not allowed (private, loopback or reserved address)")
    return parsed
