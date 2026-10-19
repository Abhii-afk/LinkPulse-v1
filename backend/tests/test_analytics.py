from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.security import hash_password
from app.main import app
from app.models.link import Link
from app.models.user import User, UserRole


class FakeResult:
    def __init__(
        self,
        *,
        one: object | None = None,
        scalar: object | None = None,
        rows: list[object] | None = None,
    ) -> None:
        self.one_value = one
        self.scalar_value = scalar
        self.rows = rows or []

    def one(self) -> object:
        assert self.one_value is not None
        return self.one_value

    def scalar_one_or_none(self) -> object | None:
        return self.scalar_value

    def all(self) -> list[object]:
        return self.rows


class FakeSession:
    def __init__(self, results: list[FakeResult]) -> None:
        self.results = results
        self.statements: list[object] = []

    async def execute(self, statement: object) -> FakeResult:
        self.statements.append(statement)
        if not self.results:
            raise AssertionError("Unexpected additional analytics query")
        return self.results.pop(0)


def make_user(role: str = UserRole.USER.value) -> User:
    return User(
        id=uuid4(),
        email=f"{role}-{uuid4().hex[:8]}@example.com",
        password_hash=hash_password("correct-password"),
        role=role,
    )


def make_link(
    owner_id: UUID,
    *,
    is_active: bool = True,
    is_abusive: bool = False,
    expires_at: datetime | None = None,
) -> Link:
    return Link(
        id=uuid4(),
        user_id=owner_id,
        short_code=f"link-{uuid4().hex[:8]}",
        destination_url="https://example.com",
        expires_at=expires_at,
        is_active=is_active,
        is_abusive=is_abusive,
        total_clicks=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def overview_results(
    *,
    total_links: int = 0,
    active_links: int = 0,
    total_clicks: int = 0,
    human_clicks: int = 0,
    bot_clicks: int = 0,
    anomalous_clicks: int = 0,
    unique_visitors: int = 0,
    time_series: list[object] | None = None,
    devices: list[object] | None = None,
    browsers: list[object] | None = None,
    top_links: list[object] | None = None,
) -> list[FakeResult]:
    return [
        FakeResult(one=SimpleNamespace(total_links=total_links, active_links=active_links)),
        FakeResult(
            one=SimpleNamespace(
                total_clicks=total_clicks,
                human_clicks=human_clicks,
                bot_clicks=bot_clicks,
                anomalous_clicks=anomalous_clicks,
                unique_visitors=unique_visitors,
            )
        ),
        FakeResult(rows=time_series),
        FakeResult(rows=devices),
        FakeResult(rows=browsers),
        FakeResult(rows=top_links),
    ]


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client


@pytest.fixture
def configure_dependencies() -> Callable[[User, FakeSession], None]:
    def configure(current_user: User, session: FakeSession) -> None:
        async def override_get_db() -> AsyncIterator[FakeSession]:
            yield session

        async def override_current_user() -> User:
            return current_user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_current_user

    yield configure
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_analytics_overview_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/analytics/overview")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_user_overview_returns_sensible_empty_state(
    client: AsyncClient,
    configure_dependencies: Callable[[User, FakeSession], None],
) -> None:
    user = make_user()
    session = FakeSession(overview_results())
    configure_dependencies(user, session)

    response = await client.get("/api/v1/analytics/overview")

    assert response.status_code == 200
    assert response.json() == {
        "scope": {
            "link_id": None,
            "from": None,
            "to": None,
            "granularity": "day",
        },
        "link": None,
        "summary": {
            "total_clicks": 0,
            "active_links": 0,
            "human_clicks": 0,
            "bot_clicks": 0,
            "anomalous_clicks": 0,
            "unique_visitors": 0,
        },
        "clicks_over_time": [],
        "device_breakdown": [],
        "browser_breakdown": [],
        "top_links": [],
    }


