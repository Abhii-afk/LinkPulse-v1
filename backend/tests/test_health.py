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
    monkeypatch.setattr(health, "check_workers", AsyncMock(return_value="ok"))

    response = await health.health(request_with_redis())

    assert response.status_code == 200
    body = json.loads(response.body)
    assert body["status"] == "ok"
    assert body["service"] == "linkpulse-api"
    assert body["checks"] == {
        "database": "ok",
        "redis": "ok",
        "worker": "ok",
    }


@pytest.mark.asyncio
async def test_health_returns_503_when_a_service_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    unavailable = AsyncMock(side_effect=ConnectionError("service unavailable"))
    monkeypatch.setattr(health, "check_database", unavailable)
    monkeypatch.setattr(health, "check_redis", AsyncMock())
    monkeypatch.setattr(health, "check_workers", AsyncMock(return_value="absent"))

    response = await health.health(request_with_redis())

    assert response.status_code == 503
    body = json.loads(response.body)
    assert body["status"] == "unavailable"
    assert body["checks"] == {
        "database": "unavailable",
        "redis": "ok",
        "worker": "absent",
    }


@pytest.mark.asyncio
async def test_a_missing_worker_does_not_make_the_api_unready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(health, "check_database", AsyncMock())
    monkeypatch.setattr(health, "check_redis", AsyncMock())
    monkeypatch.setattr(health, "check_workers", AsyncMock(return_value="absent"))

    response = await health.health(request_with_redis())

    assert response.status_code == 200
    assert json.loads(response.body)["checks"]["worker"] == "absent"


@pytest.mark.asyncio
async def test_liveness_never_touches_a_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail() -> None:
        raise AssertionError("liveness must not touch PostgreSQL or Redis")

    monkeypatch.setattr(health, "check_database", fail)
    monkeypatch.setattr(health, "check_redis", fail)

    response = await health.liveness()

    assert response.status_code == 200
    assert json.loads(response.body) == {"status": "ok", "service": "linkpulse-api"}


@pytest.mark.asyncio
async def test_worker_check_reports_absent_when_no_worker_ever_ran() -> None:
    class EmptyRedis:
        async def smembers(self, _key: str) -> set[str]:
            return set()

    assert await health.check_workers(EmptyRedis()) == "absent"


@pytest.mark.asyncio
async def test_worker_check_reports_unknown_when_redis_cannot_be_reached() -> None:
    class BrokenRedis:
        async def smembers(self, _key: str) -> set[str]:
            raise ConnectionError("redis unavailable")

    assert await health.check_workers(BrokenRedis()) == "unknown"
