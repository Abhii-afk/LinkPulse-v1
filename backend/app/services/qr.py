import re
from io import BytesIO
from uuid import UUID

import qrcode
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.link import Link


class LinkNotFoundError(ValueError):
    """Raised when a link is absent or owned by another user."""


def _download_filename(short_code: str) -> str:
    safe_short_code = re.sub(r"[^A-Za-z0-9_-]", "_", short_code)
    return f"link-{safe_short_code}.png"


async def generate_qr_code(
    *,
    short_code: str,
    owner_id: UUID,
    db: AsyncSession,
) -> tuple[bytes, str]:
    result = await db.execute(
        select(Link).where(
            Link.short_code == short_code,
            Link.user_id == owner_id,
        )
    )
    link = result.scalar_one_or_none()
    if link is None:
        raise LinkNotFoundError

    short_url = f"{settings.public_base_url.rstrip('/')}/{link.short_code}"
    qr_image = qrcode.make(short_url)
    image_buffer = BytesIO()
    qr_image.save(image_buffer, format="PNG")
    return image_buffer.getvalue(), _download_filename(link.short_code)
