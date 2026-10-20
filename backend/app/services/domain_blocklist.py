import ipaddress
import re
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain_blocklist import DomainBlocklist


class InvalidBlockedDomainError(ValueError):
    """Raised when an administrator submits an invalid domain."""


class DomainAlreadyBlockedError(ValueError):
    """Raised when a normalized domain is already blocked."""


class BlockedDestinationError(ValueError):
    """Raised when a link destination matches a blocked domain."""

    def __init__(self, domain: str) -> None:
        self.domain = domain
        super().__init__(f"Destination domain '{domain}' is blocked")


_DOMAIN_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_MULTI_LABEL_SUFFIXES = {
    "com.au",
    "co.jp",
    "co.nz",
    "co.uk",
    "com.br",
    "com.cn",
    "com.mx",
    "com.sg",
    "co.za",
    "net.au",
    "org.au",
}
_SECOND_LEVEL_COUNTRY_LABELS = {"ac", "co", "com", "edu", "gov", "net", "org"}


def normalize_domain(value: str) -> str:
    candidate = value.strip()
    try:
        parsed = urlsplit(candidate if "://" in candidate else f"//{candidate}")
        hostname = parsed.hostname
    except ValueError as error:
        raise InvalidBlockedDomainError("Domain must contain a valid hostname") from error
    if hostname is None:
        raise InvalidBlockedDomainError("Domain must contain a valid hostname")

    try:
        hostname = hostname.encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError as error:
        raise InvalidBlockedDomainError("Domain must contain a valid hostname") from error

    try:
        ipaddress.ip_address(hostname)
        return hostname
    except ValueError:
        pass

    labels = hostname.split(".")
    if not hostname or len(hostname) > 253 or any(not _DOMAIN_LABEL.fullmatch(label) for label in labels):
        raise InvalidBlockedDomainError("Domain must contain a valid hostname")

    if len(labels) < 2:
        return hostname
    suffix = ".".join(labels[-2:])
    has_country_second_level = (
        len(labels) >= 3
        and len(labels[-1]) == 2
        and labels[-2] in _SECOND_LEVEL_COUNTRY_LABELS
    )
    root_label_count = (
        3
        if (suffix in _MULTI_LABEL_SUFFIXES or has_country_second_level) and len(labels) >= 3
        else 2
    )
    return ".".join(labels[-root_label_count:])


async def find_blocked_domain(
    *,
    destination_url: str,
    db: AsyncSession,
) -> DomainBlocklist | None:
    domain = normalize_domain(destination_url)
    result = await db.execute(select(DomainBlocklist).where(DomainBlocklist.domain == domain))
    return result.scalar_one_or_none()


async def add_blocked_domain(
    *,
    domain: str,
    reason: str,
    created_by: UUID,
    db: AsyncSession,
) -> DomainBlocklist:
    normalized_domain = normalize_domain(domain)
    result = await db.execute(
        select(DomainBlocklist).where(DomainBlocklist.domain == normalized_domain)
    )
    if result.scalar_one_or_none() is not None:
        raise DomainAlreadyBlockedError

    blocked_domain = DomainBlocklist(
        domain=normalized_domain,
        reason=reason,
        created_by=created_by,
    )
    db.add(blocked_domain)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise DomainAlreadyBlockedError from None
    await db.refresh(blocked_domain)
    return blocked_domain


async def list_blocked_domains(db: AsyncSession) -> list[DomainBlocklist]:
    result = await db.execute(select(DomainBlocklist).order_by(DomainBlocklist.domain))
    return list(result.scalars().all())
