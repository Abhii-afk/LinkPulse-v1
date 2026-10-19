from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.database import ping_database
from app.core.redis_client import ping_redis


router = APIRouter(tags=["system"])


async def check_database() -> None:
    await ping_database()


async def check_redis(client: object) -> None:
    await ping_redis(client)  # type: ignore[arg-type]


@router.get("/health")
async def health(request: Request) -> JSONResponse:
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

    healthy = all(result == "ok" for result in checks.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ok" if healthy else "unavailable", "checks": checks},
    )
