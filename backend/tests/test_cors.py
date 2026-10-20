"""The API has to answer browser preflight requests.

The front end is served from a different origin than the API, so the browser
sends an OPTIONS preflight before every call. Without the CORS headers the
request never leaves the browser and the UI reports that the backend is
unreachable.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app


ORIGIN = "http://127.0.0.1:5173"


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client


@pytest.mark.asyncio
async def test_the_preflight_for_a_link_creation_is_allowed(
    client: AsyncClient,
) -> None:
    response = await client.request(
        "OPTIONS",
        "/api/v1/links",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed_headers
    assert "content-type" in allowed_headers


@pytest.mark.asyncio
async def test_the_actual_request_carries_the_origin_header(
    client: AsyncClient,
) -> None:
    response = await client.get("/health/live", headers={"Origin": ORIGIN})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN


@pytest.mark.asyncio
async def test_an_unknown_origin_is_not_allowed(client: AsyncClient) -> None:
    response = await client.request(
        "OPTIONS",
        "/api/v1/links",
        headers={
            "Origin": "https://not-allowed.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert "access-control-allow-origin" not in response.headers


def test_the_configured_origins_are_parsed() -> None:
    assert "http://127.0.0.1:5173" in settings.cors_origins
    assert "http://localhost:5173" in settings.cors_origins


def test_the_cors_origins_can_be_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings,
        "cors_allowed_origins",
        "https://app.example, https://admin.example",
    )

    assert settings.cors_origins == ["https://app.example", "https://admin.example"]
