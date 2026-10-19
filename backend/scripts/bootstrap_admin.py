import argparse
import asyncio
import getpass

from sqlalchemy import select

from app.core.database import async_session_factory, engine
from app.core.security import hash_password, normalize_email
from app.models.user import User, UserRole


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create the first LinkPulse administrator")
    parser.add_argument("--email", required=True, help="Email address for the new administrator")
    return parser.parse_args()


async def create_admin(email: str, password: str) -> int:
    async with async_session_factory() as db:
        existing = await db.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none() is not None:
            print("admin bootstrap refused: email already exists")
            return 1

        db.add(
            User(
                email=email,
                password_hash=hash_password(password),
                role=UserRole.ADMIN.value,
            )
        )
        await db.commit()

    print("admin bootstrap complete")
    return 0


async def run() -> int:
    args = parse_args()
    try:
        email = normalize_email(args.email)
    except ValueError as error:
        print(f"admin bootstrap refused: {error}")
        return 1

    password = getpass.getpass("Admin password: ")
    confirmation = getpass.getpass("Confirm admin password: ")
    if password != confirmation:
        print("admin bootstrap refused: passwords do not match")
        return 1

    try:
        return await create_admin(email, password)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
