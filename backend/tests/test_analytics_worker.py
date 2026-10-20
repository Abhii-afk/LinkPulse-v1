import json
from collections.abc import AsyncIterator
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from redis.exceptions import ResponseError

from app.services.geolocation import GeoLocation, GeoLocator
from app.services.user_agent import parse_user_agent
from workers.analytics_worker import AnalyticsWorker


LINK_ID = uuid4()
CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class FakeRedis:
    def __init__(self) -> None:
        self.acknowledged: list[str] = []
        self.calls: list[str] = []
        self.new_response: list[tuple[str, list[tuple[str, dict[str, str]]]]] = []
        self.claimed_response: tuple[str, list[tuple[str, dict[str, str]]], list[str]] = (
            "0-0",
            [],
            [],
        )
        self.ack_error = False
        self.group_error: ResponseError | None = None

    async def xgroup_create(
        self,
        _stream: str,
        _group: str,
        *,
        id: str,
        mkstream: bool,
    ) -> bool:
        self.calls.append(f"xgroup_create:{id}:{mkstream}")
        if self.group_error is not None:
            error = self.group_error
            self.group_error = None
            raise error
        return True

    async def xautoclaim(
        self,
        _stream: str,
        _group: str,
        _consumer: str,
        _min_idle_ms: int,
        *,
        start_id: str,
        count: int,
    ) -> tuple[str, list[tuple[str, dict[str, str]]], list[str]]:
        self.calls.append(f"xautoclaim:{start_id}:{count}")
        return self.claimed_response

    async def xreadgroup(
        self,
        _group: str,
        _consumer: str,
        _streams: dict[str, str],
        *,
        count: int,
        block: int,
    ) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        self.calls.append(f"xreadgroup:{count}:{block}")
        return self.new_response

    async def xack(self, _stream: str, _group: str, *message_ids: str) -> int:
        self.calls.append("xack")
        if self.ack_error:
            raise ConnectionError("Redis acknowledgement unavailable")
        self.acknowledged.extend(message_ids)
        return len(message_ids)


class FakeSavepoint:
    def __init__(self, session: "FakeSession") -> None:
        self.session = session

    async def __aenter__(self) -> "FakeSavepoint":
        return self

    async def __aexit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        return None


class FakeSession:
    def __init__(self, order: list[str]) -> None:
        self.order = order
        self.statements: list[object] = []
        self.commit_count = 0
        self.rollback_count = 0
        self.commit_error = False
        self.reject_stream_message_ids: set[str] = set()

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        return None

    async def execute(self, statement: object) -> None:
        self.order.append("execute")
        self.statements.append(statement)
        for message_id in self.reject_stream_message_ids:
            if message_id in str(statement.compile(compile_kwargs={"literal_binds": True})):
                raise RuntimeError("simulated constraint violation")

    def begin_nested(self) -> FakeSavepoint:
        self.order.append("begin_nested")
        return FakeSavepoint(self)

    async def commit(self) -> None:
        self.order.append("commit")
        if self.commit_error:
            raise RuntimeError("database unavailable")
        self.commit_count += 1

    async def rollback(self) -> None:
        self.order.append("rollback")
        self.rollback_count += 1


class FakeSessionFactory:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def __call__(self) -> AsyncIterator[FakeSession]:
        return self.session


class FakeReader:
    def city(self, _ip_address: str) -> SimpleNamespace:
        return SimpleNamespace(
            country=SimpleNamespace(iso_code="GB"),
            city=SimpleNamespace(name="London"),
        )

    def close(self) -> None:
        return None


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "short_code": "go",
        "link_id": str(LINK_ID),
        "timestamp": "2026-10-19T12:00:00+00:00",
        "ip": "203.0.113.10",
        "user_agent": CHROME_UA,
        "referrer": "https://referrer.example/",
    }
    payload.update(overrides)
    return payload


def event_message(message_id: str = "1-0", **overrides: object) -> tuple[str, dict[str, str]]:
    return message_id, {"payload": json.dumps(_payload(**overrides))}


