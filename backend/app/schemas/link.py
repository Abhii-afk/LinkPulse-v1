from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, field_validator


class LinkRules(BaseModel):
    password: str | None = Field(default=None, min_length=8, max_length=256)
    expires_at: datetime | None = None
    click_limit: int | None = Field(default=None, ge=1)

    @field_validator("expires_at")
    @classmethod
    def validate_expiration(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("expires_at must include a timezone")
        if value <= datetime.now(timezone.utc):
            raise ValueError("expires_at must be in the future")
        return value


class CreateLinkRequest(BaseModel):
    destination_url: HttpUrl
    custom_alias: str | None = Field(
        default=None,
        min_length=3,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
    )
    campaign_id: UUID | None = None
    rules: LinkRules = Field(default_factory=LinkRules)


class LinkResponse(BaseModel):
    id: UUID
    short_code: str
    short_url: str
    destination_url: str
    campaign_id: UUID | None
    expires_at: datetime | None
    click_limit: int | None
    total_clicks: int
    is_active: bool
    is_abusive: bool
    password_protected: bool
    created_at: datetime
