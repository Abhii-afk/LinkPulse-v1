import pytest

from app.core.heartbeat import (
    WORKER_NAME_KEY,
    heartbeat_key,
    publish_heartbeat,
    read_worker_heartbeats,
    summarise_workers,
)


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.names: set[str] = set()
        self.ttls: dict[str, int | None] = {}

    async def set(self, key: str, value: str, *, ex: int | None = None) -> bool:
        self.values[key] = value
        self.ttls[key] = ex
        return True

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def sadd(self, key: str, value: str) -> int:
        if key != WORKER_NAME_KEY:
            raise AssertionError(f"unexpected set key: {key}")
        if value in self.names:
            return 0
        self.names.add(value)
        return 1

    async def smembers(self, key: str) -> set[str]:
        if key != WORKER_NAME_KEY:
            raise AssertionError(f"unexpected set key: {key}")
        return set(self.names)


@pytest.mark.asyncio
async def test_publishing_a_heartbeat_records_the_worker_as_alive() -> None:
    redis = FakeRedis()

    await publish_heartbeat(redis, "worker-a")

    assert redis.names == {"worker-a"}
    assert redis.values[heartbeat_key("worker-a")]
    assert redis.ttls[heartbeat_key("worker-a")] == 90
    assert await read_worker_heartbeats(redis) == {"worker-a": "ok"}


@pytest.mark.asyncio
async def test_a_worker_that_stopped_reporting_becomes_stale() -> None:
    redis = FakeRedis()
    await publish_heartbeat(redis, "worker-a")

    redis.values.pop(heartbeat_key("worker-a"))

    assert await read_worker_heartbeats(redis) == {"worker-a": "stale"}


@pytest.mark.asyncio
async def test_no_worker_has_ever_reported() -> None:
    redis = FakeRedis()

    assert await read_worker_heartbeats(redis) == {}
    assert summarise_workers({}) == "absent"


def test_worker_states_are_summarised() -> None:
    assert summarise_workers({"a": "ok", "b": "stale"}) == "ok"
    assert summarise_workers({"a": "stale", "b": "stale"}) == "stale"
