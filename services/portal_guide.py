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
    """Idempotently seed curated static procurement portal guides into the database.

    Reads the predefined static portal guidance specifications (e.g. Öffentliche Vergabe,
    TED Europe, DTVP) and inserts any records whose portal_key does not already exist
    in the portal_guide database table.

    Agent Metadata:
      @intent: Pre-populate reference portal registration and submission guidelines at service startup.
      @domain: Bidding/PortalIntelligence
      @capability: db:seed_portal_guides
      @keywords: portal_guide, seed, registration_steps, signature_level, eforms, dtvp, ted
      @side_effects: db:mutate (inserts missing PortalGuide records and commits)
      @idempotent: true
      @agent_notes: Operates inside its own SessionLocal context. Safe to execute repeatedly.

    Contracts:
      @return None: Commits inserted rows directly.
      @raises SQLAlchemyError: If database connection or insert transaction encounters an error.

    Example:
      >>> await seed_portal_guides()
    """
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
    """Resolve a source system identifier string to a canonical portal guide key.

    Performs case-insensitive substring matching on the tender notice's source system
    string to identify standard procurement portals (Öffentliche Vergabe, TED, DTVP).

    Agent Metadata:
      @intent: Map varied external source system strings to canonical portal guide identifiers.
      @domain: Bidding/PortalIntelligence
      @capability: util:map_portal_key
      @keywords: source_system, portal_key, normalization, vergabe, ted, dtvp
      @side_effects: none (pure)
      @idempotent: true
      @agent_notes: Returns None if no known portal key matches the input string.

    Contracts:
      @param source_system (str | None): Raw source system name from tender crawler.
      @return (str | None): Normalized portal key or None if unrecognized.
      @raises None: Pure function.

    Example:
      >>> key = portal_key_for("TED eNotices2")
      >>> assert key == "ted-europe"
    """
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
