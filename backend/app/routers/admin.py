from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import AdminUser
from app.core.redis_client import get_redis
from app.models.click_event import ClickEvent
from app.models.link import Link
from app.schemas.admin import (
    AdminLinkResponse,
    AdminLinkStatusResponse,
    DomainBlocklistCreate,
    DomainBlocklistResponse,
    LinkStatusUpdate,
)
from app.services.domain_blocklist import (
    DomainAlreadyBlockedError,
    InvalidBlockedDomainError,
    add_blocked_domain,
    list_blocked_domains,
)
from app.services.links import invalidate_link_cache, link_status


router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _link_status(link: Link) -> Literal["active", "disabled", "abusive", "expired"]:
    return link_status(link)


def _admin_link_response(link: Link, *, total_clicks: int | None = None) -> AdminLinkResponse:
    return AdminLinkResponse(
        id=link.id,
        owner_id=link.user_id,
        short_code=link.short_code,
        destination_url=link.destination_url,
        total_clicks=link.total_clicks if total_clicks is None else total_clicks,
        is_active=link.is_active,
        is_abusive=link.is_abusive,
        status=_link_status(link),
        deactivated_at=link.deactivated_at,
        deactivation_reason=link.deactivation_reason,
        created_at=link.created_at,
    )


@router.get("/access-check")
async def admin_access_check(current_user: AdminUser) -> dict[str, str]:
    return {"status": "authorized", "role": current_user.role}


@router.get("/links", response_model=list[AdminLinkResponse])
async def list_managed_links(
    _current_user: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> list[AdminLinkResponse]:
    result = await db.execute(
        select(Link, func.count(ClickEvent.id).label("total_clicks"))
        .outerjoin(ClickEvent, ClickEvent.link_id == Link.id)
        .group_by(Link.id)
        .order_by(Link.created_at.desc())
    )
    return [_admin_link_response(row[0], total_clicks=int(row[1])) for row in result.all()]


@router.get("/domains", response_model=list[DomainBlocklistResponse])
async def list_blocked_domains_endpoint(
    _current_user: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> list[DomainBlocklistResponse]:
    domains = await list_blocked_domains(db)
    return [
        DomainBlocklistResponse.model_validate(domain, from_attributes=True)
        for domain in domains
    ]


@router.post(
    "/domains",
    response_model=DomainBlocklistResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_blocked_domain_endpoint(
    payload: DomainBlocklistCreate,
    current_user: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> DomainBlocklistResponse:
    try:
        domain = await add_blocked_domain(
            domain=payload.domain,
            reason=payload.reason,
            created_by=current_user.id,
            db=db,
        )
    except InvalidBlockedDomainError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from None
    except DomainAlreadyBlockedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Domain is already blocked",
        ) from None

    return DomainBlocklistResponse.model_validate(domain, from_attributes=True)


@router.patch(
    "/links/{link_id}/status",
    response_model=AdminLinkStatusResponse,
)
async def update_link_status(
    link_id: UUID,
    payload: LinkStatusUpdate,
    _current_user: AdminUser,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> AdminLinkStatusResponse:
    result = await db.execute(select(Link).where(Link.id == link_id))
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

    if payload.is_active is not None:
        link.is_active = payload.is_active
    if payload.is_abusive is not None:
        link.is_abusive = payload.is_abusive
    if payload.is_abusive is True and payload.is_active is None:
        link.is_active = False
    if payload.reason is not None:
        link.deactivation_reason = payload.reason

    if not link.is_active or link.is_abusive:
        link.deactivated_at = datetime.now(timezone.utc)
    else:
        link.deactivated_at = None

    await db.commit()
    try:
        # Delete only after commit. A cold-cache redirect racing with this
        # update can then observe either the old state before the commit or
        # the disabled state after it; the final delete removes any old
        # metadata that was repopulated during the race.
        await invalidate_link_cache(redis, link.short_code)
    except RedisError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Routing cache unavailable",
        ) from None

    return AdminLinkStatusResponse(
        status="updated",
        link_id=link.id,
        is_active=link.is_active,
        is_abusive=link.is_abusive,
        reason=link.deactivation_reason,
        cache_cleared=True,
    )
