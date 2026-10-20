"""Short-lived HMAC-signed cookies for password-protected links.

BLUEPRINT §12 requires that a visitor who solves a link password receives a
short-lived HMAC-signed cookie so the browser is not asked for the password
again. The cookie value carries no secret of its own: it is an expiry stamp
plus an HMAC-SHA256 signature over the short code and that expiry.
"""

import hashlib
import hmac
import time

from app.core.config import settings
from app.core.security import SecurityConfigurationError


COOKIE_PREFIX = "auth_"


class LinkSessionConfigurationError(SecurityConfigurationError):
    """Raised when no signing key is available for link session cookies."""


def cookie_name(short_code: str) -> str:
    """Name of the per-link challenge cookie."""

    return f"{COOKIE_PREFIX}{short_code}"


def _signing_key() -> bytes:
    secret = settings.resolved_link_session_secret
    if not secret:
        raise LinkSessionConfigurationError(
            "LINK_SESSION_SECRET (or JWT_SECRET) is not configured"
        )
    return secret.encode("utf-8")


def _sign(short_code: str, expires_at: int) -> str:
    payload = f"{short_code}:{expires_at}".encode("utf-8")
    return hmac.new(_signing_key(), payload, hashlib.sha256).hexdigest()


def _now() -> int:
    return int(time.time())


def issue_link_session_token(short_code: str, *, ttl_seconds: int | None = None) -> str:
    """Create a signed, short-lived token for one short code."""

    lifetime = settings.link_session_ttl_seconds if ttl_seconds is None else ttl_seconds
    if lifetime < 1:
        raise LinkSessionConfigurationError("LINK_SESSION_TTL_SECONDS must be positive")
    expires_at = _now() + lifetime
    return f"{expires_at}.{_sign(short_code, expires_at)}"


def verify_link_session_token(token: str, short_code: str) -> bool:
    """Return True only for a correctly signed, unexpired token.

    The signature is bound to the short code, so a cookie issued for one
    protected link never unlocks another one.
    """

    if not isinstance(token, str) or not token:
        return False

    expires_at_raw, separator, signature = token.partition(".")
    if not separator:
        return False

    try:
        expires_at = int(expires_at_raw)
    except ValueError:
        return False

    if expires_at <= _now():
        return False

    try:
        expected = _sign(short_code, expires_at)
    except LinkSessionConfigurationError:
        return False

    return hmac.compare_digest(expected, signature)
