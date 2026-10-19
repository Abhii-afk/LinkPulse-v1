from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import bcrypt
import jwt

from app.core.config import settings
from app.models.user import User


MIN_PASSWORD_LENGTH = 8
SUPPORTED_ROLES = {"visitor", "user", "admin"}


class InvalidTokenError(ValueError):
    """Raised when an access token cannot be trusted."""


def normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    local_part, separator, domain = normalized.partition("@")
    if not separator or not local_part or "." not in domain:
        raise ValueError("A valid email address is required")
    return normalized


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must contain at least {MIN_PASSWORD_LENGTH} characters")


def hash_password(password: str) -> str:
    validate_password(password)
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (TypeError, ValueError):
        return False


def _jwt_secret() -> str:
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET is not configured")
    return settings.jwt_secret


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "iat": now,
        "exp": expires_at,
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            _jwt_secret(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "email", "role", "iat", "exp"]},
        )
    except (jwt.PyJWTError, RuntimeError) as error:
        raise InvalidTokenError from error

    if not isinstance(payload.get("sub"), str) or not isinstance(payload.get("email"), str):
        raise InvalidTokenError
    if payload.get("role") not in SUPPORTED_ROLES:
        raise InvalidTokenError

    try:
        UUID(payload["sub"])
    except ValueError as error:
        raise InvalidTokenError from error

    return payload
