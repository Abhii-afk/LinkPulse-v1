"""Redis sliding-window rate limiting (BLUEPRINT §12).

The link creation endpoints are limited to a fixed number of calls per minute
per client IP. The window is a true sliding window: every accepted call is
stored in a sorted set scored by its timestamp, and entries older than the
window are dropped before the count is taken. The whole check-and-record step
runs inside a single Lua script so concurrent requests cannot both pass the
limit.
"""

import time
import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.redis_client import get_redis


RATE_LIMIT_PREFIX = "ratelimit:"

# KEYS[1] window key
# ARGV[1] now in milliseconds
# ARGV[2] window length in milliseconds
# ARGV[3] maximum number of accepted calls
# ARGV[4] unique member for this call
# Returns {allowed, retry_after_seconds}
SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]

redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local count = redis.call('ZCARD', key)

if count >= limit then
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = math.ceil(window / 1000)
    if oldest[2] then
        retry_after = math.max(1, math.ceil((tonumber(oldest[2]) + window - now) / 1000))
    end
    return {0, retry_after}
end

redis.call('ZADD', key, now, member)
redis.call('PEXPIRE', key, window)
return {1, 0}
"""


class RateLimiterUnavailableError(RuntimeError):
    """Raised when the rate limiter itself cannot be reached."""


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int
    limit: int
    remaining: int


def rate_limit_key(scope: str, identifier: str) -> str:
    return f"{RATE_LIMIT_PREFIX}{scope}:{identifier}"


async def check_rate_limit(
    *,
    redis: Redis,
    scope: str,
    identifier: str,
    limit: int,
    window_seconds: int,
) -> RateLimitDecision:
    """Record one call against a sliding window and report the decision."""

    now_ms = int(time.time() * 1000)
    window_ms = window_seconds * 1000
    member = f"{now_ms}-{uuid.uuid4().hex}"

    result = await redis.eval(
        SLIDING_WINDOW_SCRIPT,
        1,
        rate_limit_key(scope, identifier),
        str(now_ms),
        str(window_ms),
        str(limit),
        member,
    )

    allowed = int(result[0]) == 1
    retry_after = int(result[1]) if len(result) > 1 else window_seconds
    return RateLimitDecision(
        allowed=allowed,
        retry_after_seconds=max(1, retry_after),
        limit=limit,
        remaining=max(0, limit - 1) if allowed else 0,
    )


def client_identifier(request: Request) -> str:
    """Identify the caller by the direct peer address.

    Forwarded headers are deliberately ignored: they are attacker controlled
    unless a trusted proxy is known to rewrite them.
    """

    client = request.client
    if client is None or not client.host:
        return "unknown"
    return client.host


async def enforce_rate_limit(
    *,
    request: Request,
    redis: Redis,
    scope: str,
    identifier: str,
    limit: int,
    window_seconds: int,
) -> RateLimitDecision:
    """Enforce a sliding-window limit or raise the matching HTTP error."""

    try:
        decision = await check_rate_limit(
            redis=redis,
            scope=scope,
            identifier=identifier,
            limit=limit,
            window_seconds=window_seconds,
        )
    except RedisError as error:
        raise RateLimiterUnavailableError from error

    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please retry later.",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )
    return decision


async def enforce_link_creation_rate_limit(
    request: Request,
    redis: Redis = Depends(get_redis),
) -> None:
    """Limit link creation calls per client IP (BLUEPRINT §12)."""

    try:
        await enforce_rate_limit(
            request=request,
            redis=redis,
            scope="links:create",
            identifier=client_identifier(request),
            limit=settings.rate_limit_link_creation_per_minute,
            window_seconds=settings.rate_limit_window_seconds,
        )
    except RateLimiterUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rate limiter unavailable",
        ) from None


async def enforce_password_attempt_rate_limit(
    *,
    request: Request,
    redis: Redis,
    short_code: str,
) -> None:
    """Limit password guessing attempts per client IP and short code."""

    identifier = f"{client_identifier(request)}:{short_code}"
    try:
        await enforce_rate_limit(
            request=request,
            redis=redis,
            scope="links:password",
            identifier=identifier,
            limit=settings.rate_limit_password_attempts_per_minute,
            window_seconds=settings.rate_limit_window_seconds,
        )
    except RateLimiterUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rate limiter unavailable",
        ) from None
