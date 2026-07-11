"""Seed the bidding DB with sample bids so the UI renders on test data.

Run: BIDDING_MOCK=1 python seed.py
"""

import asyncio

from core.database import SessionLocal, init_db
from core.logger import setup_logger
from schemas import BidRelayPayload, LotSnapshot
from services.bid_service import create_bid_from_snapshot

logger = setup_logger("bidding-seed")

SAMPLES = [
    BidRelayPayload(
        source_ref="SEED-oeff-9d849f29",
        title="Rahmenvertrag IT-Beratung und Cloud-Betrieb",
        customer="Stadt Musterstadt",
        source_system="Öffentliche Vergabe",
        driver_user_id="anna",
        cluster="Public Sector",
        deadline_at="2099-09-01T12:00:00Z",
        questions_deadline_at="2099-08-15T12:00:00Z",
        document_text="Bau und Betrieb einer Cloud-Plattform. Bietergemeinschaft möglich. Referenzen erforderlich.",
        lots=[
            LotSnapshot(lot_id="LOT-0001", lot_number=1, title="Los 1 — Netzwerk", document_text="Netzwerkbetrieb"),
            LotSnapshot(lot_id="LOT-0002", lot_number=2, title="Los 2 — Storage", document_text="Speicherdienste"),
        ],
    ),
    BidRelayPayload(
        source_ref="SEED-ted-000123",
        title="Framework for Software Development Services",
        customer="EU Agency",
        source_system="TED Europe",
        driver_user_id="ben",
        cluster="EU",
        deadline_at="2099-10-15T17:00:00Z",
        document_text="Agile software development, ESPD required.",
    ),
    BidRelayPayload(
        source_ref="SEED-dtvp-777",
        title="Managed Security Services",
        customer="Landesbehörde",
        source_system="DTVP",
        driver_user_id="anna",
        cluster="Public Sector",
        deadline_at="2099-07-30T12:00:00Z",
    ),
]


async def main() -> None:
    await init_db()
    async with SessionLocal() as db:
        for payload in SAMPLES:
            bid, created = await create_bid_from_snapshot(db, payload)
            logger.info(f"{'✨ created' if created else '↔️ exists'}: {bid.title} ({bid.id})")
    logger.info("✅ Seed complete")


if __name__ == "__main__":
    asyncio.run(main())
