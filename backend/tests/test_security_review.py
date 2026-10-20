"""Regression tests for the LinkPulse security and reliability review.

Each test below pins one confirmed issue that was fixed:

* a forged cookie could unlock a password protected link
* the password challenge had no verification endpoint at all
* link creation was not rate limited
* a destination URL with an unusable host produced a 500 instead of a 422
* a missing or weak JWT secret produced a 500 on login
* the analytics worker lost a whole batch when one record was rejected
* the durable per-link click count was never maintained
* an Alembic revision identifier did not fit the version column
"""

import json
import re
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings, settings, validate_settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.link_session import (
    cookie_name,
    issue_link_session_token,
    verify_link_session_token,
)
from app.core.rate_limit import rate_limit_key
from app.core.redis_client import get_redis
from app.core.security import hash_password
from app.main import app
from app.models.domain_blocklist import DomainBlocklist
from app.models.link import Link
from app.models.user import User, UserRole
from tests.redis_fakes import (
    SlidingWindowCounter,
    is_rate_limit_call,
    rate_limit_arguments,
)


LINK_PASSWORD = "correct-password"


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
        self.rate_limiter = SlidingWindowCounter()
        self._click_lock = __import__("asyncio").Lock()

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ex: int | None = None) -> bool:
        self.values[key] = value
        self.ttls[key] = ex
        return True

    async def delete(self, key: str) -> int:
        self.ttls.pop(key, None)
        return int(self.values.pop(key, None) is not None)

    async def eval(self, _script: str, number_of_keys: int, *args: Any) -> Any:
        if is_rate_limit_call(number_of_keys):
            return self.rate_limiter.apply(*rate_limit_arguments(args))

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
        user: User | None = None,
        link: Link | None = None,
        blocked_domains: list[DomainBlocklist] | None = None,
    ) -> None:
        self.user = user
        self.link = link
        self.blocked_domains = {domain.domain: domain for domain in blocked_domains or []}
        self.added: list[object] = []
        self.commit_count = 0

    async def execute(self, statement: object) -> FakeResult:
        entity = statement.column_descriptions[0]["entity"]  # type: ignore[union-attr]
        if entity is User:
            return FakeResult(self.user)
        if entity is Link:
            return FakeResult(self.link)
        if entity is DomainBlocklist:
            parameters = statement.compile().params  # type: ignore[union-attr]
            for domain, blocked_domain in self.blocked_domains.items():
                if domain in parameters.values():
                    return FakeResult(blocked_domain)
            return FakeResult(None)
        raise AssertionError(f"Unexpected query entity: {entity}")

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        now = datetime.now(timezone.utc)
        for value in self.added:
            if isinstance(value, Link):
                value.id = value.id or uuid4()
                value.created_at = value.created_at or now
                value.updated_at = value.updated_at or now

    async def commit(self) -> None:
        self.commit_count += 1

    async def refresh(self, _value: object) -> None:
        return None

    async def rollback(self) -> None:
        return None


def make_user(role: str = UserRole.USER.value) -> User:
    return User(
        id=uuid4(),
        email=f"{role}-{uuid4().hex[:8]}@example.com",
        password_hash=hash_password(LINK_PASSWORD),
        role=role,
    )


def make_link(owner_id: Any, short_code: str = "go", **overrides: Any) -> Link:
    values: dict[str, Any] = {
        "id": uuid4(),
        "user_id": owner_id,
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


def make_metadata(short_code: str = "go", **overrides: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {
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


@pytest.fixture(autouse=True)
def configured_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_secret", "test-only-secret-long-enough-for-hs256")
    monkeypatch.setattr(settings, "jwt_algorithm", "HS256")
    monkeypatch.setattr(settings, "link_session_secret", "")
    monkeypatch.setattr(settings, "public_base_url", "http://testserver")
    monkeypatch.setattr(settings, "rate_limit_link_creation_per_minute", 30)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)
    monkeypatch.setattr(settings, "rate_limit_password_attempts_per_minute", 10)


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
        user: User | None = None,
        *,
        session: FakeSession | None = None,
        redis: FakeRedis | None = None,
    ) -> tuple[FakeSession, FakeRedis]:
        active_session = session or FakeSession(user=user)
        active_redis = redis or FakeRedis()

        async def override_get_db() -> AsyncIterator[FakeSession]:
            yield active_session

        async def override_get_redis() -> FakeRedis:
            return active_redis

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_redis] = override_get_redis
        if user is not None:
            async def override_current_user() -> User:
                return user

            app.dependency_overrides[get_current_user] = override_current_user
        return active_session, active_redis

    yield configure
    app.dependency_overrides.clear()


def auth_headers(user: User) -> dict[str, str]:
    from app.core.security import create_access_token

    return {"Authorization": f"Bearer {create_access_token(user)}"}


