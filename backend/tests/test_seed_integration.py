"""Integration tests for the demo seed against a real PostgreSQL database.

The test is skipped unless `LINKPULSE_TEST_DATABASE_URL` points at a
database that is safe to write to, for example the compose database:

    cd backend && LINKPULSE_TEST_DATABASE_URL=postgresql+asyncpg://linkpulse:linkpulse@127.0.0.1:5432/linkpulse \
        pytest tests/test_seed_integration.py -q

It only touches the rows the seed itself creates.
"""

import os

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.click_event import ClickEvent
from app.models.link import Link
from app.models.user import User
from app.services.demo_seed import (
    ADMIN_EMAIL,
    DEMO_USER_EMAIL,
    build_seed_links,
    reset_demo_data,
    seed_demo_data,
)
from app.core.security import verify_password


DATABASE_URL = os.environ.get("LINKPULSE_TEST_DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="set LINKPULSE_TEST_DATABASE_URL to run the seed integration test",
)


@pytest.fixture
async def session_factory():
    engine = create_async_engine(DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await reset_demo_data(session)
    try:
        yield factory
    finally:
        async with factory() as session:
            await reset_demo_data(session)
        await engine.dispose()


@pytest.mark.asyncio
async def test_the_seed_creates_the_workspace_and_is_repeatable(
    session_factory,
) -> None:
    async with session_factory() as session:
        first = await seed_demo_data(
            db=session,
            admin_password="admin-password-123",
            user_password="demo-password-123",
        )

        assert first.admin.email == ADMIN_EMAIL
        assert first.admin.role == "admin"
        assert first.demo_user.email == DEMO_USER_EMAIL
        assert first.demo_user.role == "user"
        assert len(first.links) == len(build_seed_links())
        assert first.click_events > 0

        # Running the seed again must not duplicate anything.
        second = await seed_demo_data(
            db=session,
            admin_password="admin-password-123",
            user_password="demo-password-123",
        )
        assert second.click_events == 0

        users = (
            await session.execute(
                select(User).where(
                    User.email.in_([ADMIN_EMAIL, DEMO_USER_EMAIL])
                )
            )
        ).scalars().all()
        assert len(users) == 2

        links = (await session.execute(select(Link))).scalars().all()
        seed_codes = {seed.short_code for seed in build_seed_links()}
        assert {link.short_code for link in links} >= seed_codes

        # Only the rows this test owns are counted. Other tools may have
        # written to the same database.
        seeded_ids = [link.id for link in links if link.short_code in seed_codes]
        events = (
            await session.execute(
                select(func.count())
                .select_from(ClickEvent)
                .where(ClickEvent.link_id.in_(seeded_ids))
            )
        ).scalar_one()
        assert events == first.click_events


@pytest.mark.asyncio
async def test_the_seeded_passwords_are_hashed_and_never_stored_in_clear(
    session_factory,
) -> None:
    async with session_factory() as session:
        result = await seed_demo_data(
            db=session,
            admin_password="admin-password-123",
            user_password="demo-password-123",
        )

        admin = (
            await session.execute(select(User).where(User.email == ADMIN_EMAIL))
        ).scalar_one()
        assert admin.password_hash != "admin-password-123"
        assert verify_password("admin-password-123", admin.password_hash)

        protected = (
            await session.execute(
                select(Link).where(Link.short_code == "demo-protected")
            )
        ).scalar_one()
        assert protected.password_hash is not None
        assert protected.password_hash != "link-password-123"
        assert verify_password("link-password-123", protected.password_hash)
        assert result.links["demo-protected"].id == protected.id


@pytest.mark.asyncio
async def test_the_durable_click_count_matches_the_written_events(
    session_factory,
) -> None:
    async with session_factory() as session:
        await seed_demo_data(
            db=session,
            admin_password="admin-password-123",
            user_password="demo-password-123",
        )

        seed_codes = {seed.short_code for seed in build_seed_links()}
        for link in (await session.execute(select(Link))).scalars().all():
            if link.short_code not in seed_codes:
                continue
            stored = (
                await session.execute(
                    select(func.count())
                    .select_from(ClickEvent)
                    .where(ClickEvent.link_id == link.id)
                )
            ).scalar_one()
            assert link.total_clicks == stored, link.short_code
