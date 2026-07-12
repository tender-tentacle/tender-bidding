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
    MatchDecision,
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


@router.get("/{bid_id}/score")
async def get_score(bid_id: str, db: AsyncSession = Depends(get_db)):
    """Transparent readiness score: weighted criteria, each with its own detail line."""
    from services.scoring import compute_score

    return compute_score(await _load(db, bid_id))


@router.get("/{bid_id}/recommendation")
async def get_recommendation(bid_id: str, db: AsyncSession = Depends(get_db)):
    """Bid / no-bid / review advice with explicit reasons and reusable cross-bid evidence."""
    from services.scoring import recommend

    return await recommend(db, await _load(db, bid_id))


@router.post("/{bid_id}/match")
async def rematch_documents(bid_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Re-match uploads (own + cross-bid corpus) against open requirements."""
    from services.scoring import match_documents

    bid = await _load(db, bid_id)
    result = await match_documents(db, bid)
    activity.record(db, bid.id, _actor(request), "documents.matched", {"matches": len(result["matches"])})
    await db.commit()
    return result


@router.post("/{bid_id}/match/accept")
async def accept_match(bid_id: str, body: MatchDecision, request: Request, db: AsyncSession = Depends(get_db)):
    """Accept a proposed corpus match: link the evidence with full provenance.

    The item is NOT auto-completed — a human still adapts the document; the
    acceptance only records that trusted evidence exists and where it came from.
    """
    from models.bid import BidDocument
    from sqlalchemy import select as sa_select

    bid = await _load(db, bid_id)
    item = next((i for i in bid.checklist_items if i.id == body.checklist_item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Checklist item not found on this bid")
    doc = (await db.execute(sa_select(BidDocument).where(BidDocument.id == body.document_id))).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    from_corpus = doc.bid_id != bid.id
    item.ai_verification = {
        "status": "matched",
        "detail": f"Evidence accepted: {doc.filename}" + (" (cross-bid corpus)" if from_corpus else ""),
        "from_corpus": from_corpus,
        "source_bid_id": doc.bid_id,
        "source_document_id": doc.id,
        "accepted_by": _actor(request),
    }
    activity.record(
        db,
        bid.id,
        _actor(request),
        "match.accepted",
        {
            "checklist_item_id": item.id,
            "requirement": item.title,
            "document_id": doc.id,
            "filename": doc.filename,
            "source_bid_id": doc.bid_id,
            "from_corpus": from_corpus,
        },
    )
    await db.commit()
    return {"checklist_item_id": item.id, "ai_verification": item.ai_verification}


@router.post("/{bid_id}/match/reject")
async def reject_match(bid_id: str, body: MatchDecision, request: Request, db: AsyncSession = Depends(get_db)):
    """Reject a proposed match. The item is untouched; the why is kept as a learning signal."""
    bid = await _load(db, bid_id)
    item = next((i for i in bid.checklist_items if i.id == body.checklist_item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Checklist item not found on this bid")
    activity.record(
        db,
        bid.id,
        _actor(request),
        "match.rejected",
        {
            "checklist_item_id": item.id,
            "requirement": item.title,
            "document_id": body.document_id,
            "reason": body.reason,
        },
    )
    await db.commit()
    return {"checklist_item_id": item.id, "rejected_document_id": body.document_id}