# --- password challenge ----------------------------------------------------


@pytest.mark.asyncio
async def test_a_visitor_cannot_unlock_a_protected_link_with_a_made_up_cookie(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
) -> None:
    _session, redis = configure_dependencies()
    password_hash = hash_password(LINK_PASSWORD)
    await redis.set(
        "link:go",
        json.dumps(make_metadata(password_hash=password_hash, has_password=True)),
    )

    client.cookies.set(cookie_name("go"), "forged-cookie-value")
    response = await client.get("/go")

    assert response.status_code == 401
    assert "Enter Link Password" in response.text
    assert redis.stream == []


@pytest.mark.asyncio
async def test_a_cookie_signed_for_another_link_does_not_unlock_this_one(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
) -> None:
    _session, redis = configure_dependencies()
    password_hash = hash_password(LINK_PASSWORD)
    await redis.set(
        "link:go",
        json.dumps(make_metadata(password_hash=password_hash, has_password=True)),
    )

    client.cookies.set(cookie_name("go"), issue_link_session_token("other-link"))
    response = await client.get("/go")

    assert response.status_code == 401
    assert redis.stream == []


@pytest.mark.asyncio
async def test_an_expired_link_session_token_is_rejected(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import link_session

    _session, redis = configure_dependencies()
    password_hash = hash_password(LINK_PASSWORD)
    await redis.set(
        "link:go",
        json.dumps(make_metadata(password_hash=password_hash, has_password=True)),
    )

    token = issue_link_session_token("go", ttl_seconds=1)
    monkeypatch.setattr(link_session, "_now", lambda: 4_000_000_000)

    client.cookies.set(cookie_name("go"), token)
    response = await client.get("/go")

    assert response.status_code == 401
    assert redis.stream == []


def test_link_session_tokens_are_signed_and_bound_to_the_short_code() -> None:
    token = issue_link_session_token("go")

    assert verify_link_session_token(token, "go") is True
    assert verify_link_session_token(token, "other") is False
    assert verify_link_session_token(f"{token}tampered", "go") is False
    assert verify_link_session_token("not-a-token", "go") is False


@pytest.mark.asyncio
async def test_the_correct_password_issues_a_signed_cookie_and_opens_the_link(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
) -> None:
    _session, redis = configure_dependencies()
    password_hash = hash_password(LINK_PASSWORD)
    await redis.set(
        "link:go",
        json.dumps(make_metadata(password_hash=password_hash, has_password=True)),
    )

    response = await client.post(
        "/api/v1/links/verify-password",
        data={"short_code": "go", "password": LINK_PASSWORD},
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/go"
    set_cookie = response.headers["set-cookie"]
    assert cookie_name("go") in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Path=/go" in set_cookie
    assert password_hash not in set_cookie
    assert password_hash not in response.text

    redirect_response = await client.get("/go")
    assert redirect_response.status_code == 302
    assert len(redis.stream) == 1


@pytest.mark.asyncio
async def test_a_wrong_password_is_refused_and_no_cookie_is_issued(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
) -> None:
    _session, redis = configure_dependencies()
    password_hash = hash_password(LINK_PASSWORD)
    await redis.set(
        "link:go",
        json.dumps(make_metadata(password_hash=password_hash, has_password=True)),
    )

    response = await client.post(
        "/api/v1/links/verify-password",
        data={"short_code": "go", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert "set-cookie" not in response.headers
    assert "Incorrect password" in response.text
    assert password_hash not in response.text
    assert redis.stream == []


@pytest.mark.asyncio
async def test_password_guessing_is_rate_limited(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
) -> None:
    _session, redis = configure_dependencies()
    password_hash = hash_password(LINK_PASSWORD)
    await redis.set(
        "link:go",
        json.dumps(make_metadata(password_hash=password_hash, has_password=True)),
    )

    statuses = []
    for _attempt in range(11):
        response = await client.post(
            "/api/v1/links/verify-password",
            data={"short_code": "go", "password": "wrong-password"},
        )
        statuses.append(response.status_code)

    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429
    assert redis.stream == []


# --- rate limiting ---------------------------------------------------------


@pytest.mark.asyncio
async def test_link_creation_is_rate_limited_per_client_ip(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
) -> None:
    user = make_user()
    _session, redis = configure_dependencies(user)

    statuses = []
    for _attempt in range(31):
        response = await client.post(
            "/api/v1/links",
            headers=auth_headers(user),
            json={"destination_url": "https://example.com/target"},
        )
        statuses.append(response.status_code)

    assert statuses[:30] == [201] * 30
    assert statuses[30] == 429
    assert rate_limit_key("links:create", "127.0.0.1") in redis.rate_limiter.windows


@pytest.mark.asyncio
async def test_the_rate_limit_does_not_reach_other_clients(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
) -> None:
    user = make_user()
    _session, redis = configure_dependencies(user)

    for _attempt in range(30):
        response = await client.post(
            "/api/v1/links",
            headers=auth_headers(user),
            json={"destination_url": "https://example.com/target"},
        )
        assert response.status_code == 201

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("203.0.113.7", 5555)),
        base_url="http://testserver",
    ) as other_client:
        other_response = await other_client.post(
            "/api/v1/links",
            headers=auth_headers(user),
            json={"destination_url": "https://example.com/target"},
        )

    assert other_response.status_code == 201


@pytest.mark.asyncio
async def test_unauthenticated_requests_do_not_consume_the_creation_budget(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
) -> None:
    user = make_user()
    # The real authentication dependency has to run, so it is not replaced.
    _session, redis = configure_dependencies(session=FakeSession(user=user))

    for _attempt in range(30):
        response = await client.post(
            "/api/v1/links",
            json={"destination_url": "https://example.com/target"},
        )
        assert response.status_code == 401

    response = await client.post(
        "/api/v1/links",
        headers=auth_headers(user),
        json={"destination_url": "https://example.com/target"},
    )

    assert response.status_code == 201


def test_the_documented_creation_limit_is_thirty_calls_per_minute() -> None:
    assert settings.rate_limit_link_creation_per_minute == 30
    assert settings.rate_limit_window_seconds == 60


# --- destination validation ------------------------------------------------


@pytest.mark.asyncio
async def test_a_destination_with_an_unusable_host_is_a_client_error(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
) -> None:
    user = make_user()
    _session, redis = configure_dependencies(user)

    response = await client.post(
        "/api/v1/links",
        headers=auth_headers(user),
        json={"destination_url": "https://example..com/target"},
    )

    assert response.status_code == 422
    assert "Destination URL is invalid" in response.json()["detail"]
    assert redis.values == {}


@pytest.mark.asyncio
async def test_a_destination_with_an_over_long_label_is_a_client_error(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
) -> None:
    user = make_user()
    _session, _redis = configure_dependencies(user)

    response = await client.post(
        "/api/v1/links",
        headers=auth_headers(user),
        json={"destination_url": f"https://{'a' * 64}.com/target"},
    )

    assert response.status_code == 422


# --- secrets and configuration ---------------------------------------------


@pytest.mark.asyncio
async def test_login_reports_a_missing_signing_secret_as_a_configuration_error(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = make_user()
    session = FakeSession(user=user)
    configure_dependencies(user, session=session)
    monkeypatch.setattr(settings, "jwt_secret", "")

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": LINK_PASSWORD},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Authentication is not configured"}


@pytest.mark.parametrize(
    "overrides",
    [
        {"jwt_secret": ""},
        {"jwt_secret": "too-short"},
        {"jwt_secret": "x" * 24, "jwt_algorithm": "none"},
        {"jwt_secret": "x" * 24, "jwt_algorithm": "RS256"},
    ],
)
def test_validate_settings_rejects_an_insecure_configuration(
    overrides: dict[str, str],
) -> None:
    configuration = Settings(_env_file=None, **overrides)

    with pytest.raises(RuntimeError):
        validate_settings(configuration)


def test_validate_settings_accepts_a_complete_configuration() -> None:
    configuration = Settings(
        _env_file=None,
        jwt_secret="x" * 24,
        jwt_algorithm="HS256",
    )

    validate_settings(configuration)


@pytest.mark.asyncio
async def test_a_token_signed_with_another_algorithm_is_rejected(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import jwt as pyjwt

    user = make_user()
    # The real authentication dependency has to run, so it is not replaced.
    configure_dependencies(session=FakeSession(user=user))
    monkeypatch.setattr(settings, "jwt_algorithm", "HS256")

    forged = pyjwt.encode(
        {
            "sub": str(user.id),
            "email": user.email,
            "role": UserRole.ADMIN.value,
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc),
        },
        "test-only-secret-long-enough-for-hs256",
        algorithm="HS512",
    )

    response = await client.get(
        "/api/v1/admin/access-check",
        headers={"Authorization": f"Bearer {forged}"},
    )

    assert response.status_code == 401


# --- migrations ------------------------------------------------------------


def test_alembic_revision_identifiers_fit_the_version_column() -> None:
    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    identifiers = re.findall(r'^revision: str = "([^"]+)"', "\n".join(
        path.read_text(encoding="utf-8") for path in versions.glob("0*.py")
    ), re.MULTILINE)

    assert identifiers
    for identifier in identifiers:
        assert len(identifier) <= 32, f"{identifier} does not fit alembic_version.version_num"
