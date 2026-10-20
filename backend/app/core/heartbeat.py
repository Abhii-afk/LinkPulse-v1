"""Worker liveness heartbeats stored in Redis.

The analytics worker runs as its own process, so a deployment health check
has no other way of telling whether it is alive. The worker publishes a
short-lived key for its consumer name and the API reports those keys in its
readiness response.

The heartbeat is advisory: the redirect path keeps working while the worker
is down, the click events simply buffer in the Redis stream.
"""

from datetime import datetime, timezone

from redis.asyncio import Redis


WORKER_HEARTBEAT_PREFIX = "linkpulse:worker:heartbeat:"
WORKER_NAME_KEY = "linkpulse:worker:names"
DEFAULT_HEARTBEAT_TTL_SECONDS = 90


def heartbeat_key(name: str) -> str:
    return f"{WORKER_HEARTBEAT_PREFIX}{name}"


async def publish_heartbeat(
    redis: Redis,
    name: str,
    ttl_seconds: int = DEFAULT_HEARTBEAT_TTL_SECONDS,
) -> None:
    """Record that the worker named ``name`` is alive right now."""

    await redis.set(
        heartbeat_key(name),
        datetime.now(timezone.utc).isoformat(),
        ex=ttl_seconds,
    )
    await redis.sadd(WORKER_NAME_KEY, name)


async def read_worker_heartbeats(redis: Redis) -> dict[str, str]:
    """Return ``{worker name: state}`` for every worker that ever reported.

    ``ok`` means the heartbeat is still fresh, ``stale`` means the worker
    stopped reporting.
    """

    names = await redis.smembers(WORKER_NAME_KEY)
    states: dict[str, str] = {}
    for name in sorted(str(candidate) for candidate in names or []):
        beat = await redis.get(heartbeat_key(name))
        states[name] = "ok" if beat else "stale"
    return states


def summarise_workers(states: dict[str, str]) -> str:
    """Reduce the per-worker states to one health check value."""

    if not states:
        return "absent"
    if any(state == "ok" for state in states.values()):
        return "ok"
    return "stale"