@pytest.mark.asyncio
async def test_user_overview_uses_database_aggregates_for_mvp_metrics(
    client: AsyncClient,
    configure_dependencies: Callable[[User, FakeSession], None],
) -> None:
    user = make_user()
    first_bucket = datetime(2026, 10, 1, tzinfo=timezone.utc)
    second_bucket = datetime(2026, 10, 2, tzinfo=timezone.utc)
    session = FakeSession(
        overview_results(
            total_links=3,
            active_links=2,
            total_clicks=4,
            human_clicks=3,
            bot_clicks=1,
            anomalous_clicks=1,
            unique_visitors=3,
            time_series=[
                SimpleNamespace(bucket=first_bucket, clicks=3, human_clicks=2, bot_clicks=1),
                SimpleNamespace(bucket=second_bucket, clicks=1, human_clicks=1, bot_clicks=0),
            ],
            devices=[
                SimpleNamespace(value="Mobile", clicks=3),
                SimpleNamespace(value="Desktop", clicks=1),
            ],
            browsers=[
                SimpleNamespace(value="Chrome", clicks=2),
                SimpleNamespace(value="Safari", clicks=2),
            ],
            top_links=[
                SimpleNamespace(
                    link_id=uuid4(),
                    short_code="top-link",
                    clicks=4,
                    is_active=True,
                    is_abusive=False,
                )
            ],
        )
    )
    configure_dependencies(user, session)

    response = await client.get(
        "/api/v1/analytics/overview",
        params={
            "from": "2026-10-01T00:00:00Z",
            "to": "2026-11-01T00:00:00Z",
            "granularity": "day",
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["scope"]["from"] == "2026-10-01T00:00:00Z"
    assert body["scope"]["to"] == "2026-11-01T00:00:00Z"
    assert body["summary"] == {
        "total_clicks": 4,
        "active_links": 2,
        "human_clicks": 3,
        "bot_clicks": 1,
        "anomalous_clicks": 1,
        "unique_visitors": 3,
    }
    assert body["clicks_over_time"] == [
        {"bucket": "2026-10-01T00:00:00Z", "clicks": 3, "human_clicks": 2, "bot_clicks": 1},
        {"bucket": "2026-10-02T00:00:00Z", "clicks": 1, "human_clicks": 1, "bot_clicks": 0},
    ]
    assert body["device_breakdown"] == [
        {"value": "Mobile", "clicks": 3, "percentage": 75.0},
        {"value": "Desktop", "clicks": 1, "percentage": 25.0},
    ]
    assert body["browser_breakdown"] == [
        {"value": "Chrome", "clicks": 2, "percentage": 50.0},
        {"value": "Safari", "clicks": 2, "percentage": 50.0},
    ]
    assert body["top_links"][0]["short_code"] == "top-link"
    assert len(session.statements) == 6


def link_results(
    link: Link,
    *,
    total_clicks: int = 0,
    active_links: int = 0,
    human_clicks: int = 0,
    bot_clicks: int = 0,
    anomalous_clicks: int = 0,
    unique_visitors: int = 0,
    time_series: list[object] | None = None,
    devices: list[object] | None = None,
    browsers: list[object] | None = None,
    top_links: list[object] | None = None,
) -> list[FakeResult]:
    return [
        FakeResult(scalar=link),
        *overview_results(
            total_links=1,
            active_links=active_links,
            total_clicks=total_clicks,
            human_clicks=human_clicks,
            bot_clicks=bot_clicks,
            anomalous_clicks=anomalous_clicks,
            unique_visitors=unique_visitors,
            time_series=time_series,
            devices=devices,
            browsers=browsers,
            top_links=top_links,
        ),
    ]


@pytest.mark.asyncio
async def test_user_cannot_view_another_users_link_analytics(
    client: AsyncClient,
    configure_dependencies: Callable[[User, FakeSession], None],
) -> None:
    owner = make_user()
    unrelated_user = make_user()
    link = make_link(owner.id)
    session = FakeSession([FakeResult(scalar=None)])
    configure_dependencies(unrelated_user, session)

    response = await client.get(f"/api/v1/links/{link.id}/analytics")

    assert response.status_code == 404
    assert response.json() == {"detail": "Link not found"}
    assert len(session.statements) == 1
    assert link.user_id == owner.id != unrelated_user.id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("is_active", "expires_at", "expected_status"),
    [
        (False, None, "disabled"),
        (True, datetime.now(timezone.utc) - timedelta(days=1), "expired"),
    ],
)
async def test_historical_events_remain_available_for_disabled_or_expired_links(
    client: AsyncClient,
    configure_dependencies: Callable[[User, FakeSession], None],
    is_active: bool,
    expires_at: datetime | None,
    expected_status: str,
) -> None:
    owner = make_user()
    link = make_link(owner.id, is_active=is_active, expires_at=expires_at)
    session = FakeSession(
        link_results(
            link,
            total_clicks=2,
            active_links=0 if not is_active else 1,
            human_clicks=1,
            bot_clicks=1,
            unique_visitors=2,
            time_series=[
                SimpleNamespace(
                    bucket=datetime(2026, 10, 1, tzinfo=timezone.utc),
                    clicks=2,
                    human_clicks=1,
                    bot_clicks=1,
                )
            ],
            devices=[SimpleNamespace(value="Mobile", clicks=2)],
            browsers=[SimpleNamespace(value="Chrome", clicks=2)],
            top_links=[
                SimpleNamespace(
                    link_id=link.id,
                    short_code=link.short_code,
                    clicks=2,
                    is_active=is_active,
                    is_abusive=False,
                )
            ],
        )
    )
    configure_dependencies(owner, session)

    response = await client.get(f"/api/v1/links/{link.id}/analytics")

    assert response.status_code == 200
    body = response.json()
    assert body["link"]["status"] == expected_status
    assert body["summary"]["total_clicks"] == 2
    assert body["clicks_over_time"][0]["clicks"] == 2


@pytest.mark.asyncio
async def test_normal_user_cannot_access_admin_wide_analytics(
    client: AsyncClient,
    configure_dependencies: Callable[[User, FakeSession], None],
) -> None:
    user = make_user()
    session = FakeSession([])
    configure_dependencies(user, session)

    response = await client.get("/api/v1/admin/analytics/overview")

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}
    assert session.statements == []


@pytest.mark.asyncio
async def test_admin_can_view_admin_wide_analytics_including_link_statuses(
    client: AsyncClient,
    configure_dependencies: Callable[[User, FakeSession], None],
) -> None:
    admin = make_user(UserRole.ADMIN.value)
    disabled_link_id = uuid4()
    session = FakeSession(
        overview_results(
            total_links=4,
            active_links=1,
            total_clicks=6,
            human_clicks=4,
            bot_clicks=2,
            top_links=[
                SimpleNamespace(
                    link_id=disabled_link_id,
                    short_code="historical-link",
                    clicks=6,
                    is_active=False,
                    is_abusive=False,
                )
            ],
        )
    )
    configure_dependencies(admin, session)

    response = await client.get("/api/v1/admin/analytics/overview")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["active_links"] == 1
    assert body["summary"]["total_clicks"] == 6
    assert body["top_links"][0] == {
        "link_id": str(disabled_link_id),
        "short_code": "historical-link",
        "clicks": 6,
        "is_active": False,
        "is_abusive": False,
        "destination_url": None,
        "click_limit": None,
        "expires_at": None,
        "status": "disabled",
    }
