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

    Returns (bid, created) — created=False if it already existed.
    """
    snap = snapshot_dict(payload)
    existing = await get_by_source_ref(db, snap["source_ref"])
    if existing:
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
        status="draft",
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
        {"source_ref": bid.source_ref, "checklist_items": len(bid.checklist_items)},
    )
    await db.commit()
    logger.info(f"🎯 Created bid {bid.id} from {bid.source_ref} ({len(bid.checklist_items)} checklist items)")
    return bid, True
