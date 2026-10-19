from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import AdminUser
from app.core.redis_client import get_redis
from app.models.link import Link
from app.services.links import invalidate_link_cache


router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class LinkStatusUpdate(BaseModel):
    is_active: bool | None = None
    is_abusive: bool | None = None
    reason: str | None = None


@router.get("/access-check")
async def admin_access_check(current_user: AdminUser) -> dict[str, str]:
    return {"status": "authorized", "role": current_user.role}


@router.patch("/links/{link_id}/status")
async def update_link_status(
    link_id: UUID,
    payload: LinkStatusUpdate,
    _current_user: AdminUser,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict[str, object]:
    result = await db.execute(select(Link).where(Link.id == link_id))
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

    if payload.is_active is not None:
        link.is_active = payload.is_active
    if payload.is_abusive is not None:
        link.is_abusive = payload.is_abusive
    if not link.is_active or link.is_abusive:
        link.deactivated_at = datetime.now(timezone.utc)

    await db.commit()
    try:
        await invalidate_link_cache(redis, link.short_code)
    except RedisError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Routing cache unavailable",
        ) from None

    return {
        "status": "updated",
        "link_id": str(link.id),
        "is_active": link.is_active,
        "is_abusive": link.is_abusive,
        "cache_cleared": True,
    }
