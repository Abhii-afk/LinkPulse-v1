"""Create the LinkPulse demo workspace.

    cd backend && python -m scripts.seed_demo_data
    cd backend && python -m scripts.seed_demo_data --reset

The command is safe to run repeatedly: rows are matched on their natural key
and updated in place, so the dashboard keeps the same numbers.
"""

import argparse
import asyncio
import os

from app.core.database import async_session_factory, engine
from app.core.redis_client import create_redis_client
from app.services.demo_seed import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    DEMO_USER_EMAIL,
    DEMO_USER_PASSWORD,
    LINK_PASSWORD,
    seed_demo_data,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed the LinkPulse demo workspace")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the previously seeded rows before seeding again",
    )
    parser.add_argument(
        "--admin-password",
        default=os.environ.get("LINKPULSE_SEED_ADMIN_PASSWORD", ADMIN_PASSWORD),
        help="Password for the demo administrator",
    )
    parser.add_argument(
        "--user-password",
        default=os.environ.get("LINKPULSE_SEED_USER_PASSWORD", DEMO_USER_PASSWORD),
        help="Password for the demo user",
    )
    return parser.parse_args()


async def run() -> int:
    args = parse_args()
    redis = create_redis_client()

    try:
        async with async_session_factory() as db:
            result = await seed_demo_data(
                db=db,
                redis=redis,
                admin_password=args.admin_password or None,
                user_password=args.user_password,
                reset=args.reset,
            )
    finally:
        await redis.aclose()
        await engine.dispose()

    print("LinkPulse demo data is ready.")
    print(f"  demo user : {DEMO_USER_EMAIL} / {args.user_password}")
    print(f"  admin     : {ADMIN_EMAIL} / {result.admin_password}")
    print(f"  campaigns : {', '.join(sorted(result.campaigns))}")
    print(f"  links     : {', '.join(sorted(result.links))}")
    print(f"  click rows: {result.click_events} written")
    print()
    print("Password protected demo link: demo-protected")
    print(f"  short code : demo-protected")
    print(f"  password   : {LINK_PASSWORD}")
    print("  url        : <PUBLIC_BASE_URL>/demo-protected")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
