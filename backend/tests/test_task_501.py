import asyncio
import json
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.redis_client import get_redis
from app.core.security import hash_password
from app.main import app
from app.models.domain_blocklist import DomainBlocklist
from app.models.link import Link
from app.models.user import User, UserRole


class FakeResult:
    def __init__(
        self,
        *,
        scalar: object | None = None,
        one: object | None = None,
        rows: list[object] | None = None,
        scalars: list[object] | None = None,
    ) -> None:
        self.scalar_value = scalar
        self.one_value = one
        self.rows = rows or []
        self.scalar_values = scalars or []

    def scalar_one_or_none(self) -> object | None:
        return self.scalar_value

    def one(self) -> object:
        assert self.one_value is not None
        return self.one_value

    def all(self) -> list[object]:
        return self.rows or self.scalar_values

    def scalars(self) -> "FakeResult":
        return self


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int | None] = {}
        self.stream: list[dict[str, object]] = []
        self._click_lock = asyncio.Lock()

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ex: int | None = None) -> bool:
        self.values[key] = value
        self.ttls[key] = ex
        return True

    async def delete(self, key: str) -> int:
        self.ttls.pop(key, None)
        return int(self.values.pop(key, None) is not None)

    async def eval(self, _script: str, _number_of_keys: int, *args: str) -> int:
        counter_key, stream_key, initial, limit, payload = args
        async with self._click_lock:
            current = int(self.values.get(counter_key, initial))
            if limit and current >= int(limit):
                return 0
            current += 1
            self.values[counter_key] = str(current)
            self.stream.append({"stream": stream_key, "payload": json.loads(payload)})
            return current


class FakeSession:
    def __init__(
        self,
        *,
        link: Link | None = None,
        links: list[Link] | None = None,
        blocked_domains: list[DomainBlocklist] | None = None,
        queued_results: list[FakeResult] | None = None,
    ) -> None:
        self.link = link
        self.links = links or ([] if link is None else [link])
        self.blocked_domains = {domain.domain: domain for domain in blocked_domains or []}
        self.queued_results = queued_results
        self.commit_count = 0
        self.rollback_count = 0
        self.added: list[object] = []

    async def execute(self, statement: object) -> FakeResult:
        if self.queued_results is not None:
            if not self.queued_results:
                raise AssertionError("Unexpected additional query")
            return self.queued_results.pop(0)

        entity = statement.column_descriptions[0]["entity"]  # type: ignore[union-attr]
        if entity is Link:
            if getattr(statement, "whereclause", None) is not None:
                return FakeResult(scalar=self.link)
            return FakeResult(scalars=self.links)
        if entity is DomainBlocklist:
            parameters = statement.compile().params  # type: ignore[union-attr]
            for domain, blocked_domain in self.blocked_domains.items():
                if domain in parameters.values():
                    return FakeResult(scalar=blocked_domain)
            return FakeResult(scalars=list(self.blocked_domains.values()))
        raise AssertionError(f"Unexpected query entity: {entity}")

    def add(self, value: object) -> None:
        self.added.append(value)
        if isinstance(value, DomainBlocklist):
            self.blocked_domains[value.domain] = value

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commit_count += 1

    async def refresh(self, value: object) -> None:
        if isinstance(value, DomainBlocklist):
            value.id = value.id or uuid4()
            value.created_at = value.created_at or datetime.now(timezone.utc)

    async def rollback(self) -> None:
        self.rollback_count += 1


def make_user(
    email: str = "admin@example.com",
    role: str = UserRole.ADMIN.value,
) -> User:
    return User(
        id=uuid4(),
        email=email,
        password_hash=hash_password("correct-password"),
        role=role,
    )


def make_link(
    owner_id: UUID,
    short_code: str = "managed-link",
    *,
    is_active: bool = True,
    is_abusive: bool = False,
) -> Link:
    return Link(
        id=uuid4(),
        user_id=owner_id,
        short_code=short_code,
        destination_url="https://example.com/destination",
        total_clicks=4,
        is_active=is_active,
        is_abusive=is_abusive,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def auth_user(user: User) -> Callable[[], User]:
    async def override_current_user() -> User:
        return user

    return override_current_user


@pytest.fixture(autouse=True)
def configured_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_secret", "test-only-secret-long-enough-for-hs256")
    monkeypatch.setattr(settings, "jwt_algorithm", "HS256")


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
        *,
        session: FakeSession | None = None,
        redis: FakeRedis | None = None,
    ) -> tuple[FakeSession, FakeRedis]:
        active_session = session or FakeSession()
        active_redis = redis or FakeRedis()

        async def override_get_db() -> AsyncIterator[FakeSession]:
            yield active_session

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = auth_user(user)
        app.dependency_overrides[get_redis] = lambda: active_redis
        return active_session, active_redis

    yield configure
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_normal_users_cannot_view_or_execute_admin_actions(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
) -> None:
    user = make_user("user@example.com", UserRole.USER.value)
    link = make_link(user.id)
    configure_dependencies(user, session=FakeSession(link=link))

    list_response = await client.get("/api/v1/admin/links")
    domain_response = await client.post(
        "/api/v1/admin/domains",
        json={"domain": "example.com", "reason": "malware"},
    )
    status_response = await client.patch(
        f"/api/v1/admin/links/{link.id}/status",
        json={"is_active": False, "reason": "abuse"},
    )

    assert list_response.status_code == 403
    assert domain_response.status_code == 403
    assert status_response.status_code == 403
    assert link.is_active is True


