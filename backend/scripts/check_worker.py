"""Report whether an analytics worker is alive.

    cd backend && python -m scripts.check_worker

Exits with 0 when at least one worker published a fresh heartbeat and with 1
otherwise, which makes it usable as a container health check.
"""

import asyncio
import sys

from app.core.database import engine
from app.core.heartbeat import read_worker_heartbeats
from app.core.redis_client import create_redis_client


async def run() -> int:
    redis = create_redis_client()
    try:
        states = await read_worker_heartbeats(redis)
    except Exception as error:
        print(f"worker heartbeat check failed: {error}")
        return 1
    finally:
        await redis.aclose()
        await engine.dispose()

    if not states:
        print("no worker has ever reported")
        return 1

    alive = [name for name, state in states.items() if state == "ok"]
    if not alive:
        print(f"no live worker, states: {states}")
        return 1

    print(f"live workers: {', '.join(sorted(alive))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
