from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import ping_database
from app.core.heartbeat import read_worker_heartbeats, summarise_workers
from app.core.redis_client import ping_redis


router = APIRouter(tags=["system"])

SERVICE_NAME = "linkpulse-api"


async def check_database() -> None:
    await ping_database()


async def check_redis(client: object) -> None:
    await ping_redis(client)  # type: ignore[arg-type]


async def check_workers(client: object) -> str:
    """Report whether an analytics worker is publishing heartbeats."""

    try:
        states = await read_worker_heartbeats(client)  # type: ignore[arg-type]
    except Exception:
        return "unknown"
    return summarise_workers(states)


@router.get("/health/live")
async def liveness() -> JSONResponse:
    """Liveness probe.

    It never touches PostgreSQL or Redis, so a short outage of a dependency
    cannot make an orchestrator restart an otherwise healthy API process.
    """

    return JSONResponse(content={"status": "ok", "service": SERVICE_NAME})


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    """Readiness probe.

    The API is only ready when PostgreSQL and Redis answer. The analytics
    worker is reported for visibility but does not gate readiness: clicks
    keep buffering in the Redis stream while the worker is away.
    """

    checks: dict[str, str] = {}

    try:
        await check_database()
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"

    try:
        await check_redis(request.app.state.redis)
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "unavailable"

    checks["worker"] = await check_workers(request.app.state.redis)

    healthy = all(checks[name] == "ok" for name in ("database", "redis"))
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "ok" if healthy else "unavailable",
            "service": SERVICE_NAME,
            "environment": settings.app_env,
            "checks": checks,
        },
    )
