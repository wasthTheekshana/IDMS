"""One-off CLI to create a platform admin account. Never exposed via any API
route — run manually per environment.

Usage:
    uv run python -m app.scripts.create_platform_admin --email you@example.com
"""

import argparse
import asyncio
import getpass
import uuid

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models.platform_admin import PlatformAdmin
from app.repositories.platform_admin import PlatformAdminRepository


async def _create(email: str, password: str) -> None:
    async with SessionLocal.begin() as session:
        repo = PlatformAdminRepository(session)
        existing = await repo.get_by_email(email)
        if existing:
            raise SystemExit(f"A platform admin with email {email!r} already exists.")
        session.add(
            PlatformAdmin(
                id=uuid.uuid4(), email=email, password_hash=hash_password(password)
            )
        )
    print(f"Platform admin created: {email}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a platform admin account")
    parser.add_argument("--email", required=True)
    args = parser.parse_args()

    password = getpass.getpass("Password (min 10 characters): ")
    if len(password) < 10:
        raise SystemExit("Password must be at least 10 characters")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("Passwords do not match")

    asyncio.run(_create(args.email, password))


if __name__ == "__main__":
    main()
