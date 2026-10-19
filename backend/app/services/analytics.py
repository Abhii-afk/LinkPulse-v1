from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.click_event import ClickEvent
from app.models.link import Link
from app.schemas.analytics import (
    AnalyticsBreakdownItem,
    AnalyticsGranularity,
    AnalyticsResponse,
    AnalyticsScope,
    AnalyticsSummary,
    ClicksOverTimePoint,
    LinkAnalyticsInfo,
    TopLinkAnalytics,
)


@dataclass(frozen=True, slots=True)
class AnalyticsFilters:
    from_date: datetime | None
    to_date: datetime | None
    granularity: AnalyticsGranularity

    def event_conditions(
        self,
        *,
        owner_id: UUID | None,
        link_id: UUID | None,
    ) -> list[Any]:
        conditions: list[Any] = []
        if owner_id is not None:
            conditions.append(Link.user_id == owner_id)
        if link_id is not None:
            conditions.append(Link.id == link_id)
        if self.from_date is not None:
            conditions.append(ClickEvent.clicked_at >= self.from_date)
        if self.to_date is not None:
            conditions.append(ClickEvent.clicked_at < self.to_date)
        return conditions


def make_filters(
    *,
    from_date: datetime | None,
    to_date: datetime | None,
    granularity: str,
) -> AnalyticsFilters:
    if from_date is not None and (from_date.tzinfo is None or from_date.utcoffset() is None):
        raise ValueError("from must include a timezone")
    if to_date is not None and (to_date.tzinfo is None or to_date.utcoffset() is None):
        raise ValueError("to must include a timezone")
    if from_date is not None and to_date is not None and from_date >= to_date:
        raise ValueError("from must be earlier than to")
    if granularity not in {"hour", "day", "week"}:
        raise ValueError("granularity must be hour, day, or week")

    return AnalyticsFilters(
        from_date=from_date,
        to_date=to_date,
        granularity=granularity,  # type: ignore[assignment]
    )


def _as_int(value: Any) -> int:
    return int(value or 0)


def _row_value(row: Any, name: str, position: int) -> Any:
    try:
        return getattr(row, name)
    except AttributeError:
        return row[position]


def _optional_row_value(row: Any, name: str, position: int, default: Any = None) -> Any:
    try:
        return _row_value(row, name, position)
    except (IndexError, KeyError, TypeError):
        return default


def _link_status(link: Link) -> Literal["active", "disabled", "abusive", "expired"]:
    return _status_from_values(
        is_active=link.is_active,
        is_abusive=link.is_abusive,
        expires_at=link.expires_at,
    )


def _status_from_values(
    *,
    is_active: bool,
    is_abusive: bool,
    expires_at: datetime | None,
) -> Literal["active", "disabled", "abusive", "expired"]:
    if not is_active:
        return "disabled"
    if is_abusive:
        return "abusive"
    if expires_at is not None:
        expiration = expires_at
        if expiration.tzinfo is None or expiration.utcoffset() is None:
            expiration = expiration.replace(tzinfo=timezone.utc)
        if expiration <= datetime.now(timezone.utc):
            return "expired"
    return "active"


def _link_info(link: Link) -> LinkAnalyticsInfo:
    return LinkAnalyticsInfo(
        id=link.id,
        owner_id=link.user_id,
        short_code=link.short_code,
        status=_link_status(link),
        is_active=link.is_active,
        is_abusive=link.is_abusive,
        expires_at=link.expires_at,
        deactivated_at=link.deactivated_at,
    )


def _event_query(*columns: Any) -> Select[Any]:
    return select(*columns).select_from(ClickEvent).join(Link, Link.id == ClickEvent.link_id)


async def _breakdown(
    db: AsyncSession,
    statement: Select[Any],
    *,
    total_clicks: int,
) -> list[AnalyticsBreakdownItem]:
    rows = (await db.execute(statement)).all()
    if total_clicks == 0:
        return []
    return [
        AnalyticsBreakdownItem(
            value=str(_row_value(row, "value", 0)),
            clicks=_as_int(_row_value(row, "clicks", 1)),
            percentage=round(_as_int(_row_value(row, "clicks", 1)) * 100 / total_clicks, 2),
        )
        for row in rows
    ]


