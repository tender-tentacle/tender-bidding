"""Internal ACL endpoint: enriching pushes a snapshot when a tender becomes a bid."""

from __future__ import annotations

from core.database import get_db
from fastapi import APIRouter, Depends
from schemas import BidRelayPayload, BidSummary
from services.bid_service import create_bid_from_snapshot
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/bids/relay", response_model=BidSummary)
async def relay_bid(payload: BidRelayPayload, db: AsyncSession = Depends(get_db)):
    """Idempotently create a Bid workspace from an enriching snapshot."""
    bid, _created = await create_bid_from_snapshot(db, payload)
    return bid
