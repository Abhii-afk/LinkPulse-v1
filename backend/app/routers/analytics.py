from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import AdminUser, UserOrAdmin
from app.models.user import UserRole
from app.schemas.analytics import AnalyticsGranularity, AnalyticsResponse
from app.services.analytics import get_analytics, make_filters


router = APIRouter(prefix="/api/v1", tags=["analytics"])


def _analytics_filters(
    *,
    from_date: datetime | None,
    to_date: datetime | None,
    granularity: AnalyticsGranularity,
):
    try:
        return make_filters(
            from_date=from_date,
            to_date=to_date,
            granularity=granularity,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error


async def _overview(
    *,
    db: AsyncSession,
    owner_id: UUID | None,
    from_date: datetime | None,
    to_date: datetime | None,
    granularity: AnalyticsGranularity,
) -> AnalyticsResponse:
    filters = _analytics_filters(
        from_date=from_date,
        to_date=to_date,
        granularity=granularity,
    )
    result = await get_analytics(
        db=db,
        owner_id=owner_id,
        link_id=None,
        filters=filters,
    )
    assert result is not None
    return result


@router.get("/analytics/overview", response_model=AnalyticsResponse)
async def user_analytics_overview(
    current_user: UserOrAdmin,
    db: AsyncSession = Depends(get_db),
    from_date: datetime | None = Query(default=None, alias="from"),
    to_date: datetime | None = Query(default=None, alias="to"),
    granularity: AnalyticsGranularity = Query(default="day"),
) -> AnalyticsResponse:
    return await _overview(
        db=db,
        owner_id=current_user.id,
        from_date=from_date,
        to_date=to_date,
        granularity=granularity,
    )


@router.get("/links/{link_id}/analytics", response_model=AnalyticsResponse)
async def link_analytics(
    link_id: UUID,
    current_user: UserOrAdmin,
    db: AsyncSession = Depends(get_db),
    from_date: datetime | None = Query(default=None, alias="from"),
    to_date: datetime | None = Query(default=None, alias="to"),
    granularity: AnalyticsGranularity = Query(default="day"),
) -> AnalyticsResponse:
    owner_id = None if current_user.role == UserRole.ADMIN.value else current_user.id
    filters = _analytics_filters(
        from_date=from_date,
        to_date=to_date,
        granularity=granularity,
    )
    result = await get_analytics(
        db=db,
        owner_id=owner_id,
        link_id=link_id,
        filters=filters,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
    return result


@router.get("/admin/analytics/overview", response_model=AnalyticsResponse)
async def admin_analytics_overview(
    _current_user: AdminUser,
    db: AsyncSession = Depends(get_db),
    from_date: datetime | None = Query(default=None, alias="from"),
    to_date: datetime | None = Query(default=None, alias="to"),
    granularity: AnalyticsGranularity = Query(default="day"),
) -> AnalyticsResponse:
    return await _overview(
        db=db,
        owner_id=None,
        from_date=from_date,
        to_date=to_date,
        granularity=granularity,
    )
