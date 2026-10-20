import asyncio
import json
from collections.abc import AsyncIterator, Callable
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.link_session import issue_link_session_token
from app.core.redis_client import get_redis
from app.core.security import hash_password
from app.main import app
from app.models.link import Link
from app.models.user import User, UserRole


class FakeResult:
    def __init__(self, value: object | None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> object | None:
        return self.value


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
            self.stream.append(
                {
                    "stream": stream_key,
                    "payload": json.loads(payload),
                }
            )
            return current


class FakeSession:
    def __init__(self, link: Link | None = None) -> None:
        self.link = link
        self.execute_count = 0
        self.commit_count = 0

    async def execute(self, statement: object) -> FakeResult:
        self.execute_count += 1
        entity = statement.column_descriptions[0]["entity"]  # type: ignore[union-attr]
        if entity is Link:
            return FakeResult(self.link)
        raise AssertionError(f"Unexpected query entity: {entity}")

    async def commit(self) -> None:
        self.commit_count += 1


def make_metadata(short_code: str = "go", **overrides: object) -> dict[str, object | None]:
    metadata: dict[str, object | None] = {
        "id": str(uuid4()),
        "short_code": short_code,
        "destination_url": "https://example.com/destination",
        "password_hash": None,
        "has_password": False,
        "expires_at": None,
        "click_limit": None,
        "total_clicks": 0,
        "is_active": True,
        "is_abusive": False,
        "deactivated_at": None,
    }
    metadata.update(overrides)
    return metadata


async def cache_metadata(redis: FakeRedis, metadata: dict[str, object | None]) -> None:
    await redis.set(f"link:{metadata['short_code']}", json.dumps(metadata))


def make_link(short_code: str = "go", **overrides: object) -> Link:
    values: dict[str, object] = {
        "id": uuid4(),
        "user_id": uuid4(),
        "short_code": short_code,
        "destination_url": "https://example.com/destination",
        "password_hash": None,
        "expires_at": None,
        "click_limit": None,
        "total_clicks": 0,
        "is_active": True,
        "is_abusive": False,
    }
    values.update(overrides)
    return Link(**values)


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client


@pytest.fixture
def configure_dependencies() -> Callable[[Link | None], tuple[FakeSession, FakeRedis]]:
    def configure(link: Link | None = None) -> tuple[FakeSession, FakeRedis]:
        session = FakeSession(link)
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


@pytest.mark.asyncio
async def test_warm_cache_redirects_without_a_database_query(
    client: AsyncClient,
    configure_dependencies: Callable[[Link | None], tuple[FakeSession, FakeRedis]],
) -> None:
    session, redis = configure_dependencies()
    metadata = make_metadata()
    await cache_metadata(redis, metadata)

    response = await client.get("/go", headers={"user-agent": "pytest"})

    assert response.status_code == 302
    assert response.headers["location"] == "https://example.com/destination"
    assert session.execute_count == 0
    assert len(redis.stream) == 1
    assert redis.stream[0]["payload"]["short_code"] == "go"  # type: ignore[index]
    assert "password_hash" not in json.dumps(redis.stream)
    assert "password_hash" not in response.text


@pytest.mark.asyncio
async def test_cold_cache_loads_from_database_and_caches_for_one_hour(
    client: AsyncClient,
    configure_dependencies: Callable[[Link | None], tuple[FakeSession, FakeRedis]],
) -> None:
    link = make_link("cold")
    session, redis = configure_dependencies(link)

    response = await client.get("/cold", follow_redirects=False)

    assert response.status_code == 302
    assert session.execute_count == 1
    assert redis.ttls["link:cold"] == 3600
    assert json.loads(redis.values["link:cold"])["destination_url"] == link.destination_url


@pytest.mark.asyncio
async def test_missing_short_code_returns_404(
    client: AsyncClient,
    configure_dependencies: Callable[[Link | None], tuple[FakeSession, FakeRedis]],
) -> None:
    session, _redis = configure_dependencies()

    response = await client.get("/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Short link not found"}
    assert session.execute_count == 1


@pytest.mark.asyncio
async def test_cached_inactive_link_is_rejected_without_refreshing_from_database(
    client: AsyncClient,
    configure_dependencies: Callable[[Link | None], tuple[FakeSession, FakeRedis]],
) -> None:
    session, redis = configure_dependencies()
    await cache_metadata(redis, make_metadata(is_active=False))

    response = await client.get("/go")

    assert response.status_code == 410
    assert response.text == "<h1>Link Inactive or Suspended</h1>"
    assert session.execute_count == 0
    assert redis.stream == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "expected_body"),
    [
        (
            {"is_active": False, "is_abusive": True, "expires_at": "2000-01-01T00:00:00+00:00"},
            "Link Inactive or Suspended",
        ),
        (
            {"is_abusive": True, "expires_at": "2000-01-01T00:00:00+00:00"},
            "Link Inactive or Suspended",
        ),
        (
            {
                "expires_at": "2000-01-01T00:00:00+00:00",
                "click_limit": 1,
                "total_clicks": 1,
            },
            "Link Expired",
        ),
        (
            {"click_limit": 1, "total_clicks": 1, "has_password": True},
            "Click Limit Reached",
        ),
    ],
)
async def test_rule_waterfall_returns_the_first_failure(
    client: AsyncClient,
    configure_dependencies: Callable[[Link | None], tuple[FakeSession, FakeRedis]],
    overrides: dict[str, object],
    expected_body: str,
) -> None:
    _session, redis = configure_dependencies()
    await cache_metadata(redis, make_metadata(**overrides))

    response = await client.get("/go")

    assert response.status_code == 410
    assert response.text == f"<h1>{expected_body}</h1>"
    assert redis.stream == []


