import asyncio

from app.core.database import engine, ping_database
from app.core.redis_client import create_redis_client, ping_redis


async def run() -> int:
    failures: list[str] = []

    try:
        await ping_database()
        print("database: ok")
    except Exception:
        print("database: unavailable")
        failures.append("database")

    redis_client = create_redis_client()
    try:
        await ping_redis(redis_client)
        print("redis: ok")
    except Exception:
        print("redis: unavailable")
        failures.append("redis")
    finally:
        await redis_client.aclose()
        await engine.dispose()

    if failures:
        print(f"service check failed: {', '.join(failures)}")
        return 1

    print("service check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
