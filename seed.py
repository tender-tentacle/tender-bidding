"""Seed the bidding DB with sample bids so the UI renders on test data.

Includes a WON historical bid with corpus documents so the Document Library
(US-101) demonstrates proven-asset reuse out of the box.

Run: BIDDING_MOCK=1 python seed.py
"""

import asyncio

from core.database import SessionLocal, init_db
from core.logger import setup_logger
from models.bid import BidDocument
from schemas import BidRelayPayload, LotSnapshot
from services.bid_service import create_bid_from_snapshot
from sqlalchemy import select

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
        cpv_codes=["72000000-5"],
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
        cpv_codes=["72200000-7"],
    ),
    BidRelayPayload(
        source_ref="SEED-dtvp-777",
        title="Managed Security Services",
        customer="Landesbehörde",
        source_system="DTVP",
        driver_user_id="anna",
        cluster="Public Sector",
        deadline_at="2099-07-30T12:00:00Z",
        cpv_codes=["72000000-5", "79710000-4"],
    ),
    # Provisional workspace: a tender merely marked "interesting" in enriching
    # (FEAT-051) — analysis runs, but no one has committed to bidding yet.
    BidRelayPayload(
        source_ref="SEED-exploring-042",
        title="Betrieb Fachverfahren Umweltamt (interessant markiert)",
        customer="Kreisverwaltung Beispielkreis",
        source_system="DTVP",
        deadline_at="2099-11-20T12:00:00Z",
        document_text="Betrieb und Weiterentwicklung eines Fachverfahrens. Referenzen erforderlich.",
        cpv_codes=["72000000-5"],
        provisional=True,
    ),
    # Historical WON bid: its documents seed the proven-asset corpus (US-101).
    BidRelayPayload(
        source_ref="SEED-won-2023-041",
        title="Cloud-Migration Landesverwaltung (gewonnen 2023)",
        customer="Landesverwaltung Musterland",
        source_system="Öffentliche Vergabe",
        driver_user_id="anna",
        cluster="Public Sector",
        cpv_codes=["72000000-5"],
        document_text="Cloud migration and managed operations. References and ISO certificates were decisive.",
    ),
]

CORPUS_DOCS = [
    # (source_ref, filename, markdown, kind, sensitivity)
    (
        "SEED-won-2023-041",
        "referenz-cloud-migration-2023.md",
        "Reference: cloud migration for a state administration, 40k users, "
        "managed operations 2021-2023. Comparable references for public sector cloud projects.",
        "reference",
        "normal",
    ),
    (
        "SEED-won-2023-041",
        "iso-27001-zertifikat.md",
        "ISO 27001 certificate, valid until 2027, covering cloud operations and security management.",
        "certificate",
        "normal",
    ),
    (
        "SEED-won-2023-041",
        "cv-projektleitung.md",
        "CV: senior project lead, 12 years public-sector cloud programmes.",
        "profile",
        "special",  # GDPR special category — visible to admins/uploader only
    ),
]


SEED_MATRIX_DOC = """# Public Sector Bid/No-Bid Matrix
- Strategic fit (weight 5): Fit with cluster strategy and target customers
- Comparable references (weight 4): References from the last 3 years for this service and sector
- Delivery capacity (weight 4): Team availability and required qualification profiles
- Competitive environment (weight 3): Incumbent advantage, number of likely competitors
- Profitability (weight 3): Expected margin and price pressure
- Formal & legal risk (weight 4): Contract terms, liability, missing certifications
threshold: 69
"""


async def main() -> None:
    await init_db()
    async with SessionLocal() as db:
        # Active decision matrix (idempotent: only when none exists yet).
        from services.decision_matrix import create_matrix_from_upload, get_active_matrix

        if not await get_active_matrix(db):
            matrix = await create_matrix_from_upload(
                db, markdown=SEED_MATRIX_DOC, filename="bid-no-bid-matrix.md", uploaded_by="anna"
            )
            logger.info(f"🧭 decision matrix: {matrix.name} ({len(matrix.categories)} categories, ≥{matrix.threshold})")

        bids_by_ref = {}
        for payload in SAMPLES:
            bid, created = await create_bid_from_snapshot(db, payload)
            bids_by_ref[bid.source_ref] = bid
            logger.info(f"{'✨ created' if created else '↔️ exists'}: {bid.title} ({bid.id})")

        # Mark the historical bid as won + attach its corpus documents (idempotent).
        won = bids_by_ref["SEED-won-2023-041"]
        if won.status != "won":
            won.status = "won"
        existing = {
            row.filename
            for row in (await db.execute(select(BidDocument).where(BidDocument.bid_id == won.id))).scalars()
        }
        for ref, filename, markdown, kind, sensitivity in CORPUS_DOCS:
            if filename in existing:
                continue
            db.add(
                BidDocument(
                    bid_id=bids_by_ref[ref].id,
                    kind=kind,
                    sensitivity=sensitivity,
                    filename=filename,
                    uploaded_by="anna",
                    blob_ref=f"seed://{filename}",
                    markdown=markdown,
                )
            )
            logger.info(f"📄 corpus doc: {filename} ({kind}/{sensitivity})")
        await db.commit()
    logger.info("✅ Seed complete")


if __name__ == "__main__":
    asyncio.run(main())
