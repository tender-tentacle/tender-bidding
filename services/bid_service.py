"""Bid creation from an enriching snapshot (idempotent)."""

from __future__ import annotations

from typing import Any

from core.logger import setup_logger
from models.bid import Bid, BidCollaborator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services import activity
from services.checklist_service import build_checklist, build_key_dates
from services.portal_guide import portal_key_for

logger = setup_logger("bidding-service")


def snapshot_dict(payload) -> dict[str, Any]:
    """Normalise a relay payload (pydantic or dict) into the AI snapshot shape."""
    d = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
    d.setdefault("lots", [])
    return d


async def get_by_source_ref(db: AsyncSession, source_ref: str) -> Bid | None:
    return (await db.execute(select(Bid).where(Bid.source_ref == source_ref))).scalar_one_or_none()


async def create_bid_from_snapshot(db: AsyncSession, payload) -> tuple[Bid, bool]:
    """Create a Bid + AI checklist + key dates. Idempotent on source_ref.

    A provisional snapshot (tender marked "interesting") creates the workspace
    in "exploring"; a committed one (triage = "bid") creates it in "draft" — or
    promotes an existing exploring workspace, keeping all analysis.

    Returns (bid, created) — created=False if it already existed.
    """
    snap = snapshot_dict(payload)
    provisional = bool(snap.get("provisional"))
    existing = await get_by_source_ref(db, snap["source_ref"])
    if existing:
        if existing.status == "exploring" and not provisional:
            await _promote(db, existing, snap)
        return existing, False

    bid = Bid(
        source_ref=snap["source_ref"],
        source_kind=snap.get("source_kind", "tender"),
        title=snap.get("title") or "Untitled bid",
        customer=snap.get("customer"),
        cluster=snap.get("cluster"),
        driver_user_id=snap.get("driver_user_id"),
        portal_key=portal_key_for(snap.get("source_system")),
        lots_in_scope=[lot.get("lot_id") or lot.get("lot_number") for lot in snap.get("lots", [])],
        cpv_codes=snap.get("cpv_codes") or [],
        selection_criteria=snap.get("selection_criteria"),
        status="exploring" if provisional else "draft",
    )
    bid.checklist_items = await build_checklist(snap)
    bid.key_dates = await build_key_dates(snap)
    if snap.get("driver_user_id"):
        bid.collaborators = [BidCollaborator(user_id=snap["driver_user_id"], role="lead")]

    db.add(bid)
    await db.flush()
    activity.record(
        db,
        bid.id,
        snap.get("driver_user_id"),
        "bid.created",
        {"source_ref": bid.source_ref, "checklist_items": len(bid.checklist_items), "provisional": provisional},
    )
    await db.commit()
    logger.info(
        f"🎯 Created {'provisional ' if provisional else ''}bid {bid.id} from {bid.source_ref} "
        f"({len(bid.checklist_items)} checklist items)"
    )
    return bid, True


async def _promote(db: AsyncSession, bid: Bid, snap: dict[str, Any]) -> None:
    """Exploring → draft: the tender was triaged as a real bid. Analysis is kept."""
    bid.status = "draft"
    bid.version += 1
    driver = snap.get("driver_user_id")
    if driver and not bid.driver_user_id:
        bid.driver_user_id = driver
        if driver not in {c.user_id for c in bid.collaborators}:
            bid.collaborators.append(BidCollaborator(user_id=driver, role="lead"))
    activity.record(db, bid.id, driver, "bid.promoted", {"from": "exploring", "to": "draft"})
    await db.commit()
    logger.info(f"⬆️ Promoted exploring bid {bid.id} ({bid.source_ref}) to draft")


async def discard_by_source_ref(db: AsyncSession, source_ref: str, actor: str | None = None) -> tuple[Bid | None, bool]:
    """No-bid triage: archive the workspace, but ONLY a provisional (exploring) one.

    Committed bids are never touched by an upstream triage flip — withdrawing a
    real bid is a human act in this service. Returns (bid, archived).
    """
    bid = await get_by_source_ref(db, source_ref)
    if not bid:
        return None, False
    if bid.status != "exploring":
        return bid, False
    bid.status = "withdrawn"
    bid.version += 1
    activity.record(db, bid.id, actor, "bid.archived", {"reason": "triage_no_bid", "from": "exploring"})
    await db.commit()
    logger.info(f"🗄️ Archived exploring bid {bid.id} ({source_ref}) after no-bid triage")
    return bid, True
