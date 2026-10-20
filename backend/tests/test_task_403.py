from collections.abc import AsyncIterator, Callable
from datetime import datetime, timezone
from io import BytesIO
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.core.config import settings
from app.core.database import get_db
from app.core.redis_client import get_redis
from app.core.security import create_access_token, hash_password, verify_password
from app.main import app
from app.models.link import Link
from app.models.domain_blocklist import DomainBlocklist
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
        # Bulk import is rate limited, so the limiter is the only caller.
        assert is_rate_limit_call(number_of_keys)
        return self.rate_limiter.apply(*rate_limit_arguments(args))


class FakeSession:
    def __init__(self, user: User, existing_links: list[Link] | None = None) -> None:
        self.user = user
        self.existing_links = {link.short_code: link for link in existing_links or []}
        self.added_links: list[Link] = []

    async def execute(self, statement: object) -> FakeResult:
        entity = statement.column_descriptions[0]["entity"]  # type: ignore[union-attr]
        if entity is User:
            return FakeResult(self.user)
        if entity is DomainBlocklist:
            return FakeResult(None)
        if entity is Link:
            parameters = statement.compile().params  # type: ignore[union-attr]
            for short_code, link in self.existing_links.items():
                if short_code in parameters.values():
                    owner_is_scoped = self.user.id in parameters.values()
                    if not owner_is_scoped:
                        return FakeResult(link)
                    if link.user_id == self.user.id:
                        return FakeResult(link)
                    return FakeResult(None)
            return FakeResult(None)
        raise AssertionError(f"Unexpected query entity: {entity}")

    def add(self, link: Link) -> None:
        self.added_links.append(link)

    async def flush(self) -> None:
        link = self.added_links[-1]
        link.id = link.id or uuid4()
        now = datetime.now(timezone.utc)
        link.created_at = link.created_at or now
        link.updated_at = link.updated_at or now

    async def commit(self) -> None:
        return None

    async def refresh(self, _link: Link) -> None:
        return None

    async def rollback(self) -> None:
        return None


def make_user(email: str = "user@example.com", role: str = UserRole.USER.value) -> User:
    return User(
        id=uuid4(),
        email=email,
        password_hash=hash_password("correct-password"),
        role=role,
    )


def make_link(owner_id: UUID, short_code: str, destination_url: str = "https://example.com") -> Link:
    return Link(
        id=uuid4(),
        user_id=owner_id,
        short_code=short_code,
        destination_url=destination_url,
    )


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
def configure_dependencies() -> Callable[..., tuple[FakeSession, FakeRedis]]:
    def configure(
        user: User,
        existing_links: list[Link] | None = None,
    ) -> tuple[FakeSession, FakeRedis]:
        session = FakeSession(user, existing_links)
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
async def test_bulk_import_partially_imports_valid_rows_and_reports_failures(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
) -> None:
    user = make_user()
    existing = make_link(user.id, "already-taken")
    session, redis = configure_dependencies(user, [existing])
    csv_content = (
        "destination_url,custom_alias\n"
        "https://example.com/valid,valid-alias\n"
        "not-a-url,bad-url\n"
        "https://example.com/taken,already-taken\n"
        "https://example.com/repeated,valid-alias\n"
    )

    response = await client.post(
        "/api/v1/links/bulk",
        headers=auth_headers(user),
        files={"file": ("links.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "total_processed": 4,
        "successful_imports": 1,
        "failed_imports": 3,
        "errors": [
            {
                "row": 3,
                "error": "Destination URL is invalid: Input should be a valid URL, relative URL without a base",
            },
            {"row": 4, "error": "Alias 'already-taken' is already taken"},
            {"row": 5, "error": "Alias 'valid-alias' is duplicated in this file"},
        ],
    }
    assert len(session.added_links) == 1
    assert session.added_links[0].user_id == user.id
    assert "link:valid-alias" in redis.values


@pytest.mark.asyncio
async def test_bulk_import_rejects_missing_required_header(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
) -> None:
    user = make_user()
    configure_dependencies(user)

    response = await client.post(
        "/api/v1/links/bulk",
        headers=auth_headers(user),
        files={"file": ("links.csv", "custom_alias\nmissing-destination", "text/csv")},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "CSV must include a 'destination_url' column"}


@pytest.mark.asyncio
async def test_bulk_import_preserves_password_whitespace_before_hashing(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
) -> None:
    user = make_user()
    session, _redis = configure_dependencies(user)

    response = await client.post(
        "/api/v1/links/bulk",
        headers=auth_headers(user),
        files={
            "file": (
                "links.csv",
                "destination_url,custom_alias,password\n"
                "https://example.com/password,password-link,  secret123  \n",
                "text/csv",
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["successful_imports"] == 1
    assert session.added_links[0].password_hash is not None
    assert verify_password("  secret123  ", session.added_links[0].password_hash)


@pytest.mark.asyncio
async def test_qr_endpoint_returns_downloadable_png_for_actual_short_url(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = make_user()
    link = make_link(user.id, "summer-deal", "https://secret.example/private-destination")
    configure_dependencies(user, [link])

    from app.services import qr as qr_service

    generated_data: dict[str, str] = {}
    real_make = qr_service.qrcode.make

    def capture_qr_data(data: str, *args: object, **kwargs: object) -> object:
        generated_data["value"] = data
        return real_make(data, *args, **kwargs)

    monkeypatch.setattr(qr_service.qrcode, "make", capture_qr_data)
    response = await client.get(
        "/api/v1/links/summer-deal/qr",
        headers=auth_headers(user),
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["content-disposition"] == 'attachment; filename="link-summer-deal.png"'
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert generated_data["value"] == "http://testserver/summer-deal"
    assert b"secret.example" not in response.content
    Image.open(BytesIO(response.content)).verify()


@pytest.mark.asyncio
async def test_qr_endpoint_hides_links_from_other_owners(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
) -> None:
    owner = make_user("owner@example.com")
    other_user = make_user("other@example.com")
    link = make_link(owner.id, "owner-only")
    configure_dependencies(other_user, [link])

    response = await client.get(
        "/api/v1/links/owner-only/qr",
        headers=auth_headers(other_user),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Link not found"}


@pytest.mark.asyncio
async def test_visitor_cannot_use_task_403_endpoints(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
) -> None:
    visitor = make_user(role=UserRole.VISITOR.value)
    configure_dependencies(visitor)

    qr_response = await client.get(
        "/api/v1/links/any-link/qr",
        headers=auth_headers(visitor),
    )
    bulk_response = await client.post(
        "/api/v1/links/bulk",
        headers=auth_headers(visitor),
        files={"file": ("links.csv", "destination_url\nhttps://example.com", "text/csv")},
    )

    assert qr_response.status_code == 403
    assert bulk_response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path"),
    [("get", "/api/v1/links/any-link/qr"), ("post", "/api/v1/links/bulk")],
)
async def test_task_403_endpoints_require_authentication(
    client: AsyncClient,
    configure_dependencies: Callable[..., tuple[FakeSession, FakeRedis]],
    method: str,
    path: str,
) -> None:
    configure_dependencies(make_user())

    if method == "get":
        response = await client.get(path)
    else:
        response = await client.post(
            path,
            files={"file": ("links.csv", "destination_url\nhttps://example.com", "text/csv")},
        )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
