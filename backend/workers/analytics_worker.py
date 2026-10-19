import asyncio
import json
import logging
import os
import socket
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import ResponseError
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.database import async_session_factory, engine
from app.core.redis_client import create_redis_client
from app.models.click_event import ClickEvent
from app.services.geolocation import GeoLocator
from app.services.user_agent import parse_user_agent


logger = logging.getLogger(__name__)

StreamMessage = tuple[str, dict[str, str]]


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _flatten_stream_response(response: Any) -> list[StreamMessage]:
    messages: list[StreamMessage] = []
    for _stream_name, entries in response or []:
        for message_id, fields in entries:
            messages.append(
                (
                    _text(message_id),
                    {_text(key): _text(value) for key, value in fields.items()},
                )
            )
    return messages


def _parse_clicked_at(value: Any) -> datetime:
    parsed = datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class AnalyticsWorker:
    """Consume click events, persist batches, then acknowledge them."""

    def __init__(
        self,
        *,
        redis: Redis,
        session_factory: async_sessionmaker[AsyncSession],
        stream_name: str = settings.analytics_stream_name,
        consumer_group: str = settings.analytics_consumer_group,
        consumer_name: str | None = None,
        batch_size: int = settings.analytics_batch_size,
        block_ms: int = settings.analytics_block_ms,
        claim_min_idle_ms: int = settings.analytics_claim_min_idle_ms,
        geolocator: GeoLocator | None = None,
    ) -> None:
        self.redis = redis
        self.session_factory = session_factory
        self.stream_name = stream_name
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name or f"{socket.gethostname()}-{os.getpid()}"
        self.batch_size = batch_size
        self.block_ms = block_ms
        self.claim_min_idle_ms = claim_min_idle_ms
        self.geolocator = geolocator or GeoLocator(
            db_path=settings.geolite2_city_db_path,
            mock_country_code=settings.geoip_mock_country_code,
            mock_city=settings.geoip_mock_city,
        )

    async def ensure_consumer_group(self) -> None:
        try:
            await self.redis.xgroup_create(
                self.stream_name,
                self.consumer_group,
                id="0-0",
                mkstream=True,
            )
        except ResponseError as error:
            if "BUSYGROUP" not in str(error):
                raise

    async def reclaim_stale_messages(self) -> list[StreamMessage]:
        result = await self.redis.xautoclaim(
            self.stream_name,
            self.consumer_group,
            self.consumer_name,
            self.claim_min_idle_ms,
            start_id="0-0",
            count=self.batch_size,
        )
        if not result or len(result) < 2:
            return []
        return _flatten_stream_response([("claimed", result[1])])

    async def read_new_messages(self) -> list[StreamMessage]:
        response = await self.redis.xreadgroup(
            self.consumer_group,
            self.consumer_name,
            {self.stream_name: ">"},
            count=self.batch_size,
            block=self.block_ms,
        )
        return _flatten_stream_response(response)

    def build_click_record(self, message_id: str, fields: Mapping[str, str]) -> dict[str, Any]:
        payload_raw = fields.get("payload")
        if not payload_raw:
            raise ValueError("Click event is missing its payload")

        payload = json.loads(payload_raw)
        if not isinstance(payload, dict):
            raise ValueError("Click event payload must be an object")

        link_id = UUID(str(payload["link_id"]))
        user_agent = str(payload.get("user_agent") or "")
        ip_address = str(payload.get("ip") or payload.get("ip_address") or "unknown")
        referrer = str(payload.get("referrer") or "")
        parsed_ua = parse_user_agent(user_agent)
        location = self.geolocator.resolve(ip_address)

        return {
            "link_id": link_id,
            "stream_message_id": message_id,
            "clicked_at": _parse_clicked_at(payload["timestamp"]),
            "ip_address": ip_address,
            "country_code": location.country_code,
            "city": location.city,
            "user_agent": user_agent,
            "browser": parsed_ua.browser,
            "os": parsed_ua.os,
            "device_type": parsed_ua.device_type,
            "referrer": referrer,
            "is_bot": parsed_ua.is_bot,
            # ML anomaly detection is intentionally out of scope for this slice.
            "is_anomalous": False,
        }

    async def persist_batch(self, records: Iterable[dict[str, Any]]) -> None:
        values = list(records)
        if not values:
            return

        statement = postgres_insert(ClickEvent).values(values)
        statement = statement.on_conflict_do_nothing(
            index_elements=[ClickEvent.stream_message_id],
        )

        async with self.session_factory() as session:
            try:
                await session.execute(statement)
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def process_messages(self, messages: list[StreamMessage]) -> bool:
        if not messages:
            return True

        try:
            records = [self.build_click_record(message_id, fields) for message_id, fields in messages]
            await self.persist_batch(records)
        except Exception:
            logger.exception("Click event batch failed; leaving messages pending for retry")
            return False

        message_ids = [message_id for message_id, _fields in messages]
        try:
            acknowledged = await self.redis.xack(
                self.stream_name,
                self.consumer_group,
                *message_ids,
            )
            if int(acknowledged) != len(message_ids):
                logger.error("Only %s of %s click events were acknowledged", acknowledged, len(message_ids))
                return False
        except Exception:
            # PostgreSQL has already committed. The unique stream_message_id
            # makes a later retry idempotent, and the pending entries remain
            # claimable instead of being silently lost.
            logger.exception("Click event acknowledgement failed; messages remain pending")
            return False
        return True

    async def run_once(self) -> bool:
        reclaimed = await self.reclaim_stale_messages()
        if reclaimed:
            return await self.process_messages(reclaimed)

        return await self.process_messages(await self.read_new_messages())

    async def run_forever(self) -> None:
        await self.ensure_consumer_group()
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Analytics worker iteration failed; retrying")
                await asyncio.sleep(1)


async def main() -> None:
    redis = create_redis_client()
    geolocator = GeoLocator(
        db_path=settings.geolite2_city_db_path,
        mock_country_code=settings.geoip_mock_country_code,
        mock_city=settings.geoip_mock_city,
    )
    worker = AnalyticsWorker(
        redis=redis,
        session_factory=async_session_factory,
        geolocator=geolocator,
    )
    try:
        await worker.run_forever()
    finally:
        geolocator.close()
        await redis.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
