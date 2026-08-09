import asyncio

from core.database import SessionLocal
from sqlalchemy import text


async def main():
    tables_to_wipe = [
        "bid_activity",
        "bid_category_rating",
        "comment",
        "required_document",
        "key_date",
        "bid_document",
        "checklist_item",
        "bid_collaborator",
        "decision_matrix_history",
        "prompt_config_history",
        "decision_category",
        "decision_matrix",
        "bid",
        "company_mood",
        "company_register_entry",
        "company_job_entry",
        "company_news_entry",
        "company_historic_tender",
        "company_insolvency",
        "company_reputation_cache",
        "buyer_intelligence_cache",
    ]
    async with SessionLocal() as db:
        try:
            await db.execute(text("EXEC sp_MSforeachtable 'ALTER TABLE ? NOCHECK CONSTRAINT all'"))
        except Exception:
            pass

        for table in tables_to_wipe:
            try:
                await db.execute(text(f"DELETE FROM {table}"))
                print(f"Wiped {table}")
            except Exception as e:
                print(f"Note on {table}: {e}")

        try:
            await db.execute(text("EXEC sp_MSforeachtable 'ALTER TABLE ? WITH CHECK CHECK CONSTRAINT all'"))
        except Exception:
            pass
        await db.commit()
    print("Bidding database safely wiped!")


if __name__ == "__main__":
    asyncio.run(main())
