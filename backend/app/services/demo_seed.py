"""Reproducible demo seed data for LinkPulse.

The seed creates a small, believable workspace:

* one administrator and one demo user
* four campaigns
* six links that cover every status the dashboard can show
* two weeks of click history so the analytics charts have shape

Running it twice leaves the same result: rows are matched on their natural
key and updated in place. Nothing is hard deleted except through
:func:`reset_demo_data`, which only touches the rows this module created.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.campaign import Campaign
from app.models.click_event import ClickEvent
from app.models.link import Link
from app.models.user import User, UserRole
from app.services.links import cache_link, routing_metadata
from app.services.user_agent import parse_user_agent


ADMIN_EMAIL = "admin@linkpulse.local"
DEMO_USER_EMAIL = "demo@linkpulse.local"
DEMO_USER_PASSWORD = "demo-password-123"
ADMIN_PASSWORD = "admin-password-123"
LINK_PASSWORD = "link-password-123"

CHROME_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
SAFARI_IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
FIREFOX_WINDOWS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) "
    "Gecko/20100101 Firefox/126.0"
)
CHROME_TABLET = (
    "Mozilla/5.0 (Linux; Android 14; Pixel Tablet) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
GOOGLEBOT = (
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)
CURL_AGENT = "curl/8.4.0"

VISITORS = (
    ("198.51.100.12", "GB", "London", CHROME_DESKTOP),
    ("198.51.100.31", "US", "New York", SAFARI_IPHONE),
    ("203.0.113.44", "DE", "Berlin", FIREFOX_WINDOWS),
    ("203.0.113.77", "IN", "Mumbai", CHROME_DESKTOP),
    ("203.0.113.91", "BR", "Sao Paulo", CHROME_TABLET),
    ("192.0.2.18", "NL", "Amsterdam", SAFARI_IPHONE),
    ("192.0.2.55", "CA", "Toronto", FIREFOX_WINDOWS),
)


@dataclass(frozen=True, slots=True)
class SeedLink:
    short_code: str
    destination_url: str
    campaign_name: str
    click_limit: int | None = None
    expires_at: datetime | None = None
    is_active: bool = True
    is_abusive: bool = False
    password: str | None = None
    deactivation_reason: str | None = None
    daily_clicks: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class SeedResult:
    admin: User
    demo_user: User
    admin_password: str
    campaigns: dict[str, Campaign] = field(default_factory=dict)
    links: dict[str, Link] = field(default_factory=dict)
    click_events: int = 0


def _days_ago(days: int, hour: int = 12, minute: int = 30) -> datetime:
    moment = datetime.now(timezone.utc) - timedelta(days=days)
    return moment.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _history_anchor() -> datetime:
    """Midnight UTC of the day before the seed runs.

    The history ends yesterday so that no click is ever timestamped in the
    future, whatever time of day the seed happens to run.
    """

    return (datetime.now(timezone.utc) - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def build_seed_links(now: datetime | None = None) -> tuple[SeedLink, ...]:
    """Return the links the demo workspace contains."""

    reference = now or datetime.now(timezone.utc)
    return (
        SeedLink(
            short_code="demo-launch",
            destination_url="https://example.com/spring-launch",
            campaign_name="Spring Launch",
            daily_clicks=(18, 22, 15, 26, 31, 12, 9, 24, 29, 33, 21, 17, 27, 34),
        ),
        SeedLink(
            short_code="demo-newsletter",
            destination_url="https://example.com/newsletter/march",
            campaign_name="Newsletter",
            daily_clicks=(6, 8, 5, 9, 11, 4, 3, 7, 10, 12, 8, 6, 9, 13),
        ),
        SeedLink(
            short_code="demo-protected",
            destination_url="https://example.com/early-access",
            campaign_name="Spring Launch",
            password=LINK_PASSWORD,
            daily_clicks=(4, 6, 3, 7, 8, 2, 1, 5, 9, 10, 6, 5, 8, 11),
        ),
        SeedLink(
            short_code="demo-limited",
            destination_url="https://example.com/limited-offer",
            campaign_name="Limited Offer",
            click_limit=25,
            daily_clicks=(3, 4, 2, 5, 6, 1, 1, 3, 6, 7, 4, 3, 5, 8),
        ),
        SeedLink(
            short_code="demo-expired",
            destination_url="https://example.com/spring-sale",
            campaign_name="Spring Launch",
            expires_at=reference - timedelta(days=2),
            daily_clicks=(7, 9, 6, 11, 13, 5, 4, 8, 12, 14, 9, 7, 10, 15),
        ),
        SeedLink(
            short_code="demo-disabled",
            destination_url="https://example.com/partner-portal",
            campaign_name="Partners",
            is_active=False,
            deactivation_reason="Partner asked for a quieter period",
            daily_clicks=(5, 7, 4, 9, 10, 3, 2, 6, 11, 12, 7, 6, 8, 13),
        ),
    )


def build_campaigns() -> tuple[tuple[str, str], ...]:
    return (
        ("Spring Launch", "Short links for the spring product launch."),
        ("Newsletter", "Weekly newsletter call to action links."),
        ("Partners", "Co-marketing links for partner portals."),
        ("Limited Offer", "Time boxed campaigns with a click limit."),
    )


async def reset_demo_data(db: AsyncSession) -> None:
    """Remove everything this module created."""

    user_ids = [
        user.id
        for user in (
            await db.execute(
                select(User).where(User.email.in_([ADMIN_EMAIL, DEMO_USER_EMAIL]))
            )
        ).scalars()
    ]
    if not user_ids:
        return

    link_ids = [
        link.id
        for link in (
            await db.execute(select(Link).where(Link.user_id.in_(user_ids)))
        ).scalars()
    ]
    if link_ids:
        await db.execute(delete(ClickEvent).where(ClickEvent.link_id.in_(link_ids)))
        await db.execute(delete(Link).where(Link.id.in_(link_ids)))
    await db.execute(delete(Campaign).where(Campaign.user_id.in_(user_ids)))
    await db.execute(delete(User).where(User.id.in_(user_ids)))
    await db.commit()


async def _upsert_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    role: str,
) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            id=uuid4(),
            email=email,
            password_hash=hash_password(password),
            role=role,
        )
        db.add(user)
    else:
        user.password_hash = hash_password(password)
        user.role = role
    await db.flush()
    return user


async def _upsert_campaign(
    db: AsyncSession,
    *,
    user_id: UUID,
    name: str,
    description: str,
) -> Campaign:
    result = await db.execute(
        select(Campaign).where(Campaign.user_id == user_id, Campaign.name == name)
    )
    campaign = result.scalar_one_or_none()
    if campaign is None:
        campaign = Campaign(
            id=uuid4(),
            user_id=user_id,
            name=name,
            description=description,
        )
        db.add(campaign)
    else:
        campaign.description = description
    await db.flush()
    return campaign


async def _upsert_link(
    db: AsyncSession,
    *,
    owner_id: UUID,
    campaign_id: UUID | None,
    seed: SeedLink,
) -> Link:
    result = await db.execute(select(Link).where(Link.short_code == seed.short_code))
    link = result.scalar_one_or_none()
    values: dict[str, Any] = {
        "user_id": owner_id,
        "campaign_id": campaign_id,
        "destination_url": seed.destination_url,
        "click_limit": seed.click_limit,
        "expires_at": seed.expires_at,
        "is_active": seed.is_active,
        "is_abusive": seed.is_abusive,
        "password_hash": hash_password(seed.password) if seed.password else None,
        "deactivated_at": None if seed.is_active else _days_ago(3),
        "deactivation_reason": seed.deactivation_reason,
    }
    if link is None:
        link = Link(id=uuid4(), short_code=seed.short_code, total_clicks=0, **values)
        db.add(link)
    else:
        for field_name, value in values.items():
            setattr(link, field_name, value)
    await db.flush()
    return link


def build_click_rows(link: Link, seed: SeedLink) -> list[dict[str, Any]]:
    """Build the click events for one seeded link.

    The identifiers are derived from the link and the day, so the same seed
    always produces the same rows and a second run can recognise them.
    """

    rows: list[dict[str, Any]] = []
    days = len(seed.daily_clicks)
    anchor = _history_anchor()
    for index, clicks in enumerate(seed.daily_clicks):
        day = anchor - timedelta(days=days - 1 - index)
        for visit in range(clicks):
            ip, country, city, user_agent = VISITORS[(index + visit) % len(VISITORS)]
            parsed = parse_user_agent(user_agent)
            clicked_at = day + timedelta(hours=8 + (visit % 12), minutes=30)
            rows.append(
                {
                    "link_id": link.id,
                    "stream_message_id": f"seed-{link.short_code}-{index:02d}-{visit:02d}",
                    "clicked_at": clicked_at,
                    "ip_address": ip,
                    "country_code": country,
                    "city": city,
                    "user_agent": user_agent,
                    "browser": parsed.browser,
                    "os": parsed.os,
                    "device_type": parsed.device_type,
                    "referrer": "https://newsletter.example/",
                    "is_bot": parsed.is_bot,
                    "is_anomalous": False,
                }
            )

    # A couple of bot visits so the "bots filtered" metric is not empty.
    for index in range(3):
        agent = GOOGLEBOT if index % 2 == 0 else CURL_AGENT
        parsed = parse_user_agent(agent)
        rows.append(
            {
                "link_id": link.id,
                "stream_message_id": f"seed-{link.short_code}-bot-{index:02d}",
                "clicked_at": _days_ago(index + 1, hour=3),
                "ip_address": f"192.0.2.{200 + index}",
                "country_code": "US",
                "city": "New York",
                "user_agent": agent,
                "browser": parsed.browser,
                "os": parsed.os,
                "device_type": parsed.device_type,
                "referrer": "",
                "is_bot": True,
                "is_anomalous": False,
            }
        )
    return rows


async def _insert_click_events(
    db: AsyncSession,
    *,
    link: Link,
    seed: SeedLink,
) -> int:
    rows = build_click_rows(link, seed)
    if not rows:
        return 0

    identifiers = [row["stream_message_id"] for row in rows]
    existing = await db.execute(
        select(ClickEvent.stream_message_id).where(
            ClickEvent.stream_message_id.in_(identifiers)
        )
    )
    known = set(existing.scalars())

    fresh = [row for row in rows if row["stream_message_id"] not in known]
    for row in fresh:
        db.add(ClickEvent(**row))

    link.total_clicks = len(rows)
    return len(fresh)


async def seed_demo_data(
    *,
    db: AsyncSession,
    redis: Redis | None = None,
    admin_password: str | None = None,
    user_password: str = DEMO_USER_PASSWORD,
    reset: bool = False,
) -> SeedResult:
    """Create or refresh the demo workspace.

    The passwords are hashed with bcrypt exactly like the API does, and the
    routing cache is refreshed so the seeded links redirect immediately.
    """

    if reset:
        await reset_demo_data(db)

    admin_secret = admin_password or ADMIN_PASSWORD
    admin = await _upsert_user(
        db,
        email=ADMIN_EMAIL,
        password=admin_secret,
        role=UserRole.ADMIN.value,
    )
    demo_user = await _upsert_user(
        db,
        email=DEMO_USER_EMAIL,
        password=user_password,
        role=UserRole.USER.value,
    )

    campaigns: dict[str, Campaign] = {}
    for name, description in build_campaigns():
        campaigns[name] = await _upsert_campaign(
            db,
            user_id=demo_user.id,
            name=name,
            description=description,
        )

    links: dict[str, Link] = {}
    click_events = 0
    for seed in build_seed_links():
        link = await _upsert_link(
            db,
            owner_id=demo_user.id,
            campaign_id=campaigns[seed.campaign_name].id,
            seed=seed,
        )
        links[seed.short_code] = link
        click_events += await _insert_click_events(db, link=link, seed=seed)

    await db.commit()

    for link in links.values():
        await db.refresh(link)

    if redis is not None:
        for link in links.values():
            await cache_link(redis, link)

    return SeedResult(
        admin=admin,
        demo_user=demo_user,
        admin_password=admin_secret,
        campaigns=campaigns,
        links=links,
        click_events=click_events,
    )


def routing_metadata_for(link: Link) -> dict[str, Any]:
    """Expose the cached routing metadata, mainly for tests."""

    return routing_metadata(link)
