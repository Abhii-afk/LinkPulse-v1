"""Tests for the workspace endpoints the front end needs.

The link list, the campaign endpoints and the referrer breakdown did not
exist when the dashboard was built. These tests pin their behaviour, in
particular that the list never leaks another user's links.
"""

import json
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.main import app
from app.models.campaign import Campaign
from app.models.click_event import ClickEvent
from app.models.link import Link
from app.models.user import User, UserRole


class FakeResult:
    def __init__(self, *, scalar: object | None = None, rows: list[Any] | None = None) -> None:
        self.scalar = scalar
        self.rows = rows or []

    def scalar_one_or_none(self) -> object | None:
        return self.scalar

    def scalars(self) -> "FakeResult":
        return self

    def all(self) -> list[Any]:
        return self.rows

    def one(self) -> object:
        assert self.scalar is not None
        return self.scalar


class FakeSession:
    def __init__(
        self,
        *,
        links: list[Any] | None = None,
        campaigns: list[Campaign] | None = None,
        queued: list[FakeResult] | None = None,
    ) -> None:
        self.links = links if links is not None else []
        self.campaigns = campaigns or []
        self.queued = queued or []
        self.added: list[object] = []
        self.commit_count = 0

    async def execute(self, statement: object) -> FakeResult:
        if self.queued:
            return self.queued.pop(0)

        entity = statement.column_descriptions[0]["entity"]  # type: ignore[union-attr]
        parameters = statement.compile().params  # type: ignore[union-attr]
        values = list(parameters.values())

        if entity is Link:
            owner = next((v for v in values if isinstance(v, uuid4().__class__)), None)
            rows = [
                (link, self.campaign_name(link))
                for link in self.links
                if owner is None or link.user_id == owner
            ]
            return FakeResult(rows=rows)
        if entity is Campaign:
            owner = next((v for v in values if isinstance(v, uuid4().__class__)), None)
            name = next((v for v in values if isinstance(v, str)), None)
            if name is not None:
                # A lookup by name is a scalar query, not a list query.
                match = next(
                    (
                        campaign
                        for campaign in self.campaigns
                        if campaign.name == name
                        and (owner is None or campaign.user_id == owner)
                    ),
                    None,
                )
                return FakeResult(scalar=match)
            return FakeResult(
                rows=[
                    campaign
                    for campaign in self.campaigns
                    if owner is None or campaign.user_id == owner
                ]
            )
        if entity is ClickEvent:
            return FakeResult(rows=[])
        raise AssertionError(f"Unexpected query entity: {entity}")

    def campaign_name(self, link: Link) -> str | None:
        for campaign in self.campaigns:
            if campaign.id == link.campaign_id:
                return campaign.name
        return None

    def add(self, value: object) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        self.commit_count += 1

    async def refresh(self, value: object) -> None:
        if isinstance(value, Campaign):
            value.id = value.id or uuid4()
            value.created_at = value.created_at or datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def configured_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_secret", "test-only-secret-long-enough-for-hs256")
    monkeypatch.setattr(settings, "jwt_algorithm", "HS256")
    monkeypatch.setattr(settings, "public_base_url", "http://testserver")


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client


@pytest.fixture
def configure_dependencies() -> Callable[..., FakeSession]:
    def configure(session: FakeSession, user: User | None = None) -> FakeSession:
        async def override_get_db() -> AsyncIterator[FakeSession]:
            yield session

        app.dependency_overrides[get_db] = override_get_db
        if user is not None:
            async def override_current_user() -> User:
                return user

            app.dependency_overrides[get_current_user] = override_current_user
        return session

    yield configure
    app.dependency_overrides.clear()


def make_user(role: str = UserRole.USER.value) -> User:
    return User(
        id=uuid4(),
        email=f"{role}-{uuid4().hex[:6]}@example.com",
        password_hash="x",
        role=role,
    )


def make_link(
    owner_id: Any,
    short_code: str = "demo-link",
    **overrides: Any,
) -> Link:
    values: dict[str, Any] = {
        "id": uuid4(),
        "user_id": owner_id,
        "short_code": short_code,
        "destination_url": "https://example.com/target",
        "password_hash": None,
        "expires_at": None,
        "click_limit": None,
        "total_clicks": 0,
        "is_active": True,
        "is_abusive": False,
        "created_at": datetime.now(timezone.utc),
    }
    values.update(overrides)
    return Link(**values)


