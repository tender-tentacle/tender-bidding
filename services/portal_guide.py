"""Curated static portal-registration/submission library (+ AI gap-fill).

Keyed by the enriching `source_system` / portal. Accurate and cheap; the AI
backend only fills gaps for portals not in this table.
"""

from __future__ import annotations

from core.database import SessionLocal
from core.logger import setup_logger
from models.bid import PortalGuide
from sqlalchemy import select

logger = setup_logger("bidding-portal-guide")

STATIC_GUIDES: list[dict] = [
    {
        "portal_key": "oeffentliche-vergabe",
        "name": "Öffentliche Vergabe (DÖE)",
        "registration_steps": [
            "Create a company account at oeffentlichevergabe.de",
            "Verify the organisation (Elster / company register)",
            "Add authorised submitters and their roles",
        ],
        "submission_channel": "Electronic via the portal (eForms).",
        "signature_level": "textform",
        "notes": "Textform (§126b BGB) is the default; name an authorised person in the declaration.",
    },
    {
        "portal_key": "ted-europe",
        "name": "TED Europe / eNotices2",
        "registration_steps": [
            "Register an EU Login account",
            "Link the economic operator profile",
        ],
        "submission_channel": "Follow the buyer's national eSubmission link on the notice.",
        "signature_level": "textform",
        "notes": "Above-threshold; ESPD/EEE self-declaration usually required.",
    },
    {
        "portal_key": "dtvp",
        "name": "Deutsches Vergabeportal (DTVP)",
        "registration_steps": [
            "Register a bidder account at dtvp.de",
            "Install/verify the bidder cockpit if required",
        ],
        "submission_channel": "Electronic via DTVP bidder cockpit.",
        "signature_level": "textform",
        "notes": "Check per-notice whether an advanced/qualified signature is demanded.",
    },
]


async def seed_portal_guides() -> None:
    """Idempotently upsert the static portal guides."""
    async with SessionLocal() as db:
        existing = set((await db.execute(select(PortalGuide.portal_key))).scalars().all())
        added = 0
        for g in STATIC_GUIDES:
            if g["portal_key"] not in existing:
                db.add(PortalGuide(**g))
                added += 1
        if added:
            await db.commit()
            logger.info(f"📚 Seeded {added} portal guides")


def portal_key_for(source_system: str | None) -> str | None:
    """Map an enriching source_system to a portal-guide key."""
    if not source_system:
        return None
    s = source_system.lower()
    if "öffentlich" in s or "oeffentlich" in s:
        return "oeffentliche-vergabe"
    if s.startswith("ted"):
        return "ted-europe"
    if "dtvp" in s:
        return "dtvp"
    return None