def make_worker(
    redis: FakeRedis,
    session: FakeSession,
    *,
    geolocator: GeoLocator | None = None,
) -> AnalyticsWorker:
    return AnalyticsWorker(
        redis=redis,  # type: ignore[arg-type]
        session_factory=FakeSessionFactory(session),  # type: ignore[arg-type]
        stream_name="stream:clicks",
        consumer_group="click_group",
        consumer_name="test-consumer",
        batch_size=100,
        block_ms=2000,
        claim_min_idle_ms=60000,
        geolocator=geolocator or GeoLocator(db_path=None),
    )


@pytest.mark.parametrize(
    ("user_agent", "browser", "operating_system", "device_type", "is_bot"),
    [
        (CHROME_UA, "Chrome", "Windows", "Desktop", False),
        (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            "Safari",
            "iOS",
            "Mobile",
            False,
        ),
        ("curl/8.4.0", "curl", "Other", "Desktop", True),
        (
            "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
            "Googlebot",
            "Other",
            "Desktop",
            True,
        ),
        ("", "Other", "Other", "Desktop", True),
    ],
)
def test_user_agent_parser_extracts_metadata_and_detects_bots(
    user_agent: str,
    browser: str,
    operating_system: str,
    device_type: str,
    is_bot: bool,
) -> None:
    parsed = parse_user_agent(user_agent)

    assert parsed.browser == browser
    assert parsed.os == operating_system
    assert parsed.device_type == device_type
    assert parsed.is_bot is is_bot


def test_geolite2_reader_is_used_when_configured() -> None:
    locator = GeoLocator(db_path="/local/GeoLite2-City.mmdb", reader=FakeReader())

    assert locator.resolve("198.51.100.5") == GeoLocation("GB", "London")
    locator.close()


def test_geolocation_uses_deterministic_mock_fallback_without_local_data() -> None:
    locator = GeoLocator(db_path=None, mock_country_code="XX", mock_city="Mock City")

    assert locator.resolve("203.0.113.10") == GeoLocation("XX", "Mock City")


def test_missing_configured_geolite2_file_uses_mock_fallback() -> None:
    locator = GeoLocator(
        db_path="/missing/GeoLite2-City.mmdb",
        mock_country_code="XX",
        mock_city="Mock City",
    )

    assert locator.resolve("203.0.113.10") == GeoLocation("XX", "Mock City")


@pytest.mark.asyncio
async def test_worker_builds_click_record_with_visit_metadata() -> None:
    redis = FakeRedis()
    session = FakeSession([])
    worker = make_worker(redis, session, geolocator=GeoLocator(db_path=None))

    record = worker.build_click_record(*event_message("42-0"))

    assert record["link_id"] == LINK_ID
    assert record["stream_message_id"] == "42-0"
    assert record["ip_address"] == "203.0.113.10"
    assert record["country_code"] == "XX"
    assert record["city"] == "Mock City"
    assert record["browser"] == "Chrome"
    assert record["os"] == "Windows"
    assert record["device_type"] == "Desktop"
    assert record["referrer"] == "https://referrer.example/"
    assert record["is_bot"] is False
    assert record["is_anomalous"] is False


@pytest.mark.asyncio
async def test_worker_persists_one_batch_before_acknowledging_messages() -> None:
    order: list[str] = []
    redis = FakeRedis()
    redis.calls = order
    session = FakeSession(order)
    worker = make_worker(redis, session)
    messages = [event_message("1-0"), event_message("2-0", user_agent="curl/8.4.0")]

    processed = await worker.process_messages(messages)

    assert processed is True
    assert session.commit_count == 1
    assert len(session.statements) == 1
    assert redis.acknowledged == ["1-0", "2-0"]
    assert order == ["execute", "commit", "xack"]


