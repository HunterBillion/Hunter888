"""Shared rate-limiter with proxy-aware IP resolution.

Behind a reverse proxy (nginx, Cloudflare, ALB) all requests arrive from the
proxy's IP.  ``get_remote_address`` returns that single IP, so every user
shares the same rate-limit bucket.

``get_client_ip`` reads the standard ``X-Forwarded-For`` / ``X-Real-IP``
headers first, falling back to the socket address.  Only the *leftmost*
entry of ``X-Forwarded-For`` is used (the one the edge proxy appends).
"""

import ipaddress
import logging
import re

from fastapi import Request
from slowapi import Limiter

logger = logging.getLogger(__name__)

# Trusted private ranges — we skip these when they appear in X-Forwarded-For
_TRUSTED_PRIVATE = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
)

_IP_PATTERN = re.compile(r"^[\d.:a-fA-F]+$")


def _is_private(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
        return any(addr in net for net in _TRUSTED_PRIVATE)
    except ValueError:
        return False


def get_client_ip(request: Request) -> str:
    """Extract the real client IP from proxy headers or socket.

    Priority:
      1. X-Forwarded-For — first *public* IP (leftmost non-private)
      2. X-Real-IP
      3. request.client.host (socket address)
    """
    # X-Forwarded-For: client, proxy1, proxy2
    xff = request.headers.get("x-forwarded-for")
    if xff:
        for part in xff.split(","):
            ip = part.strip()
            if _IP_PATTERN.match(ip) and not _is_private(ip):
                return ip
        # All private — return leftmost (local dev / internal network)
        first = xff.split(",")[0].strip()
        if _IP_PATTERN.match(first):
            return first

    # X-Real-IP (set by nginx)
    xri = request.headers.get("x-real-ip")
    if xri and _IP_PATTERN.match(xri.strip()):
        return xri.strip()

    # Fallback
    return request.client.host if request.client else "127.0.0.1"


# Shared limiter instance — import this instead of creating per-module.
# In development, disable rate limiting entirely (devs spam endpoints while testing,
# and localhost 127.0.0.1 is a single key_func bucket for the whole team).
from app.config import settings as _settings
limiter = Limiter(key_func=get_client_ip, enabled=(_settings.app_env != "development"))
