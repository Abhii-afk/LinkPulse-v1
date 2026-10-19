import json
from datetime import datetime, timezone
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.link import Link
from app.services.links import (
    CLICK_STREAM_KEY,
    cache_link,
    click_count_key,
    link_cache_key,
    routing_metadata,
)


# The counter check, reservation, and stream enqueue must be one Redis
# operation. Otherwise two concurrent requests can both observe the final
# available click and both redirect.
RESERVE_CLICK_SCRIPT = """
local current = redis.call('GET', KEYS[1])
if not current then
    current = ARGV[1]
    redis.call('SET', KEYS[1], current)
end

local limit = ARGV[2]
if limit ~= '' and tonumber(current) >= tonumber(limit) then
    return 0
end

local new_count = redis.call('INCR', KEYS[1])
redis.call('XADD', KEYS[2], '*', 'payload', ARGV[3])
return new_count
"""


class InvalidCachedLinkError(ValueError):
    """Raised when Redis contains malformed routing metadata."""


async def get_routing_metadata(
    *,
    short_code: str,
    redis: Redis,
    db: AsyncSession,
) -> dict[str, Any] | None:
    """Resolve a link from Redis, using PostgreSQL only on a cold-cache miss."""

    cached = await redis.get(link_cache_key(short_code))
    if cached is not None:
        try:
            metadata = json.loads(cached)
        except (TypeError, json.JSONDecodeError) as error:
            raise InvalidCachedLinkError from error
        if not isinstance(metadata, dict):
            raise InvalidCachedLinkError
        return metadata

    result = await db.execute(select(Link).where(Link.short_code == short_code))
    link = result.scalar_one_or_none()
    if link is None:
        return None

    await cache_link(redis, link)
    return routing_metadata(link)


def _initial_click_count(metadata: dict[str, Any]) -> int:
    try:
        return max(0, int(metadata.get("total_clicks") or 0))
    except (TypeError, ValueError):
        return 0


async def click_limit_reached(
    *,
    short_code: str,
    metadata: dict[str, Any],
    redis: Redis,
) -> bool:
    """Perform the pre-password limit check without reserving a click."""

    click_limit = metadata.get("click_limit")
    if click_limit is None:
        return False

    current = await redis.get(click_count_key(short_code))
    if current is None:
        current_count = _initial_click_count(metadata)
    else:
        try:
            current_count = int(current)
        except (TypeError, ValueError):
            current_count = _initial_click_count(metadata)

    return current_count >= int(click_limit)


async def reserve_click_and_enqueue(
    *,
    short_code: str,
    metadata: dict[str, Any],
    redis: Redis,
    event: dict[str, str],
) -> bool:
    """Atomically reserve a permitted click and append its stream event."""

    click_limit = metadata.get("click_limit")
    limit_argument = "" if click_limit is None else str(click_limit)
    payload = json.dumps(event, separators=(",", ":"))
    result = await redis.eval(
        RESERVE_CLICK_SCRIPT,
        2,
        click_count_key(short_code),
        CLICK_STREAM_KEY,
        str(_initial_click_count(metadata)),
        limit_argument,
        payload,
    )
    return int(result) > 0


def click_event(*, short_code: str, metadata: dict[str, Any], request: Any) -> dict[str, str]:
    client = getattr(request, "client", None)
    return {
        "short_code": short_code,
        "link_id": str(metadata.get("id", "")),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ip": client.host if client else "unknown",
        "user_agent": request.headers.get("user-agent", ""),
        "referrer": request.headers.get("referer", ""),
    }
