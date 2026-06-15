"""Dev seed script — verifies DB connectivity; populates minimal dev data."""
import asyncio

from sqlalchemy import text

from app.core.db import SessionLocal


async def seed() -> None:
    async with SessionLocal() as session:
        result = await session.execute(text("SELECT current_database()"))
        db_name = result.scalar_one()
        print(f"Connected to database: {db_name}")
        print("Phase 0: no seed data needed yet.")


if __name__ == "__main__":
    asyncio.run(seed())