@pytest.mark.asyncio
async def test_database_failure_leaves_messages_unacknowledged_for_retry() -> None:
    redis = FakeRedis()
    session = FakeSession([])
    session.commit_error = True
    worker = make_worker(redis, session)
    messages = [event_message("3-0")]

    first_attempt = await worker.process_messages(messages)

    assert first_attempt is False
    assert redis.acknowledged == []
    assert session.rollback_count == 1

    session.commit_error = False
    retry = await worker.process_messages(messages)

    assert retry is True
    assert redis.acknowledged == ["3-0"]
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_ack_failure_leaves_pending_message_retryable_and_insert_is_idempotent() -> None:
    redis = FakeRedis()
    redis.ack_error = True
    session = FakeSession([])
    worker = make_worker(redis, session)
    messages = [event_message("4-0")]

    first_attempt = await worker.process_messages(messages)

    assert first_attempt is False
    assert session.commit_count == 1
    assert redis.acknowledged == []

    redis.ack_error = False
    retry = await worker.process_messages(messages)

    assert retry is True
    assert session.commit_count == 2
    assert redis.acknowledged == ["4-0"]
    statement_sql = str(session.statements[0].compile(compile_kwargs={"literal_binds": True}))
    assert "ON CONFLICT (stream_message_id) DO NOTHING" in statement_sql


@pytest.mark.asyncio
async def test_malformed_event_is_not_acknowledged_or_persisted() -> None:
    redis = FakeRedis()
    session = FakeSession([])
    worker = make_worker(redis, session)

    processed = await worker.process_messages([("5-0", {"payload": "not-json"})])

    assert processed is False
    assert redis.acknowledged == []
    assert session.statements == []


@pytest.mark.asyncio
async def test_malformed_event_does_not_block_the_healthy_records_of_the_same_batch() -> None:
    redis = FakeRedis()
    session = FakeSession([])
    worker = make_worker(redis, session)
    messages = [
        ("5-0", {"payload": "not-json"}),
        ("6-0", {"payload": json.dumps(_payload())}),
    ]

    processed = await worker.process_messages(messages)

    # The healthy record is stored and acknowledged; only the malformed
    # message stays pending.
    assert processed is False
    assert redis.acknowledged == ["6-0"]
    assert len(session.statements) == 1


@pytest.mark.asyncio
async def test_record_rejected_by_the_database_does_not_block_the_rest_of_the_batch() -> None:
    redis = FakeRedis()
    session = FakeSession([])
    session.reject_stream_message_ids = {"7-0"}
    worker = make_worker(redis, session)
    messages = [
        ("7-0", {"payload": json.dumps(_payload())}),
        ("8-0", {"payload": json.dumps(_payload())}),
    ]

    processed = await worker.process_messages(messages)

    assert processed is False
    assert redis.acknowledged == ["8-0"]
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_batch_statement_keeps_the_durable_link_click_count_in_step() -> None:
    redis = FakeRedis()
    session = FakeSession([])
    worker = make_worker(redis, session)

    await worker.process_messages([("9-0", {"payload": json.dumps(_payload())})])

    statement_sql = str(session.statements[0].compile(compile_kwargs={"literal_binds": True}))
    assert "WITH inserted_clicks AS" in statement_sql
    assert "UPDATE links SET total_clicks" in statement_sql
    assert "ON CONFLICT (stream_message_id) DO NOTHING" in statement_sql


@pytest.mark.asyncio
async def test_worker_reclaims_pending_messages_before_reading_new_messages() -> None:
    order: list[str] = []
    redis = FakeRedis()
    redis.claimed_response = ("0-0", [event_message("6-0")], [])
    redis.new_response = [("stream:clicks", [event_message("7-0")])]
    session = FakeSession(order)
    worker = make_worker(redis, session)

    processed = await worker.run_once()

    assert processed is True
    assert redis.acknowledged == ["6-0"]
    assert "xreadgroup:100:2000" not in redis.calls


@pytest.mark.asyncio
async def test_worker_reads_new_messages_from_its_consumer_group() -> None:
    redis = FakeRedis()
    redis.new_response = [("stream:clicks", [event_message("7-0")])]
    session = FakeSession([])
    worker = make_worker(redis, session)

    await worker.ensure_consumer_group()
    processed = await worker.run_once()

    assert processed is True
    assert redis.calls[0] == "xgroup_create:0-0:True"
    assert "xreadgroup:100:2000" in redis.calls
    assert redis.acknowledged == ["7-0"]
