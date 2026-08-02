import logging

from sqlalchemy import inspect, text
from sqlalchemy.sql.sqltypes import NVARCHAR, VARCHAR, String, Unicode

logger = logging.getLogger("schema-validator")


def sync_and_verify_schema_integrity(conn, base_class):
    """
    Auto-synchronizes active DB schema with SQLAlchemy metadata models and verifies alignment.
    1. Ensures all tables exist via Base.metadata.create_all.
    2. Auto-adds any missing columns defined in ORM models.
    3. Auto-expands string column widths if ORM model requires a larger length (e.g. VARCHAR(255) -> VARCHAR(1000)).
    4. Validates final schema integrity.
    """
    logger.info("🔍 Running proactive schema auto-synchronization & verification...")

    # Force registration of all model tables
    base_class.metadata.create_all(conn)

    inspector = inspect(conn)
    dialect_name = conn.dialect.name.lower()
    is_mssql = "mssql" in dialect_name or "pyodbc" in dialect_name or "aioodbc" in dialect_name

    for table_name, table in base_class.metadata.tables.items():
        if not inspector.has_table(table_name):
            continue

        db_cols = {col["name"]: col for col in inspector.get_columns(table_name)}

        for column in table.columns:
            col_name = column.name

            # 1. Auto-add missing column
            if col_name not in db_cols:
                col_type_sql = _get_sql_type(column.type, is_mssql)
                nullable_sql = "" if column.nullable else " NOT NULL"

                if is_mssql:
                    alter_sql = f"ALTER TABLE [{table_name}] ADD [{col_name}] {col_type_sql}{nullable_sql}"
                else:
                    alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type_sql}{nullable_sql}"

                try:
                    conn.execute(text(alter_sql))
                    logger.info(f"➕ Auto-added missing column '{col_name}' ({col_type_sql}) to table '{table_name}'.")
                    db_cols[col_name] = {
                        "name": col_name,
                        "nullable": column.nullable,
                        "length": getattr(column.type, "length", None),
                    }
                except Exception as e:
                    logger.warning(f"Could not auto-add column '{col_name}' to '{table_name}': {e}")
                continue

            # 2. Auto-expand column length if ORM definition requires wider VARCHAR/NVARCHAR
            if is_mssql and isinstance(column.type, (String, NVARCHAR, VARCHAR, Unicode)):
                target_len = getattr(column.type, "length", None)
                db_col = db_cols[col_name]
                db_len = db_col.get("length")

                needs_expansion = False
                if target_len is None or target_len == -1:
                    # Unlimited / MAX in SQLAlchemy
                    if db_len is not None and db_len != -1 and db_len < 4000:
                        needs_expansion = True
                        new_type_sql = "NVARCHAR(MAX)"
                elif isinstance(target_len, int) and db_len is not None and db_len != -1 and target_len > db_len:
                    needs_expansion = True
                    new_type_sql = f"VARCHAR({target_len})"

                if needs_expansion:
                    try:
                        conn.execute(text(f"ALTER TABLE [{table_name}] ALTER COLUMN [{col_name}] {new_type_sql}"))
                        logger.info(
                            f"⚡ Auto-expanded column '{col_name}' in table '{table_name}' from len {db_len} to {new_type_sql}."
                        )
                    except Exception as e:
                        logger.warning(f"Could not auto-expand column '{col_name}' in '{table_name}': {e}")

    # Re-inspect to perform final verification pass
    inspector = inspect(conn)
    errors = []
    for table_name, table in base_class.metadata.tables.items():
        if not inspector.has_table(table_name):
            errors.append(f"Table '{table_name}' defined in Python model is missing in DB.")
            continue

        db_cols = {col["name"]: col for col in inspector.get_columns(table_name)}
        for column in table.columns:
            if column.name not in db_cols:
                errors.append(f"Column '{column.name}' of Table '{table_name}' is missing in Database.")

    if errors:
        logger.error("❌ Schema integrity check FAILED after auto-sync:")
        for err in errors:
            logger.error(f"  - {err}")
        raise RuntimeError(f"Database schema drift detected ({len(errors)} errors). Refusing to boot service.")

    logger.info("✅ Schema alignment & synchronization PASSED.")


def verify_schema_integrity(conn, base_class):
    """Legacy alias for backward compatibility."""
    sync_and_verify_schema_integrity(conn, base_class)


def _get_sql_type(col_type, is_mssql: bool) -> str:
    """Helper to derive SQL column type string from SQLAlchemy type."""
    type_str = str(col_type).upper()
    if isinstance(col_type, (String, VARCHAR, NVARCHAR, Unicode)):
        length = getattr(col_type, "length", None)
        if length is None or length == -1:
            return "NVARCHAR(MAX)" if is_mssql else "TEXT"
        return f"VARCHAR({length})"
    if "BOOLEAN" in type_str or "BIT" in type_str:
        return "BIT" if is_mssql else "BOOLEAN"
    if "DATETIME" in type_str:
        return "DATETIMEOFFSET" if is_mssql else "DATETIME"
    if "FLOAT" in type_str:
        return "FLOAT"
    if "INT" in type_str:
        return "INT"
    if "JSON" in type_str:
        return "NVARCHAR(MAX)" if is_mssql else "JSON"
    return "VARCHAR(255)"
