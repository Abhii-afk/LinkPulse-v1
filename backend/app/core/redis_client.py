import redis.asyncio as redis
from fastapi import Request
from redis.asyncio import Redis

from app.core.config import settings


def create_redis_client(url: str = settings.redis_url) -> Redis:
    return redis.from_url(url, decode_responses=True)


async def ping_redis(client: Redis) -> None:
    """Raise if Redis does not answer a ping."""

    await client.ping()


async def get_redis(request: Request) -> Redis:
    return request.app.state.redis