@pytest.mark.asyncio
async def test_password_protected_link_requires_a_session_cookie(
    client: AsyncClient,
    configure_dependencies: Callable[[Link | None], tuple[FakeSession, FakeRedis]],
) -> None:
    _session, redis = configure_dependencies()
    password_hash = hash_password("correct-password")
    await cache_metadata(
        redis,
        make_metadata(password_hash=password_hash, has_password=True),
    )

    response = await client.get("/go")

    assert response.status_code == 401
    assert "Enter Link Password" in response.text
    assert password_hash not in response.text
    assert redis.stream == []


@pytest.mark.asyncio
async def test_password_session_cookie_allows_redirect_without_plaintext_comparison(
    client: AsyncClient,
    configure_dependencies: Callable[[Link | None], tuple[FakeSession, FakeRedis]],
) -> None:
    _session, redis = configure_dependencies()
    password_hash = hash_password("correct-password")
    await cache_metadata(
        redis,
        make_metadata(password_hash=password_hash, has_password=True),
    )

    client.cookies.set("auth_go", issue_link_session_token("go"))
    response = await client.get("/go")

    assert response.status_code == 302
    assert password_hash not in response.text
    assert redis.stream[0]["payload"]["short_code"] == "go"  # type: ignore[index]


@pytest.mark.asyncio
async def test_forged_password_cookie_does_not_unlock_a_protected_link(
    client: AsyncClient,
    configure_dependencies: Callable[[Link | None], tuple[FakeSession, FakeRedis]],
) -> None:
    _session, redis = configure_dependencies()
    password_hash = hash_password("correct-password")
    await cache_metadata(
        redis,
        make_metadata(password_hash=password_hash, has_password=True),
    )

    client.cookies.set("auth_go", "anything-the-visitor-makes-up")
    response = await client.get("/go")

    assert response.status_code == 401
    assert "Enter Link Password" in response.text
    assert redis.stream == []


@pytest.mark.asyncio
async def test_click_limit_is_enforced_atomically_at_the_boundary(
    client: AsyncClient,
    configure_dependencies: Callable[[Link | None], tuple[FakeSession, FakeRedis]],
) -> None:
    _session, redis = configure_dependencies()
    await cache_metadata(redis, make_metadata(click_limit=1))

    responses = await asyncio.gather(
        client.get("/go", follow_redirects=False),
        client.get("/go", follow_redirects=False),
    )
    statuses = sorted(response.status_code for response in responses)

    assert statuses == [302, 410]
    assert redis.values["clicks:count:go"] == "1"
    assert len(redis.stream) == 1


@pytest.mark.asyncio
async def test_admin_deactivation_clears_cached_routing_metadata(
    client: AsyncClient,
    configure_dependencies: Callable[[Link | None], tuple[FakeSession, FakeRedis]],
) -> None:
    link = make_link("kill-me")
    session, redis = configure_dependencies(link)
    await cache_metadata(redis, make_metadata("kill-me"))
    admin = User(
        id=uuid4(),
        email="admin@example.com",
        password_hash=hash_password("correct-password"),
        role=UserRole.ADMIN.value,
    )

    async def override_current_user() -> User:
        return admin

    app.dependency_overrides[get_current_user] = override_current_user

    response = await client.patch(
        f"/api/v1/admin/links/{link.id}/status",
        json={"is_active": False, "reason": "safety review"},
    )

    assert response.status_code == 200
    assert response.json()["cache_cleared"] is True
    assert "link:kill-me" not in redis.values
    assert link.is_active is False
    assert link.deactivated_at is not None
    assert session.commit_count == 1