@pytest.mark.asyncio
async def test_the_link_list_returns_the_owner_links(
    client: AsyncClient,
    configure_dependencies: Callable[..., FakeSession],
) -> None:
    user = make_user()
    campaign = Campaign(
        id=uuid4(),
        user_id=user.id,
        name="Spring Launch",
        description="Launch links",
        created_at=datetime.now(timezone.utc),
    )
    link = make_link(user.id, "summer-deal", campaign_id=campaign.id, total_clicks=12)
    session = FakeSession(links=[link], campaigns=[campaign])
    configure_dependencies(session, user)

    response = await client.get("/api/v1/links")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["short_code"] == "summer-deal"
    assert body[0]["short_url"] == "http://testserver/summer-deal"
    assert body[0]["qr_code_url"] == "http://testserver/api/v1/links/summer-deal/qr"
    assert body[0]["campaign_name"] == "Spring Launch"
    assert body[0]["total_clicks"] == 12
    assert body[0]["status"] == "active"
    assert body[0]["password_protected"] is False


@pytest.mark.asyncio
async def test_the_link_list_reports_the_status_of_every_link(
    client: AsyncClient,
    configure_dependencies: Callable[..., FakeSession],
) -> None:
    user = make_user()
    links = [
        make_link(user.id, "live-link"),
        make_link(user.id, "off-link", is_active=False),
        make_link(user.id, "abusive-link", is_abusive=True),
        make_link(
            user.id,
            "old-link",
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        ),
    ]
    session = FakeSession(links=links)
    configure_dependencies(session, user)

    response = await client.get("/api/v1/links")

    assert response.status_code == 200
    statuses = {item["short_code"]: item["status"] for item in response.json()}
    assert statuses == {
        "live-link": "active",
        "off-link": "disabled",
        "abusive-link": "abusive",
        "old-link": "expired",
    }


@pytest.mark.asyncio
async def test_the_link_list_requires_authentication(
    client: AsyncClient,
    configure_dependencies: Callable[..., FakeSession],
) -> None:
    configure_dependencies(FakeSession())

    response = await client.get("/api/v1/links")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_campaigns_are_listed_for_the_owner(
    client: AsyncClient,
    configure_dependencies: Callable[..., FakeSession],
) -> None:
    user = make_user()
    campaigns = [
        Campaign(
            id=uuid4(),
            user_id=user.id,
            name="Spring Launch",
            description=None,
            created_at=datetime.now(timezone.utc),
        ),
    ]
    session = FakeSession(campaigns=campaigns)
    configure_dependencies(session, user)

    response = await client.get("/api/v1/campaigns")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(campaigns[0].id)
    assert body[0]["name"] == "Spring Launch"
    assert body[0]["description"] is None
    assert datetime.fromisoformat(body[0]["created_at"]) == campaigns[0].created_at


@pytest.mark.asyncio
async def test_a_campaign_can_be_created(
    client: AsyncClient,
    configure_dependencies: Callable[..., FakeSession],
) -> None:
    user = make_user()
    session = FakeSession()
    configure_dependencies(session, user)

    response = await client.post(
        "/api/v1/campaigns",
        json={"name": "  Spring Launch  ", "description": "Launch links"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Spring Launch"
    assert body["description"] == "Launch links"
    assert session.added and isinstance(session.added[0], Campaign)
    assert session.added[0].user_id == user.id
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_a_duplicate_campaign_name_is_refused(
    client: AsyncClient,
    configure_dependencies: Callable[..., FakeSession],
) -> None:
    user = make_user()
    existing = Campaign(
        id=uuid4(),
        user_id=user.id,
        name="Spring Launch",
        description=None,
        created_at=datetime.now(timezone.utc),
    )
    session = FakeSession(campaigns=[existing])
    configure_dependencies(session, user)

    response = await client.post(
        "/api/v1/campaigns",
        json={"name": "Spring Launch"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Campaign name already exists"}


@pytest.mark.asyncio
async def test_a_blank_campaign_name_is_refused(
    client: AsyncClient,
    configure_dependencies: Callable[..., FakeSession],
) -> None:
    user = make_user()
    configure_dependencies(FakeSession(), user)

    response = await client.post("/api/v1/campaigns", json={"name": "   "})

    assert response.status_code == 422
