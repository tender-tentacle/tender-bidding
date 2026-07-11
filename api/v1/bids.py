"""Bid workspace endpoints: list, detail, status, collaborators, regenerate,
deadlines, portal guide, activity."""

from __future__ import annotations

from datetime import UTC, datetime

from core.database import get_db
from fastapi import APIRouter, Depends, HTTPException, Request
from models.bid import (
    BID_STATUSES,
    LOSS_REASONS,
    Bid,
    BidActivity,
    BidCollaborator,
    KeyDate,
    PortalGuide,
)
from schemas import (
    ActivityOut,
    BidDetail,
    BidSummary,
    CollaboratorIn,
    CollaboratorOut,
    FormalGate,
    KeyDateOut,
    StatusUpdate,
)
from services import activity
from services.bid_service import snapshot_dict
from services.checklist_service import build_checklist, formal_gate, regenerate_checklist
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/bids", tags=["bids"])


async def _load(db: AsyncSession, bid_id: str) -> Bid:
    bid = (await db.execute(select(Bid).where(Bid.id == bid_id))).scalar_one_or_none()
    if not bid:
        raise HTTPException(status_code=404, detail="Bid not found")
    return bid


def _actor(request: Request) -> str | None:
    return request.headers.get("X-User-ID")


def _detail(bid: Bid) -> BidDetail:
    d = BidDetail.model_validate(bid)
    d.formal_gate = FormalGate(**formal_gate(bid))
    for kd in d.key_dates:
        kd.days_remaining = _days_remaining(kd.date)
    return d


def _days_remaining(dt: datetime | None) -> int | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return (dt - datetime.now(UTC)).days


@router.get("", response_model=list[BidSummary])
async def list_bids(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(Bid).order_by(Bid.updated_at.desc()))).scalars().all()


@router.get("/{bid_id}", response_model=BidDetail)
async def get_bid(bid_id: str, db: AsyncSession = Depends(get_db)):
    return _detail(await _load(db, bid_id))


@router.post("/{bid_id}/status", response_model=BidDetail)
async def update_status(bid_id: str, body: StatusUpdate, request: Request, db: AsyncSession = Depends(get_db)):
    bid = await _load(db, bid_id)
    if body.status not in BID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Allowed: {BID_STATUSES}")
    # Optimistic concurrency: reject a write based on a stale read.
    if body.expected_version != bid.version:
        raise HTTPException(
            status_code=409,
            detail=f"Version conflict: bid is at v{bid.version}, you sent v{body.expected_version}. Reload.",
        )
    if body.status == "lost":
        if body.loss_reason not in LOSS_REASONS:
            raise HTTPException(status_code=400, detail=f"loss_reason required for 'lost'. Allowed: {LOSS_REASONS}")
        bid.loss_reason = body.loss_reason
        bid.loss_note = body.loss_note

    old = bid.status
    bid.status = body.status
    bid.version += 1
    activity.record(db, bid.id, _actor(request), "bid.status_changed", {"from": old, "to": body.status})
    await db.commit()
    await db.refresh(bid)
    return _detail(bid)


@router.post("/{bid_id}/collaborators", response_model=CollaboratorOut, status_code=201)
async def add_collaborator(bid_id: str, body: CollaboratorIn, request: Request, db: AsyncSession = Depends(get_db)):
    bid = await _load(db, bid_id)
    collab = BidCollaborator(bid_id=bid.id, user_id=body.user_id, role=body.role)
    db.add(collab)
    activity.record(db, bid.id, _actor(request), "collaborator.added", {"user_id": body.user_id, "role": body.role})
    await db.commit()
    await db.refresh(collab)
    return collab


@router.post("/{bid_id}/regenerate", response_model=BidDetail)
async def regenerate(bid_id: str, payload: dict, request: Request, db: AsyncSession = Depends(get_db)):
    """Re-import an amended notice / Bieterfrage answer and additively diff the checklist."""
    bid = await _load(db, bid_id)
    snap = snapshot_dict(payload)
    snap.setdefault("source_ref", bid.source_ref)
    if not bid.checklist_items:
        bid.checklist_items = await build_checklist(snap)
        diff = {"added": len(bid.checklist_items), "kept": 0}
    else:
        diff = await regenerate_checklist(bid, snap)
    bid.version += 1
    activity.record(db, bid.id, _actor(request), "checklist.regenerated", diff)
    await db.commit()
    await db.refresh(bid)
    return _detail(bid)


@router.get("/{bid_id}/deadlines", response_model=list[KeyDateOut])
async def get_deadlines(bid_id: str, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(KeyDate).where(KeyDate.bid_id == bid_id))).scalars().all()
    out = []
    for kd in rows:
        o = KeyDateOut.model_validate(kd)
        o.days_remaining = _days_remaining(kd.date)
        out.append(o)
    return out


@router.get("/{bid_id}/portal-guide")
async def get_portal_guide(bid_id: str, db: AsyncSession = Depends(get_db)):
    bid = await _load(db, bid_id)
    if not bid.portal_key:
        return {"portal_key": None, "note": "No portal guide mapped for this source."}
    guide = (await db.execute(select(PortalGuide).where(PortalGuide.portal_key == bid.portal_key))).scalar_one_or_none()
    if not guide:
        return {"portal_key": bid.portal_key, "note": "Guide not found (AI gap-fill would apply)."}
    return {
        "portal_key": guide.portal_key,
        "name": guide.name,
        "registration_steps": guide.registration_steps,
        "submission_channel": guide.submission_channel,
        "signature_level": guide.signature_level,
        "notes": guide.notes,
    }


@router.get("/{bid_id}/activity", response_model=list[ActivityOut])
async def get_activity(bid_id: str, db: AsyncSession = Depends(get_db)):
    return (
        (
            await db.execute(
                select(BidActivity).where(BidActivity.bid_id == bid_id).order_by(BidActivity.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