async def get_analytics(
    *,
    db: AsyncSession,
    owner_id: UUID | None,
    link_id: UUID | None,
    filters: AnalyticsFilters,
) -> AnalyticsResponse | None:
    link: Link | None = None
    if link_id is not None:
        link_conditions = [Link.id == link_id]
        if owner_id is not None:
            link_conditions.append(Link.user_id == owner_id)
        link_result = await db.execute(select(Link).where(*link_conditions))
        link = link_result.scalar_one_or_none()
        if link is None:
            return None

    link_conditions = []
    if owner_id is not None:
        link_conditions.append(Link.user_id == owner_id)
    if link_id is not None:
        link_conditions.append(Link.id == link_id)

    link_summary_result = await db.execute(
        select(
            func.count(Link.id).label("total_links"),
            func.count(Link.id).filter(Link.is_active.is_(True)).label("active_links"),
        ).where(*link_conditions)
    )
    link_summary = link_summary_result.one()

    event_conditions = filters.event_conditions(owner_id=owner_id, link_id=link_id)
    summary_result = await db.execute(
        _event_query(
            func.count(ClickEvent.id).label("total_clicks"),
            func.count(ClickEvent.id)
            .filter(ClickEvent.is_bot.is_(False))
            .label("human_clicks"),
            func.count(ClickEvent.id).filter(ClickEvent.is_bot.is_(True)).label("bot_clicks"),
            func.count(ClickEvent.id)
            .filter(ClickEvent.is_anomalous.is_(True))
            .label("anomalous_clicks"),
            func.count(func.distinct(ClickEvent.ip_address))
            .filter(ClickEvent.ip_address.is_not(None))
            .label("unique_visitors"),
        ).where(*event_conditions)
    )
    summary = summary_result.one()
    total_clicks = _as_int(_row_value(summary, "total_clicks", 0))

    bucket = func.date_trunc(filters.granularity, ClickEvent.clicked_at).label("bucket")
    time_series_result = await db.execute(
        _event_query(
            bucket,
            func.count(ClickEvent.id).label("clicks"),
            func.count(ClickEvent.id)
            .filter(ClickEvent.is_bot.is_(False))
            .label("human_clicks"),
            func.count(ClickEvent.id).filter(ClickEvent.is_bot.is_(True)).label("bot_clicks"),
        )
        .where(*event_conditions)
        .group_by(bucket)
        .order_by(bucket)
    )
    clicks_over_time = [
        ClicksOverTimePoint(
            bucket=_row_value(row, "bucket", 0),
            clicks=_as_int(_row_value(row, "clicks", 1)),
            human_clicks=_as_int(_row_value(row, "human_clicks", 2)),
            bot_clicks=_as_int(_row_value(row, "bot_clicks", 3)),
        )
        for row in time_series_result.all()
    ]

    device = func.coalesce(ClickEvent.device_type, "Unknown").label("value")
    browser = func.coalesce(ClickEvent.browser, "Unknown").label("value")
    device_breakdown = await _breakdown(
        db,
        _event_query(
            device,
            func.count(ClickEvent.id).label("clicks"),
        )
        .where(*event_conditions)
        .group_by(device)
        .order_by(func.count(ClickEvent.id).desc(), device)
        .limit(10),
        total_clicks=total_clicks,
    )
    browser_breakdown = await _breakdown(
        db,
        _event_query(
            browser,
            func.count(ClickEvent.id).label("clicks"),
        )
        .where(*event_conditions)
        .group_by(browser)
        .order_by(func.count(ClickEvent.id).desc(), browser)
        .limit(10),
        total_clicks=total_clicks,
    )

    top_links_result = await db.execute(
        _event_query(
            Link.id.label("link_id"),
            Link.short_code,
            func.count(ClickEvent.id).label("clicks"),
            Link.is_active,
            Link.is_abusive,
            Link.destination_url,
            Link.click_limit,
            Link.expires_at,
        )
        .where(*event_conditions)
        .group_by(
            Link.id,
            Link.short_code,
            Link.is_active,
            Link.is_abusive,
            Link.destination_url,
            Link.click_limit,
            Link.expires_at,
        )
        .order_by(func.count(ClickEvent.id).desc(), Link.short_code)
        .limit(10)
    )
    top_links = [
        TopLinkAnalytics(
            link_id=_row_value(row, "link_id", 0),
            short_code=str(_row_value(row, "short_code", 1)),
            clicks=_as_int(_row_value(row, "clicks", 2)),
            is_active=bool(_row_value(row, "is_active", 3)),
            is_abusive=bool(_row_value(row, "is_abusive", 4)),
            destination_url=_optional_row_value(row, "destination_url", 5),
            click_limit=_optional_row_value(row, "click_limit", 6),
            expires_at=_optional_row_value(row, "expires_at", 7),
            status=_status_from_values(
                is_active=bool(_row_value(row, "is_active", 3)),
                is_abusive=bool(_row_value(row, "is_abusive", 4)),
                expires_at=_optional_row_value(row, "expires_at", 7),
            ),
        )
        for row in top_links_result.all()
    ]

    return AnalyticsResponse(
        scope=AnalyticsScope(
            link_id=link_id,
            from_=filters.from_date,
            to=filters.to_date,
            granularity=filters.granularity,
        ),
        link=_link_info(link) if link is not None else None,
        summary=AnalyticsSummary(
            total_clicks=total_clicks,
            active_links=_as_int(_row_value(link_summary, "active_links", 1)),
            human_clicks=_as_int(_row_value(summary, "human_clicks", 1)),
            bot_clicks=_as_int(_row_value(summary, "bot_clicks", 2)),
            anomalous_clicks=_as_int(_row_value(summary, "anomalous_clicks", 3)),
            unique_visitors=_as_int(_row_value(summary, "unique_visitors", 4)),
        ),
        clicks_over_time=clicks_over_time,
        device_breakdown=device_breakdown,
        browser_breakdown=browser_breakdown,
        top_links=top_links,
    )
