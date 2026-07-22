from unittest.mock import patch

import pytest
from core.database import Base, engine, init_db
from sqlalchemy import text


@pytest.mark.asyncio
@patch("core.schema_validator.verify_schema_integrity")
async def test_init_db_adds_selection_criteria_column(mock_verify):
    """
    Test that if the bid table already exists but lacks the selection_criteria column,
    init_db() successfully adds it via the migration logic.
    """
    async with engine.begin() as conn:
        # 1. Ensure table doesn't exist (clean slate)
        await conn.run_sync(Base.metadata.drop_all)

        # 2. Create the bid table manually WITHOUT selection_criteria
        await conn.execute(
            text("""
            CREATE TABLE bid (
                id CHAR(36) PRIMARY KEY,
                title VARCHAR(255)
            )
        """)
        )

        # 3. Verify selection_criteria does NOT exist yet
        cols_res = await conn.execute(text("PRAGMA table_info(bid)"))
        existing_cols = {row[1] for row in cols_res.fetchall()}
        assert "selection_criteria" not in existing_cols

    # 4. Run the database initialization / migration logic
    await init_db()

    # 5. Verify the selection_criteria column was added
    async with engine.begin() as conn:
        cols_res = await conn.execute(text("PRAGMA table_info(bid)"))
        existing_cols = {row[1] for row in cols_res.fetchall()}
        assert "selection_criteria" in existing_cols

        # Verify it can be written to
        await conn.execute(
            text("INSERT INTO bid (id, title, selection_criteria) VALUES ('123', 'Test', '{\"foo\": \"bar\"}')")
        )
        res = await conn.execute(text("SELECT selection_criteria FROM bid WHERE id = '123'"))
        val = res.scalar_one()
        assert val == '{"foo": "bar"}'

        # Cleanup
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
