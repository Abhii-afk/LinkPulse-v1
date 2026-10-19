from datetime import datetime, timezone
from html import escape
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis_client import get_redis
from app.services.redirect import (
    InvalidCachedLinkError,
    click_event,
    click_limit_reached,
    get_routing_metadata,
    reserve_click_and_enqueue,
)


router = APIRouter(tags=["redirect"])


def _html_failure(title: str) -> HTMLResponse:
    return HTMLResponse(content=f"<h1>{escape(title)}</h1>", status_code=status.HTTP_410_GONE)


def _is_expired(expires_at: Any) -> bool:
    if not expires_at:
        return False

    try:
        parsed = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
    except ValueError:
        # Invalid expiry metadata must fail closed rather than create an
        # accidentally permanent redirect.
        return True

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed <= datetime.now(timezone.utc)


def _password_challenge(short_code: str) -> HTMLResponse:
    safe_code = escape(short_code, quote=True)
    return HTMLResponse(
        content=(
            "<form method=\"post\" action=\"/api/v1/links/verify-password\">"
            f"<input type=\"hidden\" name=\"short_code\" value=\"{safe_code}\" />"
            "<input type=\"password\" name=\"password\" "
            "placeholder=\"Enter Link Password\" required />"
            "<button type=\"submit\">Access Destination</button>"
            "</form>"
        ),
        status_code=status.HTTP_401_UNAUTHORIZED,
    )


@router.get("/{short_code}")
async def execute_redirect(
    short_code: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> Response:
    try:
        metadata = await get_routing_metadata(short_code=short_code, redis=redis, db=db)
    except (RedisError, InvalidCachedLinkError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Routing cache unavailable",
        ) from None

    if metadata is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short link not found")

    # This order is part of the public redirect contract. Keep each check
    # separate so an earlier failure always wins over a later rule.
    if not metadata.get("is_active", False):
        return _html_failure("Link Inactive or Suspended")

    if metadata.get("is_abusive", False):
        return _html_failure("Link Inactive or Suspended")

    if _is_expired(metadata.get("expires_at")):
        return _html_failure("Link Expired")

    try:
        if await click_limit_reached(short_code=short_code, metadata=metadata, redis=redis):
            return _html_failure("Click Limit Reached")
    except RedisError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Routing cache unavailable",
        ) from None

    if metadata.get("has_password") or metadata.get("password_hash"):
        # Password verification belongs to the password challenge flow. The
        # redirect handler only accepts the already-issued, opaque session
        # cookie and never compares a submitted password with stored data.
        if not request.cookies.get(f"auth_{short_code}"):
            return _password_challenge(short_code)

    try:
        accepted = await reserve_click_and_enqueue(
            short_code=short_code,
            metadata=metadata,
            redis=redis,
            event=click_event(short_code=short_code, metadata=metadata, request=request),
        )
    except RedisError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Routing cache unavailable",
        ) from None

    if not accepted:
        return _html_failure("Click Limit Reached")

    return RedirectResponse(
        url=str(metadata["destination_url"]),
        status_code=status.HTTP_302_FOUND,
    )
