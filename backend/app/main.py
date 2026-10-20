from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from app.core.config import settings, validate_settings
from app.core.database import engine
from app.core.redis_client import create_redis_client
from app.routers.admin import router as admin_router
from app.routers.analytics import router as analytics_router
from app.routers.auth import router as auth_router
from app.routers.health import router as health_router
from app.routers.links import router as links_router
from app.routers.redirect import router as redirect_router
from app.routers.user import router as user_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Refuse to serve traffic with an incomplete or insecure configuration.
    validate_settings()
    redis_client = create_redis_client()
    app.state.redis = redis_client
    try:
        yield
    finally:
        await redis_client.aclose()
        await engine.dispose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(links_router)
app.include_router(user_router)
app.include_router(admin_router)
app.include_router(analytics_router)
app.include_router(redirect_router)
