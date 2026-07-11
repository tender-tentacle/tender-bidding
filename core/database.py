"""Database engine for the bidding service.

Uses its OWN isolated database (a dedicated Azure SQL server in production; a
local SQLite file for dev/tests). Schema is created with SQLAlchemy
``create_all`` — this service has no Liquibase changelog (matching
predictive-crawling's approach) — so a fresh DB is fully provisioned on boot.
"""

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from core.config import DATABASE_URL
from core.logger import setup_logger

logger = setup_logger("bidding-db")

_url = DATABASE_URL
if not _url:
    # Local SQLite fallback. Prefer /data (Docker named volume) when writable,
    # else the service directory — never crash on an unwritable /data (dev/tests).
    data_dir = os.getenv("SQLITE_DATA_DIR", "/data")
    try:
        os.makedirs(data_dir, exist_ok=True)
        if not os.access(data_dir, os.W_OK):
            raise OSError(f"{data_dir} not writable")
    except OSError:
        data_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _url = f"sqlite+aiosqlite:///{data_dir}/bidding.db"

DATABASE_URL_RESOLVED = _url

# Server DBs get a pooled engine with pre-ping + recycling (Azure SQL closes
# idle connections aggressively); SQLite gets its own connect_args.
engine_kwargs: dict = {}
if _url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs.update(
        {"pool_pre_ping": True, "pool_recycle": 300, "pool_size": 10, "max_overflow": 10, "pool_timeout": 30}
    )

engine = create_async_engine(_url, **engine_kwargs)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    """Create all tables (idempotent) and seed the static portal-guide library."""
    import models.bid  # noqa: F401 — register mappers with Base.metadata

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info(f"🔌 Bidding DB ready at {_url.split('@')[-1]}")

    from services.portal_guide import seed_portal_guides

    await seed_portal_guides()
