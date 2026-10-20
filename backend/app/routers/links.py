from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import UserOrAdmin
from app.core.redis_client import get_redis
from app.models.link import Link
from app.models.user import User
from app.schemas.link import BulkImportResponse, CreateLinkRequest, LinkResponse
from app.services.bulk import InvalidCsvError, import_links_from_csv
from app.services.qr import LinkNotFoundError, generate_qr_code
from app.services.links import (
    AliasGenerationError,
    CampaignNotFoundError,
    DuplicateAliasError,
    LinkCacheUnavailableError,
    create_link,
)


router = APIRouter(prefix="/api/v1/links", tags=["links"])


def link_response(link: Link) -> LinkResponse:
    return LinkResponse(
        id=link.id,
        short_code=link.short_code,
        short_url=f"{settings.public_base_url.rstrip('/')}/{link.short_code}",
        qr_code_url=(
            f"{settings.public_base_url.rstrip('/')}/api/v1/links/{link.short_code}/qr"
        ),
        destination_url=link.destination_url,
        campaign_id=link.campaign_id,
        expires_at=link.expires_at,
        click_limit=link.click_limit,
        total_clicks=link.total_clicks,
        is_active=link.is_active,
        is_abusive=link.is_abusive,
        password_protected=link.password_hash is not None,
        created_at=link.created_at,
    )


@router.post("", response_model=LinkResponse, status_code=status.HTTP_201_CREATED)
async def create_link_endpoint(
    payload: CreateLinkRequest,
    current_user: UserOrAdmin,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> LinkResponse:
    try:
        link = await create_link(
            payload=payload,
            user_id=current_user.id,
            db=db,
            redis=redis,
        )
    except CampaignNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        ) from None
    except DuplicateAliasError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Alias already in use",
        ) from None
    except LinkCacheUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Routing cache unavailable",
        ) from None
    except AliasGenerationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not allocate a short alias",
        ) from None

    return link_response(link)


@router.post("/bulk", response_model=BulkImportResponse)
async def bulk_import_endpoint(
    current_user: UserOrAdmin,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> BulkImportResponse:
    content = await file.read()
    try:
        return await import_links_from_csv(
            content=content,
            user_id=current_user.id,
            db=db,
            redis=redis,
        )
    except InvalidCsvError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from None


@router.get("/{short_code}/qr")
async def qr_code_endpoint(
    short_code: str,
    current_user: UserOrAdmin,
    db: AsyncSession = Depends(get_db),
) -> Response:
    try:
        image_bytes, filename = await generate_qr_code(
            short_code=short_code,
            owner_id=current_user.id,
            db=db,
        )
    except LinkNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link not found",
        ) from None

    return Response(
        content=image_bytes,
        media_type="image/png",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
        },
    )
