import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.routers import health


def request_with_redis() -> SimpleNamespace:
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(redis=object()))
    )


@pytest.mark.asyncio
async def test_health_returns_ok_when_both_services_are_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health, "check_database", AsyncMock())
    monkeypatch.setattr(health, "check_redis", AsyncMock())

    response = await health.health(request_with_redis())

    assert response.status_code == 200
    assert json.loads(response.body) == {
        "status": "ok",
        "checks": {"database": "ok", "redis": "ok"},
    }


@pytest.mark.asyncio
async def test_health_returns_503_when_a_service_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    unavailable = AsyncMock(side_effect=ConnectionError("service unavailable"))
    monkeypatch.setattr(health, "check_database", unavailable)
    monkeypatch.setattr(health, "check_redis", AsyncMock())

    response = await health.health(request_with_redis())

    assert response.status_code == 503
    assert json.loads(response.body) == {
        "status": "unavailable",
        "checks": {"database": "unavailable", "redis": "ok"},
    }
