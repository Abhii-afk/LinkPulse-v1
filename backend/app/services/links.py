import json
import secrets
import string
from collections.abc import Callable
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.campaign import Campaign
from app.models.link import Link
from app.schemas.link import CreateLinkRequest


LINK_CACHE_PREFIX = "link:"
LINK_CACHE_TTL_SECONDS = 60 * 60
CLICK_COUNT_PREFIX = "clicks:count:"
CLICK_STREAM_KEY = "stream:clicks"
GENERATED_ALIAS_LENGTH = 8
GENERATED_ALIAS_ATTEMPTS = 5
ALIAS_ALPHABET = string.ascii_lowercase + string.digits


class DuplicateAliasError(ValueError):
    """Raised when a requested or generated alias is already in use."""


class CampaignNotFoundError(ValueError):
    """Raised when a campaign is absent or owned by another user."""


class LinkCacheUnavailableError(RuntimeError):
    """Raised when routing metadata cannot be written to Redis."""


class AliasGenerationError(RuntimeError):
    """Raised when a generated alias cannot be made unique."""


def generate_short_code() -> str:
    return "".join(secrets.choice(ALIAS_ALPHABET) for _ in range(GENERATED_ALIAS_LENGTH))


def routing_metadata(link: Link) -> dict[str, object | None]:
    return {
        "id": str(link.id),
        "short_code": link.short_code,
        "destination_url": link.destination_url,
        "password_hash": link.password_hash,
        "has_password": link.password_hash is not None,
        "expires_at": link.expires_at.isoformat() if link.expires_at else None,
        "click_limit": link.click_limit,
        "total_clicks": link.total_clicks,
        "is_active": link.is_active,
        "is_abusive": link.is_abusive,
        "deactivated_at": link.deactivated_at.isoformat() if link.deactivated_at else None,
    }


async def _delete_cache_key(redis: Redis, key: str) -> None:
    try:
        await redis.delete(key)
    except RedisError:
        return


def link_cache_key(short_code: str) -> str:
    return f"{LINK_CACHE_PREFIX}{short_code}"


def click_count_key(short_code: str) -> str:
    return f"{CLICK_COUNT_PREFIX}{short_code}"


async def cache_link(redis: Redis, link: Link) -> None:
    """Cache routing metadata with the redirect engine's fixed TTL."""

    await redis.set(
        link_cache_key(link.short_code),
        json.dumps(routing_metadata(link)),
        ex=LINK_CACHE_TTL_SECONDS,
    )


async def invalidate_link_cache(redis: Redis, short_code: str) -> None:
    """Remove routing metadata so status changes take effect immediately."""

    await redis.delete(link_cache_key(short_code))


async def _campaign_for_user(
    db: AsyncSession,
    campaign_id: UUID,
    user_id: UUID,
) -> Campaign | None:
    result = await db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def create_link(
    *,
    payload: CreateLinkRequest,
    user_id: UUID,
    db: AsyncSession,
    redis: Redis,
    generate_alias: Callable[[], str] = generate_short_code,
) -> Link:
    if payload.campaign_id is not None:
        campaign = await _campaign_for_user(db, payload.campaign_id, user_id)
        if campaign is None:
            raise CampaignNotFoundError

    password_hash = hash_password(payload.rules.password) if payload.rules.password else None
    is_custom_alias = payload.custom_alias is not None

    for _ in range(GENERATED_ALIAS_ATTEMPTS):
        short_code = payload.custom_alias or generate_alias()
        existing = await db.execute(select(Link).where(Link.short_code == short_code))
        if existing.scalar_one_or_none() is not None:
            if is_custom_alias:
                raise DuplicateAliasError
            continue

        link = Link(
            user_id=user_id,
            campaign_id=payload.campaign_id,
            short_code=short_code,
            destination_url=str(payload.destination_url),
            password_hash=password_hash,
            expires_at=payload.rules.expires_at,
            click_limit=payload.rules.click_limit,
            total_clicks=0,
            is_active=True,
            is_abusive=False,
        )
        db.add(link)

        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            if is_custom_alias:
                raise DuplicateAliasError from None
            continue

        cache_key = link_cache_key(short_code)
        cache_written = False
        try:
            await redis.set(
                cache_key,
                json.dumps(routing_metadata(link)),
                ex=LINK_CACHE_TTL_SECONDS,
            )
            cache_written = True
        except RedisError as error:
            await db.rollback()
            raise LinkCacheUnavailableError from error

        try:
            await db.commit()
            await db.refresh(link)
        except IntegrityError:
            await db.rollback()
            if cache_written:
                await _delete_cache_key(redis, cache_key)
            if is_custom_alias:
                raise DuplicateAliasError from None
            continue

        return link

    raise AliasGenerationError
