"""Unit tests for the demo seed definitions.

The parts that touch PostgreSQL are covered by
``tests/test_seed_integration.py``, which runs against a real database.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.services.demo_seed import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    DEMO_USER_EMAIL,
    DEMO_USER_PASSWORD,
    LINK_PASSWORD,
    build_campaigns,
    build_click_rows,
    build_seed_links,
)
from app.services.user_agent import parse_user_agent


def test_the_seed_contains_every_status_the_dashboard_can_show() -> None:
    seeds = build_seed_links()

    codes = [seed.short_code for seed in seeds]
    assert codes == [
        "demo-launch",
        "demo-newsletter",
        "demo-protected",
        "demo-limited",
        "demo-expired",
        "demo-disabled",
    ]
    assert len(set(codes)) == len(codes)

    by_code = {seed.short_code: seed for seed in seeds}
    assert by_code["demo-launch"].is_active is True
    assert by_code["demo-protected"].password == LINK_PASSWORD
    assert by_code["demo-limited"].click_limit == 25
    assert by_code["demo-expired"].expires_at is not None
    assert by_code["demo-expired"].expires_at < datetime.now(timezone.utc)
    assert by_code["demo-disabled"].is_active is False
    assert by_code["demo-disabled"].deactivation_reason


def test_every_seeded_link_belongs_to_a_seeded_campaign() -> None:
    campaign_names = {name for name, _ in build_campaigns()}

    for seed in build_seed_links():
        assert seed.campaign_name in campaign_names


def test_the_click_history_is_reproducible() -> None:
    class FakeLink:
        id = uuid4()
        short_code = "demo-launch"

    seed = build_seed_links()[0]
    first = build_click_rows(FakeLink(), seed)
    second = build_click_rows(FakeLink(), seed)

    assert [row["stream_message_id"] for row in first] == [
        row["stream_message_id"] for row in second
    ]
    assert len(first) == sum(seed.daily_clicks) + 3


def test_the_click_history_contains_bots_and_humans() -> None:
    class FakeLink:
        id = uuid4()
        short_code = "demo-launch"

    rows = build_click_rows(FakeLink(), build_seed_links()[0])
    bots = [row for row in rows if row["is_bot"]]
    humans = [row for row in rows if not row["is_bot"]]

    assert len(bots) == 3
    assert len(humans) == sum(build_seed_links()[0].daily_clicks)
    assert {row["device_type"] for row in humans} >= {"Desktop", "Mobile"}


def test_the_click_history_spans_the_last_two_weeks() -> None:
    class FakeLink:
        id = uuid4()
        short_code = "demo-launch"

    rows = build_click_rows(FakeLink(), build_seed_links()[0])
    stamps = [row["clicked_at"] for row in rows]
    now = datetime.now(timezone.utc)

    assert max(stamps) <= now
    assert min(stamps) > now - timedelta(days=15)
    assert all(stamp.tzinfo is not None for stamp in stamps)


def test_the_bot_rows_use_the_shared_user_agent_parser() -> None:
    class FakeLink:
        id = uuid4()
        short_code = "demo-launch"

    rows = build_click_rows(FakeLink(), build_seed_links()[0])
    for row in rows:
        parsed = parse_user_agent(row["user_agent"])
        assert row["is_bot"] == parsed.is_bot
        assert row["browser"] == parsed.browser
        assert row["device_type"] == parsed.device_type


def test_the_seeded_accounts_have_known_credentials() -> None:
    assert ADMIN_EMAIL == "admin@linkpulse.local"
    assert DEMO_USER_EMAIL == "demo@linkpulse.local"
    assert ADMIN_PASSWORD
    assert DEMO_USER_PASSWORD
    assert len(DEMO_USER_PASSWORD) >= 8
    assert len(ADMIN_PASSWORD) >= 8
