"""Internal ACL endpoints: enriching pushes triage transitions.

- relay   → tender marked "interesting" (provisional=True → exploring workspace)
            or triaged "bid" (provisional=False → draft, promoting an exploring one)
- discard → tender triaged "no_bid" (archives ONLY an exploring workspace)
"""

from __future__ import annotations

from core.database import get_db
from fastapi import APIRouter, Depends, HTTPException
from schemas import BidRelayPayload, BidSummary, DiscardPayload
from services.bid_service import create_bid_from_snapshot, discard_by_source_ref
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/bids/relay", response_model=BidSummary)
async def relay_bid(payload: BidRelayPayload, db: AsyncSession = Depends(get_db)):
    """Idempotently create (or promote) a Bid workspace from an enriching snapshot."""
    bid, _created = await create_bid_from_snapshot(db, payload)
    return bid


@router.post("/bids/discard")
async def discard_bid(payload: DiscardPayload, db: AsyncSession = Depends(get_db)):
    """Archive the provisional workspace for a no-bid tender. Committed bids are untouched."""
    bid, archived = await discard_by_source_ref(db, payload.source_ref)
    if bid is None:
        raise HTTPException(status_code=404, detail=f"No bid for source_ref {payload.source_ref}")
    return {"bid_id": bid.id, "source_ref": bid.source_ref, "status": bid.status, "archived": archived}
