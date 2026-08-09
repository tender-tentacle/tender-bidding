import asyncio

from core.database import engine
from sqlalchemy import text


async def wipe():
    async with engine.begin() as conn:
        try:
            await conn.execute(text("DROP TABLE company_profiles"))
            print("Dropped company_profiles.")
        except Exception as e:
            print("Error dropping company_profiles:", e)


asyncio.run(wipe())
