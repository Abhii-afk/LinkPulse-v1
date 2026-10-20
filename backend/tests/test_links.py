import json
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.database import get_db
from app.core.redis_client import get_redis
from app.core.security import create_access_token, hash_password, verify_password
from app.main import app
from app.models.campaign import Campaign
from app.models.domain_blocklist import DomainBlocklist
from app.models.link import Link
from app.models.user import User, UserRole
from tests.redis_fakes import (
    SlidingWindowCounter,
    is_rate_limit_call,
    rate_limit_arguments,
)


class FakeResult:
    def __init__(self, value: object | None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> object | None:
        return self.value


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.rate_limiter = SlidingWindowCounter()

    async def set(self, key: str, value: str, *, ex: int | None = None) -> bool:
        self.values[key] = value
        return True

    async def delete(self, key: str) -> int:
        return int(self.values.pop(key, None) is not None)

    async def eval(self, _script: str, number_of_keys: int, *args: Any) -> list[int]:
        # Link creation is rate limited, so the limiter is the only caller.
        assert is_rate_limit_call(number_of_keys)
        return self.rate_limiter.apply(*rate_limit_arguments(args))


class FakeSession:
    def __init__(
        self,
        user: User,
        campaign: Campaign | None = None,
        existing_link: Link | None = None,
    ) -> None:
        self.user = user
        self.campaign = campaign
        self.existing_link = existing_link
        self.added: Link | None = None

    async def execute(self, statement: object) -> FakeResult:
        entity = statement.column_descriptions[0]["entity"]  # type: ignore[union-attr]
        if entity is User:
            return FakeResult(self.user)
        if entity is Campaign:
            if self.campaign is not None and self.campaign.user_id == self.user.id:
                return FakeResult(self.campaign)
            return FakeResult(None)
        if entity is DomainBlocklist:
            return FakeResult(None)
        if entity is Link:
            return FakeResult(self.existing_link)
        raise AssertionError(f"Unexpected query entity: {entity}")

    def add(self, link: Link) -> None:
        self.added = link

    async def flush(self) -> None:
        assert self.added is not None
        self.added.id = self.added.id or uuid4()
        now = datetime.now(timezone.utc)
        self.added.created_at = self.added.created_at or now
        self.added.updated_at = self.added.updated_at or now

    async def commit(self) -> None:
        return None

    async def refresh(self, _link: Link) -> None:
        return None

    async def rollback(self) -> None:
        return None


def make_user(email: str = "user@example.com") -> User:
    return User(
        id=uuid4(),
        email=email,
        password_hash=hash_password("correct-password"),
        role=UserRole.USER.value,
    )


@pytest.fixture(autouse=True)
def configured_jwt(monkeypatch: pytest.MonkeyPatch) -> None:
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
def configure_dependencies() -> Callable[..., tuple[FakeSession, FakeRedis]]:
    def configure(
        user: User,
        campaign: Campaign | None = None,
        existing_link: Link | None = None,
    ) -> tuple[FakeSession, FakeRedis]:
        session = FakeSession(user, campaign, existing_link)
        redis = FakeRedis()

        async def override_get_db() -> AsyncIterator[FakeSession]:
            yield session

        async def override_get_redis() -> FakeRedis:
            return redis

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_redis] = override_get_redis
        return session, redis

    yield configure
    app.dependency_overrides.clear()


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user)}"}


@pytest.mark.asyncio
async def test_valid_link_creation_persists_and_populates_redis(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
) -> None:
    user = make_user()
    campaign = Campaign(id=uuid4(), user_id=user.id, name="Launch")
    session, redis = configure_dependencies(user, campaign=campaign)
    expires_at = datetime.now(timezone.utc) + timedelta(days=1)

    response = await client.post(
        "/api/v1/links",
        headers=auth_headers(user),
        json={
            "destination_url": "https://example.com/products/gadget",
            "custom_alias": "summer-deal",
            "campaign_id": str(campaign.id),
            "rules": {
                "password": "PromoPassword123",
                "expires_at": expires_at.isoformat(),
                "click_limit": 1000,
            },
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["short_code"] == "summer-deal"
    assert body["short_url"] == "http://testserver/summer-deal"
    assert body["campaign_id"] == str(campaign.id)
    assert body["click_limit"] == 1000
    assert body["is_active"] is True
    assert body["is_abusive"] is False
    assert body["password_protected"] is True
    assert "password_hash" not in response.text
    assert "PromoPassword123" not in response.text

    assert session.added is not None
    assert session.added.user_id == user.id
    assert session.added.campaign_id == campaign.id
    assert verify_password("PromoPassword123", session.added.password_hash)

    cached = json.loads(redis.values["link:summer-deal"])
    assert cached["id"] == str(session.added.id)
    assert cached["destination_url"] == body["destination_url"]
    assert cached["has_password"] is True
    assert cached["password_hash"] != "PromoPassword123"
    assert verify_password("PromoPassword123", cached["password_hash"])
    assert cached["is_active"] is True
    assert cached["is_abusive"] is False


@pytest.mark.asyncio
async def test_malformed_destination_url_is_rejected(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
) -> None:
    user = make_user()
    configure_dependencies(user)

    response = await client.post(
        "/api/v1/links",
        headers=auth_headers(user),
        json={"destination_url": "not-a-url"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_invalid_alias_and_rules_are_rejected(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
) -> None:
    user = make_user()
    configure_dependencies(user)

    response = await client.post(
        "/api/v1/links",
        headers=auth_headers(user),
        json={
            "destination_url": "https://example.com",
            "custom_alias": "bad/alias",
            "rules": {"click_limit": 0, "password": "short"},
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_duplicate_custom_alias_returns_conflict(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
) -> None:
    user = make_user()
    existing = Link(
        id=uuid4(),
        user_id=user.id,
        short_code="summer-deal",
        destination_url="https://existing.example.com",
    )
    _session, redis = configure_dependencies(user, existing_link=existing)

    response = await client.post(
        "/api/v1/links",
        headers=auth_headers(user),
        json={
            "destination_url": "https://example.com/new",
            "custom_alias": "summer-deal",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Alias already in use"
    assert redis.values == {}


@pytest.mark.asyncio
async def test_missing_authentication_is_rejected(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
) -> None:
    configure_dependencies(make_user())

    response = await client.post(
        "/api/v1/links",
        json={"destination_url": "https://example.com"},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_user_cannot_attach_another_users_campaign(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
) -> None:
    owner = make_user("owner@example.com")
    other_user = make_user("other@example.com")
    other_campaign = Campaign(id=uuid4(), user_id=owner.id, name="Owner campaign")
    _session, redis = configure_dependencies(other_user, campaign=other_campaign)

    response = await client.post(
        "/api/v1/links",
        headers=auth_headers(other_user),
        json={
            "destination_url": "https://example.com/private",
            "campaign_id": str(other_campaign.id),
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Campaign not found"
    assert redis.values == {}
