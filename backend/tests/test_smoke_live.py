"""End-to-end smoke test against a running LinkPulse instance.

The test is skipped unless `LINKPULSE_SMOKE_BASE_URL` points at a running
API, so the normal unit suite stays offline:

    cd backend && LINKPULSE_SMOKE_BASE_URL=http://127.0.0.1:8000 \
        pytest tests/test_smoke_live.py -q

Optional variables:

    LINKPULSE_SMOKE_ADMIN_EMAIL     admin account used for the kill switch
    LINKPULSE_SMOKE_ADMIN_PASSWORD  password of that account
    LINKPULSE_SMOKE_API_KEY         bearer token used instead of the two above

The test creates real rows. It uses a random suffix for every alias and
email so repeated runs never collide.
"""

import os
import uuid

import pytest
from httpx import AsyncClient


BASE_URL = os.environ.get("LINKPULSE_SMOKE_BASE_URL", "").strip()
ADMIN_EMAIL = os.environ.get("LINKPULSE_SMOKE_ADMIN_EMAIL", "").strip()
ADMIN_PASSWORD = os.environ.get("LINKPULSE_SMOKE_ADMIN_PASSWORD", "").strip()
API_KEY = os.environ.get("LINKPULSE_SMOKE_API_KEY", "").strip()

pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="set LINKPULSE_SMOKE_BASE_URL to run the live smoke test",
)


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(base_url=BASE_URL, timeout=15.0) as test_client:
        yield test_client


def unique_suffix() -> str:
    return uuid.uuid4().hex[:10]


async def sign_in(
    client: AsyncClient,
    email: str,
    password: str,
) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_health_endpoints_report_the_dependencies(client: AsyncClient) -> None:
    live = await client.get("/health/live")
    ready = await client.get("/health")

    assert live.status_code == 200, live.text
    assert live.json()["status"] == "ok"
    assert ready.status_code == 200, ready.text
    body = ready.json()
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["redis"] == "ok"
    assert body["checks"]["worker"] in {"ok", "stale", "absent"}


@pytest.mark.asyncio
async def test_link_creation_redirect_and_analytics(client: AsyncClient) -> None:
    suffix = unique_suffix()
    email = f"smoke-{suffix}@example.com"
    password = "smoke-password-123"

    register = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert register.status_code == 201, register.text

    headers = await sign_in(client, email, password)

    alias = f"smoke-{suffix}"
    created = await client.post(
        "/api/v1/links",
        headers=headers,
        json={
            "destination_url": "https://example.com/smoke-target",
            "custom_alias": alias,
            "rules": {"password": "link-password-123", "click_limit": 5},
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["short_code"] == alias
    assert body["password_protected"] is True

    # The password challenge blocks the redirect until it is solved.
    challenge = await client.get(f"/{alias}")
    assert challenge.status_code == 401, challenge.text
    assert "Enter Link Password" in challenge.text

    verified = await client.post(
        "/api/v1/links/verify-password",
        data={"short_code": alias, "password": "link-password-123"},
    )
    assert verified.status_code == 303, verified.text

    redirected = await client.get(f"/{alias}")
    assert redirected.status_code == 302, redirected.text
    assert redirected.headers["location"] == "https://example.com/smoke-target"

    overview = await client.get("/api/v1/analytics/overview", headers=headers)
    assert overview.status_code == 200, overview.text

    link_analytics = await client.get(f"/api/v1/links/{body['id']}/analytics", headers=headers)
    assert link_analytics.status_code == 200, link_analytics.text
    assert link_analytics.json()["link"]["short_code"] == alias


@pytest.mark.asyncio
async def test_csv_import_creates_links(client: AsyncClient) -> None:
    suffix = unique_suffix()
    email = f"smoke-csv-{suffix}@example.com"
    password = "smoke-password-123"

    register = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert register.status_code == 201, register.text
    headers = await sign_in(client, email, password)

    csv_content = (
        "destination_url,custom_alias,click_limit\n"
        f"https://example.com/one,csv-{suffix}-one,10\n"
        f"https://example.com/two,csv-{suffix}-two,20\n"
        "not-a-url,csv-broken-row,5\n"
    )
    response = await client.post(
        "/api/v1/links/bulk",
        headers=headers,
        files={"file": ("links.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_processed"] == 3
    assert body["successful_imports"] == 2
    assert body["failed_imports"] == 1
    assert body["errors"][0]["row"] == 4


@pytest.mark.asyncio
async def test_admin_kill_switch_stops_the_redirect(client: AsyncClient) -> None:
    if API_KEY:
        headers = {"Authorization": f"Bearer {API_KEY}"}
    elif ADMIN_EMAIL and ADMIN_PASSWORD:
        headers = await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    else:
        pytest.skip(
            "set LINKPULSE_SMOKE_ADMIN_EMAIL and LINKPULSE_SMOKE_ADMIN_PASSWORD "
            "(or LINKPULSE_SMOKE_API_KEY) to exercise the kill switch"
        )

    suffix = unique_suffix()
    alias = f"smoke-admin-{suffix}"
    created = await client.post(
        "/api/v1/links",
        headers=headers,
        json={
            "destination_url": "https://example.com/kill-switch",
            "custom_alias": alias,
        },
    )
    assert created.status_code == 201, created.text
    link_id = created.json()["id"]

    before = await client.get(f"/{alias}")
    assert before.status_code == 302, before.text

    disabled = await client.patch(
        f"/api/v1/admin/links/{link_id}/status",
        headers=headers,
        json={"is_active": False, "reason": "smoke test kill switch"},
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["cache_cleared"] is True

    after = await client.get(f"/{alias}")
    assert after.status_code == 410, after.text

    # Historical analytics survive the deactivation.
    analytics = await client.get(f"/api/v1/links/{link_id}/analytics", headers=headers)
    assert analytics.status_code == 200, analytics.text
    assert analytics.json()["link"]["status"] == "disabled"
