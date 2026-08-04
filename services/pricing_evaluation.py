"""Service to evaluate pricing quality and manage buyer intelligence cache."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from core.ai_client import get_ai_client
from models.bid import Bid
from models.buyer_cache import BuyerIntelligenceCacheORM
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def evaluate_pricing_strategy(db: AsyncSession, bid: Bid) -> dict[str, Any]:
    """
    Evaluates pricing strategy for a given bid.
    Checks the BuyerIntelligenceCacheORM first. If expired or missing,
    fetches historical data (currently mock/placeholder if no direct access),
    calls the AI, and caches the result.
    """
    buyer_name = bid.customer or "Unknown Buyer"
    buyer_name_clean = str(buyer_name).strip()

    # 1. Check cache
    now = datetime.now(UTC)
    cache_record = (
        await db.execute(
            select(BuyerIntelligenceCacheORM).where(BuyerIntelligenceCacheORM.customer_id == buyer_name_clean)
        )
    ).scalar_one_or_none()

    if cache_record and (now - cache_record.created_at.replace(tzinfo=UTC)) < timedelta(days=30):
        try:
            payload = json.loads(cache_record.intelligence_payload)
            if "strategy" in payload:
                return payload
        except json.JSONDecodeError:
            pass

    # 2. Gather context
    snapshot = {
        "buyer_name": buyer_name_clean,
        "current_value": f"€{bid.total_value:,}" if hasattr(bid, 'total_value') and bid.total_value else "Unknown",
        "current_ratio": "Unknown", # The actual tender data will be rendered by the frontend directly for the Current Tender block
    }

    # 3. Call AI to extract historical evidence (crawler)
    ai = get_ai_client()
    historical_data = await ai.extract_historical_evidence(buyer_name_clean)
    snapshot["historical_pricing_payload"] = historical_data

    # 4. Call AI to extract strategy
    result = await ai.extract_bidding_strategy(snapshot)

    # Inject the historic payload so the frontend can display it without hardcoding
    result["historical_data"] = historical_data

    # 4. Cache it
    if cache_record:
        cache_record.intelligence_payload = json.dumps(result)
        cache_record.created_at = now.replace(tzinfo=None)
    else:
        new_record = BuyerIntelligenceCacheORM(
            customer_id=buyer_name_clean,
            intelligence_payload=json.dumps(result),
            created_at=now.replace(tzinfo=None)
        )
        db.add(new_record)

    await db.commit()

    return result
