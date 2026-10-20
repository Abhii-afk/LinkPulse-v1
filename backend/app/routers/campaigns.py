from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import UserOrAdmin
from app.models.campaign import Campaign
from app.schemas.campaign import CampaignCreate, CampaignResponse


router = APIRouter(prefix="/api/v1/campaigns", tags=["campaigns"])


@router.get("", response_model=list[CampaignResponse])
async def list_campaigns(
    current_user: UserOrAdmin,
    db: AsyncSession = Depends(get_db),
) -> list[CampaignResponse]:
    """List the campaigns the signed in user owns."""

    result = await db.execute(
        select(Campaign)
        .where(Campaign.user_id == current_user.id)
        .order_by(Campaign.name)
    )
    return [
        CampaignResponse.model_validate(campaign, from_attributes=True)
        for campaign in result.scalars().all()
    ]


@router.post("", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CampaignCreate,
    current_user: UserOrAdmin,
    db: AsyncSession = Depends(get_db),
) -> CampaignResponse:
    """Create a campaign that links can be grouped under."""

    existing = await db.execute(
        select(Campaign).where(
            Campaign.user_id == current_user.id,
            Campaign.name == payload.name,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Campaign name already exists",
        )

    campaign = Campaign(
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)

    return CampaignResponse.model_validate(campaign, from_attributes=True)
