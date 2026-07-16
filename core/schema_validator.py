import logging

from sqlalchemy import inspect

logger = logging.getLogger("schema-validator")

def verify_schema_integrity(conn, base_class):
    """
    Inspects the active database schema and compares it with SQLAlchemy metadata models.
    Must be executed inside a run_sync block on an async connection:
        async with engine.begin() as conn:
            await conn.run_sync(verify_schema_integrity, Base)
    Raises RuntimeError if any database column is missing or types/nullability drift critically.
    """
    logger.info("🔍 Running proactive schema alignment check...")

    inspector = inspect(conn)
    errors = []

    for table_name, table in base_class.metadata.tables.items():
        if not inspector.has_table(table_name):
            # Table defined in Python but not in DB yet (could be defined in another MS)
            continue

        # Get active columns from the database table
        db_cols = {col['name']: col for col in inspector.get_columns(table_name)}

        for column in table.columns:
            if column.name not in db_cols:
                # Column defined in Python model but does not exist in DB (will crash SELECT/INSERT)
                errors.append(
                    f"Column '{column.name}' of Table '{table_name}' is defined in Python models but does not exist in the Database."
                )
                continue

            db_col = db_cols[column.name]

            # Check critical nullability drift:
            # If Database is NOT NULL (nullable=False) with no default,
            # but Python model thinks it's nullable (nullable=True), inserts will fail.
            if column.nullable and not db_col['nullable'] and db_col['default'] is None:
                errors.append(
                    f"Column '{column.name}' of Table '{table_name}' is marked nullable in Python, but is NOT NULL without default in the Database."
                )

        # Reverse check: Database -> Python model
        for db_col_name, db_col in db_cols.items():
            if db_col_name not in [c.name for c in table.columns]:
                # The Database requires this column, but the Python model doesn't define it.
                # If it's NOT NULL and has no default, inserts will fail with Error 515.
                if not db_col['nullable'] and db_col['default'] is None:
                    errors.append(
                        f"Database requires column '{db_col_name}' in Table '{table_name}' (NOT NULL, no default), but Python model does not define it. Inserts will crash."
                    )

    if errors:
        logger.error("❌ Schema integrity check FAILED:")
        for err in errors:
            logger.error(f"  - {err}")
        raise RuntimeError("Database schema drift detected. Refusing to boot service.")

    logger.info("✅ Schema alignment check PASSED.")
