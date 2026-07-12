"""Service KPIs for the expert backend (like the enriching admin dashboard)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from core.database import get_db
from fastapi import APIRouter, Depends
from models.bid import (
    Bid,
    BidActivity,
    BidCategoryRating,
    BidDocument,
    ChecklistItem,
    KeyDate,
    PromptConfig,
    RequiredDocument,
)
from services.decision_matrix import get_active_matrix
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/stats", tags=["stats"])


async def _count(db: AsyncSession, stmt) -> int:
    return int((await db.execute(stmt)).scalar() or 0)


@router.get("")
async def service_stats(db: AsyncSession = Depends(get_db)):
    """KPIs over the bidding DB: pipeline, detection output, deadlines, config state."""
    by_status_rows = (await db.execute(select(Bid.status, func.count()).group_by(Bid.status))).all()
    bids_by_status = {status: count for status, count in by_status_rows}

    now = datetime.now(UTC)
    soon = now + timedelta(days=14)
    due_soon = await _count(
        db, select(func.count()).select_from(KeyDate).where(KeyDate.date.isnot(None), KeyDate.date <= soon)
    )

    evaluated_bids = await _count(
        db, select(func.count(func.distinct(BidCategoryRating.bid_id))).select_from(BidCategoryRating)
    )
    overrides = await _count(
        db, select(func.count()).select_from(BidCategoryRating).where(BidCategoryRating.human_score.isnot(None))
    )

    matrix = await get_active_matrix(db)
    prompt_rows = (await db.execute(select(PromptConfig.category, PromptConfig.version))).all()

    return {
        "bids_total": sum(bids_by_status.values()),
        "bids_by_status": bids_by_status,
        "requirements_detected": await _count(db, select(func.count()).select_from(RequiredDocument)),
        "checklist_items_total": await _count(db, select(func.count()).select_from(ChecklistItem)),
        "checklist_items_open": await _count(
            db, select(func.count()).select_from(ChecklistItem).where(ChecklistItem.status == "open")
        ),
        "key_dates_total": await _count(db, select(func.count()).select_from(KeyDate)),
        "deadlines_due_14d": due_soon,
        "corpus_documents": await _count(db, select(func.count()).select_from(BidDocument)),
        "matrix_evaluated_bids": evaluated_bids,
        "human_overrides": overrides,
        "activity_events": await _count(db, select(func.count()).select_from(BidActivity)),
        "matrix": ({"name": matrix.name, "version": matrix.version, "threshold": matrix.threshold} if matrix else None),
        "prompt_versions": {category: version for category, version in prompt_rows},
    }