@pytest.mark.asyncio
async def test_admin_can_list_managed_links_without_sensitive_fields(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
) -> None:
    admin = make_user()
    first = make_link(admin.id, "first-link")
    second = make_link(uuid4(), "second-link", is_active=False)
    configure_dependencies(
        admin,
        session=FakeSession(
            queued_results=[FakeResult(rows=[(first, 7), (second, 0)])]
        ),
    )

    response = await client.get("/api/v1/admin/links")

    assert response.status_code == 200
    assert [item["short_code"] for item in response.json()] == ["first-link", "second-link"]
    assert response.json()[0]["owner_id"] == str(admin.id)
    assert response.json()[0]["total_clicks"] == 7
    assert response.json()[1]["status"] == "disabled"
    assert "password_hash" not in response.text


@pytest.mark.asyncio
async def test_admin_can_add_and_review_normalized_blocked_domains(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
) -> None:
    admin = make_user()
    session, _redis = configure_dependencies(admin)

    add_response = await client.post(
        "/api/v1/admin/domains",
        json={"domain": "WWW.Example.com.", "reason": "Known malware host"},
    )
    list_response = await client.get("/api/v1/admin/domains")
    duplicate_response = await client.post(
        "/api/v1/admin/domains",
        json={"domain": "example.com", "reason": "Duplicate"},
    )
    invalid_response = await client.post(
        "/api/v1/admin/domains",
        json={"domain": "http://[invalid", "reason": "Malformed"},
    )

    assert add_response.status_code == 201
    assert add_response.json()["domain"] == "example.com"
    assert add_response.json()["created_by"] == str(admin.id)
    assert list_response.status_code == 200
    assert list_response.json()[0]["reason"] == "Known malware host"
    assert duplicate_response.status_code == 409
    assert invalid_response.status_code == 422
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_blocked_destination_is_rejected_for_link_creation(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
) -> None:
    user = make_user("creator@example.com", UserRole.USER.value)
    blocked = DomainBlocklist(
        id=uuid4(),
        domain="example.com",
        reason="Malware",
        created_by=uuid4(),
        created_at=datetime.now(timezone.utc),
    )
    session, redis = configure_dependencies(
        user,
        session=FakeSession(blocked_domains=[blocked]),
    )

    response = await client.post(
        "/api/v1/links",
        json={"destination_url": "https://sub.example.com/path", "custom_alias": "blocked"},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Destination domain 'example.com' is blocked"}
    assert session.added == []
    assert redis.values == {}


@pytest.mark.asyncio
async def test_admin_disable_records_reason_invalidates_cache_and_stops_redirects(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
) -> None:
    admin = make_user()
    link = make_link(admin.id, "kill-me")
    redis = FakeRedis()
    await redis.set(
        "link:kill-me",
        json.dumps(
            {
                "id": str(link.id),
                "short_code": link.short_code,
                "destination_url": link.destination_url,
                "password_hash": None,
                "has_password": False,
                "expires_at": None,
                "click_limit": None,
                "total_clicks": link.total_clicks,
                "is_active": True,
                "is_abusive": False,
                "deactivated_at": None,
            }
        ),
    )
    session, _redis = configure_dependencies(
        admin,
        session=FakeSession(link=link),
        redis=redis,
    )

    response = await client.patch(
        f"/api/v1/admin/links/{link.id}/status",
        json={
            "is_active": False,
            "is_abusive": True,
            "reason": "Phishing destination confirmed",
        },
    )
    assert "link:kill-me" not in redis.values
    redirect_response = await client.get("/kill-me", follow_redirects=False)

    assert response.status_code == 200
    assert response.json() == {
        "status": "updated",
        "link_id": str(link.id),
        "is_active": False,
        "is_abusive": True,
        "reason": "Phishing destination confirmed",
        "cache_cleared": True,
    }
    assert link.deactivation_reason == "Phishing destination confirmed"
    assert link.deactivated_at is not None
    assert redirect_response.status_code == 410
    assert redirect_response.text == "<h1>Link Inactive or Suspended</h1>"
    assert redis.stream == []
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_disabled_link_keeps_historical_analytics_available(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
) -> None:
    admin = make_user()
    link = make_link(admin.id, "historical-link")
    session = FakeSession(
        queued_results=[
            FakeResult(scalar=link),
            FakeResult(scalar=link),
            FakeResult(one=SimpleNamespace(total_links=1, active_links=0)),
            FakeResult(
                one=SimpleNamespace(
                    total_clicks=2,
                    human_clicks=1,
                    bot_clicks=1,
                    anomalous_clicks=0,
                    unique_visitors=2,
                )
            ),
            FakeResult(
                rows=[
                    SimpleNamespace(
                        bucket=datetime(2026, 10, 1, tzinfo=timezone.utc),
                        clicks=2,
                        human_clicks=1,
                        bot_clicks=1,
                    )
                ]
            ),
            FakeResult(rows=[SimpleNamespace(value="Mobile", clicks=2)]),
            FakeResult(rows=[SimpleNamespace(value="Chrome", clicks=2)]),
            FakeResult(
                rows=[
                    SimpleNamespace(
                        link_id=link.id,
                        short_code=link.short_code,
                        clicks=2,
                        is_active=False,
                        is_abusive=True,
                        destination_url=link.destination_url,
                        click_limit=None,
                        expires_at=None,
                    )
                ]
            ),
        ]
    )
    configure_dependencies(admin, session=session)

    disable_response = await client.patch(
        f"/api/v1/admin/links/{link.id}/status",
        json={"is_active": False, "reason": "Abuse review"},
    )
    analytics_response = await client.get(f"/api/v1/links/{link.id}/analytics")

    assert disable_response.status_code == 200
    assert analytics_response.status_code == 200
    body = analytics_response.json()
    assert body["link"]["status"] == "disabled"
    assert body["summary"]["total_clicks"] == 2
    assert body["clicks_over_time"][0]["clicks"] == 2
