from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


AnalyticsGranularity = Literal["hour", "day", "week"]


class AnalyticsScope(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    link_id: UUID | None = None
    from_: datetime | None = Field(default=None, alias="from")
    to: datetime | None = None
    granularity: AnalyticsGranularity


class AnalyticsSummary(BaseModel):
    total_clicks: int
    active_links: int
    human_clicks: int
    bot_clicks: int
    anomalous_clicks: int
    unique_visitors: int


class ClicksOverTimePoint(BaseModel):
    bucket: datetime
    clicks: int
    human_clicks: int
    bot_clicks: int


class AnalyticsBreakdownItem(BaseModel):
    value: str
    clicks: int
    percentage: float


class TopLinkAnalytics(BaseModel):
    link_id: UUID
    short_code: str
    clicks: int
    is_active: bool
    is_abusive: bool
    destination_url: str | None = None
    click_limit: int | None = None
    expires_at: datetime | None = None
    status: Literal["active", "disabled", "abusive", "expired"] = "active"


class LinkAnalyticsInfo(BaseModel):
    id: UUID
    owner_id: UUID
    short_code: str
    status: Literal["active", "disabled", "abusive", "expired"]
    is_active: bool
    is_abusive: bool
    expires_at: datetime | None
    deactivated_at: datetime | None


class AnalyticsResponse(BaseModel):
    scope: AnalyticsScope
    link: LinkAnalyticsInfo | None
    summary: AnalyticsSummary
    clicks_over_time: list[ClicksOverTimePoint]
    device_breakdown: list[AnalyticsBreakdownItem]
    browser_breakdown: list[AnalyticsBreakdownItem]
    top_links: list[TopLinkAnalytics]
