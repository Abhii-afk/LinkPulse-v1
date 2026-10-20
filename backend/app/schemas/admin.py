from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class LinkStatusUpdate(BaseModel):
    is_active: bool | None = None
    is_abusive: bool | None = None
    reason: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_action(self) -> "LinkStatusUpdate":
        if self.reason is not None:
            self.reason = self.reason.strip()
            if not self.reason:
                raise ValueError("Reason must not be blank")
        if self.is_active is None and self.is_abusive is None:
            raise ValueError("At least one link status field is required")
        if (
            self.is_active is False or self.is_abusive is True
        ) and self.reason is None:
            raise ValueError("A reason is required when disabling or marking a link abusive")
        return self


class AdminLinkResponse(BaseModel):
    id: UUID
    owner_id: UUID
    short_code: str
    destination_url: str
    total_clicks: int
    is_active: bool
    is_abusive: bool
    status: Literal["active", "disabled", "abusive", "expired"]
    deactivated_at: datetime | None
    deactivation_reason: str | None
    created_at: datetime


class DomainBlocklistCreate(BaseModel):
    domain: str = Field(min_length=1, max_length=255)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("domain", "reason")
    @classmethod
    def reject_blank_values(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Value must not be blank")
        return value.strip()


class DomainBlocklistResponse(BaseModel):
    id: UUID
    domain: str
    reason: str
    created_by: UUID
    created_at: datetime


class AdminLinkStatusResponse(BaseModel):
    status: Literal["updated"]
    link_id: UUID
    is_active: bool
    is_abusive: bool
    reason: str | None
    cache_cleared: bool
