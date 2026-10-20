from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import UserOrAdmin
from app.core.link_session import (
    LinkSessionConfigurationError,
    cookie_name,
    issue_link_session_token,
)
from app.core.rate_limit import (
    enforce_link_creation_rate_limit,
    enforce_password_attempt_rate_limit,
)
from app.core.redis_client import get_redis
from app.core.security import verify_password
from app.models.campaign import Campaign
from app.models.link import Link
from app.models.user import User
from app.schemas.link import BulkImportResponse, CreateLinkRequest, LinkListItem, LinkResponse
from app.services.bulk import InvalidCsvError, import_links_from_csv
from app.services.challenge import render_password_challenge
from app.services.domain_blocklist import BlockedDestinationError
from app.services.qr import LinkNotFoundError, generate_qr_code
from app.services.links import (
    AliasGenerationError,
    CampaignNotFoundError,
    DuplicateAliasError,
    InvalidDestinationError,
    LinkCacheUnavailableError,
    create_link,
    link_status,
)
from app.services.redirect import get_routing_metadata


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


@router.get("", response_model=list[LinkListItem])
async def list_own_links(
    current_user: UserOrAdmin,
    db: AsyncSession = Depends(get_db),
) -> list[LinkListItem]:
    """List the links the signed in user owns, newest first.

    The list is scoped to the owner, so a user never sees another user's
    links. Disabled and expired links stay in the list together with their
    history.
    """

    result = await db.execute(
        select(Link, Campaign.name)
        .outerjoin(Campaign, Campaign.id == Link.campaign_id)
        .where(Link.user_id == current_user.id)
        .order_by(Link.created_at.desc())
    )

    base_url = settings.public_base_url.rstrip("/")
    return [
        LinkListItem(
            id=link.id,
            short_code=link.short_code,
            short_url=f"{base_url}/{link.short_code}",
            qr_code_url=f"{base_url}/api/v1/links/{link.short_code}/qr",
            destination_url=link.destination_url,
            campaign_id=link.campaign_id,
            campaign_name=campaign_name,
            total_clicks=link.total_clicks,
            click_limit=link.click_limit,
            expires_at=link.expires_at,
            is_active=link.is_active,
            is_abusive=link.is_abusive,
            password_protected=link.password_hash is not None,
            status=link_status(link),
            created_at=link.created_at,
        )
        for link, campaign_name in result.all()
    ]


@router.post("", response_model=LinkResponse, status_code=status.HTTP_201_CREATED)
async def create_link_endpoint(
    payload: CreateLinkRequest,
    current_user: UserOrAdmin,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    _rate_limit: None = Depends(enforce_link_creation_rate_limit),
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
    except BlockedDestinationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from None
    except InvalidDestinationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Destination URL is invalid: {error}",
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
    _rate_limit: None = Depends(enforce_link_creation_rate_limit),
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


@router.post("/verify-password", status_code=status.HTTP_303_SEE_OTHER)
async def verify_link_password_endpoint(
    request: Request,
    short_code: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> Response:
    """Check a link password and issue the signed challenge cookie.

    This endpoint is public: it is the visitor facing half of the password
    challenge and never exposes the stored hash.
    """

    await enforce_password_attempt_rate_limit(
        request=request,
        redis=redis,
        short_code=short_code,
    )

    try:
        metadata = await get_routing_metadata(short_code=short_code, redis=redis, db=db)
    except (RedisError, ValueError):
        metadata = None

    stored_hash = metadata.get("password_hash") if metadata else None
    if not stored_hash:
        return HTMLResponse(
            content=render_password_challenge(
                short_code,
                "This link is not available or is not password protected.",
            ),
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if not verify_password(password, str(stored_hash)):
        return HTMLResponse(
            content=render_password_challenge(short_code, "Incorrect password."),
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        session_token = issue_link_session_token(short_code)
    except LinkSessionConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Link passwords are not configured",
        ) from None

    response = RedirectResponse(url=f"/{short_code}", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=cookie_name(short_code),
        value=session_token,
        max_age=settings.link_session_ttl_seconds,
        httponly=True,
        secure=settings.cookies_require_secure_transport,
        samesite="lax",
        path=f"/{short_code}",
    )
    return response


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
