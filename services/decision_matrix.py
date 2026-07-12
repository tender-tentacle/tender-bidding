"""Decision-matrix service: upload→categories, per-bid AI evaluation with human
override, and the weighted bid/no-bid verdict.

Verdict rule (as specified by the expert user): each category is scored 0–5,
carries a weight 1–5, and the tender is a BID when
Σ(effective_score × weight) ≥ threshold — where the effective score is the
human override when present, else the AI score. Every AI score keeps its
rationale; every override keeps who/why. The evaluation is the strategic layer
on top of the operational readiness score.
"""

from __future__ import annotations

from typing import Any

from core.ai_client import get_ai_client
from core.portal_intel import get_portal_intel_client
from models.bid import Bid, BidCategoryRating, DecisionCategory, DecisionMatrix
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

SCORE_RANGE = range(0, 6)  # 0–5


async def get_active_matrix(db: AsyncSession) -> DecisionMatrix | None:
    return (
        (
            await db.execute(
                select(DecisionMatrix).where(DecisionMatrix.active).order_by(DecisionMatrix.created_at.desc())
            )
        )
        .scalars()
        .first()
    )


async def create_matrix_from_upload(
    db: AsyncSession, *, markdown: str, filename: str | None, uploaded_by: str | None
) -> DecisionMatrix:
    """AI-translate the uploaded document into a matrix; deactivate the previous one."""
    extracted = await get_ai_client().extract_decision_matrix(markdown)

    for old in (await db.execute(select(DecisionMatrix).where(DecisionMatrix.active))).scalars():
        old.active = False

    matrix = DecisionMatrix(
        name=extracted["name"],
        source_filename=filename,
        uploaded_by=uploaded_by,
        threshold=extracted["threshold"],
        active=True,
        categories=[
            DecisionCategory(
                name=c["name"],
                description=c.get("description"),
                weight=min(5, max(1, int(c.get("weight", 3)))),
                order=i,
            )
            for i, c in enumerate(extracted["categories"])
        ],
    )
    db.add(matrix)
    await db.flush()
    return matrix


def _bid_text(bid: Bid) -> str:
    """Everything we hold about the bid, as the AI's evidence corpus."""
    parts = [bid.title, bid.customer or ""]
    parts += [i.title for i in bid.checklist_items]
    parts += [f"{d.filename} {d.markdown or ''}" for d in bid.documents]
    return "\n".join(parts)


async def evaluate_bid(db: AsyncSession, bid: Bid) -> dict[str, Any]:
    """AI-score every category of the active matrix for this bid (upsert).

    Human overrides are never touched by a re-evaluation — the AI only refreshes
    its own proposal and rationale.
    """
    matrix = await get_active_matrix(db)
    if not matrix:
        raise LookupError("No active decision matrix — upload one first.")

    intel = await get_portal_intel_client().competitor_scan(bid.customer, bid.cpv_codes)
    text = _bid_text(bid)

    existing = {
        r.category_id: r
        for r in (await db.execute(select(BidCategoryRating).where(BidCategoryRating.bid_id == bid.id))).scalars()
    }
    ai = get_ai_client()
    for cat in matrix.categories:
        result = await ai.score_category(
            {"name": cat.name, "description": cat.description, "weight": cat.weight}, text, intel
        )
        rating = existing.get(cat.id)
        if rating:
            rating.ai_score = result["score"]
            rating.ai_rationale = result["rationale"]
        else:
            db.add(
                BidCategoryRating(
                    bid_id=bid.id, category_id=cat.id, ai_score=result["score"], ai_rationale=result["rationale"]
                )
            )
    await db.flush()
    return await get_evaluation(db, bid, intel=intel)


async def override_rating(
    db: AsyncSession, bid: Bid, category_id: str, *, score: int | None, note: str | None, actor: str | None
) -> BidCategoryRating:
    """Human-in-the-loop: set (or clear with score=None) the override for one category."""
    if score is not None and score not in SCORE_RANGE:
        raise ValueError("score must be between 0 and 5")
    rating = (
        await db.execute(
            select(BidCategoryRating).where(
                BidCategoryRating.bid_id == bid.id, BidCategoryRating.category_id == category_id
            )
        )
    ).scalar_one_or_none()
    if not rating:
        rating = BidCategoryRating(bid_id=bid.id, category_id=category_id)
        db.add(rating)
    rating.human_score = score
    rating.human_note = note
    rating.overridden_by = actor if score is not None else None
    await db.flush()
    return rating


async def get_evaluation(db: AsyncSession, bid: Bid, intel: dict[str, Any] | None = None) -> dict[str, Any]:
    """The full evaluation: per-category rows + weighted total vs threshold → verdict."""
    matrix = await get_active_matrix(db)
    if not matrix:
        raise LookupError("No active decision matrix — upload one first.")

    ratings = {
        r.category_id: r
        for r in (await db.execute(select(BidCategoryRating).where(BidCategoryRating.bid_id == bid.id))).scalars()
    }

    rows: list[dict[str, Any]] = []
    total = 0
    scored_any = False
    for cat in matrix.categories:
        r = ratings.get(cat.id)
        effective = r.human_score if r and r.human_score is not None else (r.ai_score if r else None)
        if effective is not None:
            scored_any = True
            total += effective * cat.weight
        rows.append(
            {
                "category_id": cat.id,
                "name": cat.name,
                "description": cat.description,
                "weight": cat.weight,
                "ai_score": r.ai_score if r else None,
                "ai_rationale": r.ai_rationale if r else None,
                "human_score": r.human_score if r else None,
                "human_note": r.human_note if r else None,
                "overridden_by": r.overridden_by if r else None,
                "effective_score": effective,
                "weighted_points": (effective * cat.weight) if effective is not None else None,
            }
        )

    max_points = 5 * sum(c.weight for c in matrix.categories)
    return {
        "matrix_id": matrix.id,
        "matrix_name": matrix.name,
        "threshold": matrix.threshold,
        "max_points": max_points,
        "total_points": total if scored_any else None,
        "verdict": (("bid" if total >= matrix.threshold else "no_bid") if scored_any else None),
        "evaluated": scored_any,
        "categories": rows,
        "market_intel": intel,
    }
