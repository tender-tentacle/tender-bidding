import asyncio

from core.database import engine
from sqlalchemy import text


async def check():
    async with engine.begin() as conn:
        res = await conn.execute(text("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'company_profiles'"))
        print([r[0] for r in res.fetchall()])

asyncio.run(check())
