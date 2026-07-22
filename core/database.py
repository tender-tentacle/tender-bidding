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
    sql_server = os.getenv("SQL_SERVER")
    if sql_server:
        sql_user = os.getenv("SQL_USER", "azureuser")
        sql_password = os.getenv("SQL_PASSWORD", "")
        db_name = os.getenv("SQL_DATABASE", "bidding")
        _url = f"mssql+aioodbc://{sql_user}:{sql_password}@{sql_server}:1433/{db_name}?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no&MARS_Connection=yes"
    else:
        import sys

        if "pytest" in sys.modules or os.getenv("PYTEST_CURRENT_TEST"):
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
        else:
            raise ValueError("DATABASE_URL environment variable is required")

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

        # Safe migration patch: check and add new columns to bid_required_document
        from sqlalchemy import text

        if _url.startswith("sqlite"):
            cols_res = await conn.execute(text("PRAGMA table_info(bid_required_document)"))
            existing_cols = {row[1] for row in cols_res.fetchall()}
            for col, col_type in [
                ("short_summary", "TEXT"),
                ("link_original_doc", "VARCHAR(1000)"),
                ("link_parsed_doc", "VARCHAR(1000)"),
                ("quote_original", "TEXT"),
                ("is_mandatory", "BOOLEAN DEFAULT 1"),
                ("status", "VARCHAR(20) DEFAULT 'open'"),
                ("user_override", "BOOLEAN DEFAULT 0"),
                ("uploaded_by", "VARCHAR(255)"),
                ("uploaded_at", "DATETIME"),
                ("uploaded_filename", "VARCHAR(500)"),
                ("extracted_metadata", "JSON"),
            ]:
                if col not in existing_cols:
                    await conn.execute(text(f"ALTER TABLE bid_required_document ADD COLUMN {col} {col_type}"))
                    logger.info(f"SQLite migration: Added column {col} to bid_required_document")

            cols_res = await conn.execute(text("PRAGMA table_info(bid)"))
            existing_cols = {row[1] for row in cols_res.fetchall()}
            if "selection_criteria" not in existing_cols:
                await conn.execute(text("ALTER TABLE bid ADD COLUMN selection_criteria JSON"))
                logger.info("SQLite migration: Added column selection_criteria to bid")
            for col in [
                "matched_labels",
                "matched_sectors",
                "matched_services",
                "matched_people",
                "matched_campaigns",
                "matched_trends",
                "matched_practices",
                "matched_clusters",
                "matched_ressorts",
                "matched_horizontals",
                "classification_matches",
            ]:
                if col not in existing_cols:
                    await conn.execute(text(f"ALTER TABLE bid ADD COLUMN {col} JSON"))
                    logger.info(f"SQLite migration: Added column {col} to bid")

            cols_res = await conn.execute(text("PRAGMA table_info(bid_checklist_item)"))
            existing_cols = {row[1] for row in cols_res.fetchall()}
            if "metadata_json" not in existing_cols:
                await conn.execute(text("ALTER TABLE bid_checklist_item ADD COLUMN metadata_json JSON"))
                logger.info("SQLite migration: Added column metadata_json to bid_checklist_item")
        else:
            for col, col_type in [
                ("short_summary", "NVARCHAR(MAX)"),
                ("link_original_doc", "NVARCHAR(1000)"),
                ("link_parsed_doc", "NVARCHAR(1000)"),
                ("quote_original", "NVARCHAR(MAX)"),
                ("is_mandatory", "BIT DEFAULT 1"),
                ("status", "NVARCHAR(20) DEFAULT 'open'"),
                ("user_override", "BIT DEFAULT 0"),
                ("uploaded_by", "NVARCHAR(255)"),
                ("uploaded_at", "DATETIMEOFFSET"),
                ("uploaded_filename", "NVARCHAR(500)"),
                ("extracted_metadata", "NVARCHAR(MAX)"),
            ]:
                check_sql = f"""
                IF COL_LENGTH('bid_required_document', '{col}') IS NULL
                BEGIN
                    ALTER TABLE bid_required_document ADD {col} {col_type} NULL
                END
                """
                await conn.execute(text(check_sql))

            check_sql_bid = """
            IF COL_LENGTH('bid', 'selection_criteria') IS NULL
            BEGIN
                ALTER TABLE bid ADD selection_criteria NVARCHAR(MAX) NULL
            END
            """
            await conn.execute(text(check_sql_bid))

            for col in [
                "matched_labels",
                "matched_sectors",
                "matched_services",
                "matched_people",
                "matched_campaigns",
                "matched_trends",
                "matched_practices",
                "matched_clusters",
                "matched_ressorts",
                "matched_horizontals",
                "classification_matches",
            ]:
                check_sql_col = f"""
                IF COL_LENGTH('bid', '{col}') IS NULL
                BEGIN
                    ALTER TABLE bid ADD {col} NVARCHAR(MAX) NULL
                END
                """
                await conn.execute(text(check_sql_col))

            check_sql_checklist = """
            IF COL_LENGTH('bid_checklist_item', 'metadata_json') IS NULL
            BEGIN
                ALTER TABLE bid_checklist_item ADD metadata_json NVARCHAR(MAX) NULL
            END
            """
            await conn.execute(text(check_sql_checklist))

        from core.schema_validator import verify_schema_integrity

        await conn.run_sync(verify_schema_integrity, Base)

    logger.info(f"🔌 Bidding DB ready at {_url.split('@')[-1]}")

    from services.portal_guide import seed_portal_guides

    await seed_portal_guides()


import logging

from sqlalchemy import event

db_logger = logging.getLogger("schema-validator")


@event.listens_for(engine.sync_engine, "handle_error")
def receive_handle_error(exception_context):
    if hasattr(exception_context, "original_exception") and hasattr(exception_context.original_exception, "args"):
        error_str = str(exception_context.original_exception)
        if "42S22" in error_str or "Invalid column name" in error_str or "no such column" in error_str:
            db_logger.error(
                f"🚨 DATABASE SCHEMA MISMATCH: A required column is missing in the database table! "
                f"The SQLAlchemy models were updated, but the corresponding migration was either not run "
                f"or failed to add the column. Details: {error_str}"
            )
