"""Decision-matrix service: upload→categories, expert backend (edit + versioned
history, enriching-config style), per-bid AI evaluation with human override, and
the weighted bid/no-bid verdict.

Verdict rule (as specified by the expert user): each category is scored 0–5,
carries a weight 1–5, and the tender is a BID when
Σ(effective_score × weight) ≥ threshold — where the effective score is the
human override when present, else the AI score. Every AI score keeps its
rationale; every override keeps who/why; every matrix change is a version with
a history snapshot. Each category carries a `headline` and the expert's prose
`explanation` — the explanation is what the AI grounds its scoring on.
"""

from __future__ import annotations

from typing import Any

from core.ai_client import get_ai_client
from core.portal_intel import get_portal_intel_client
from models.bid import (
    Bid,
    BidCategoryRating,
    DecisionCategory,
    DecisionMatrix,
    DecisionMatrixHistory,
)
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

SCORE_RANGE = range(0, 6)  # 0–5
WEIGHT_RANGE = range(1, 6)  # 1–5


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


def matrix_dict(matrix: DecisionMatrix) -> dict[str, Any]:
    return {
        "id": matrix.id,
        "name": matrix.name,
        "threshold": matrix.threshold,
        "version": matrix.version,
        "source_filename": matrix.source_filename,
        "uploaded_by": matrix.uploaded_by,
        "max_points": 5 * sum(c.weight for c in matrix.categories),
        "categories": [
            {"id": c.id, "headline": c.headline, "explanation": c.explanation, "weight": c.weight}
            for c in matrix.categories
        ],
    }


async def _snapshot(db: AsyncSession, matrix: DecisionMatrix, *, change_summary: str, created_by: str | None) -> None:
    """Version bump + history entry (same shape as the enriching config API)."""
    db.add(
        DecisionMatrixHistory(
            matrix_id=matrix.id,
            version=matrix.version,
            change_summary=change_summary,
            created_by=created_by,
            data=matrix_dict(matrix),
        )
    )
    matrix.version += 1


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
                headline=c["headline"],
                explanation=c.get("explanation"),
                weight=min(5, max(1, int(c.get("weight", 3)))),
                order=i,
            )
            for i, c in enumerate(extracted["categories"])
        ],
    )
    db.add(matrix)
    await db.flush()
    await _snapshot(db, matrix, change_summary=f"Uploaded from {filename or 'document'}", created_by=uploaded_by)
    await db.flush()
    return matrix


# ── Expert backend (edit + history) ─────────────────────────────────────────


async def update_matrix(
    db: AsyncSession,
    matrix: DecisionMatrix,
    *,
    name: str | None,
    threshold: int | None,
    change_summary: str | None,
    actor: str | None,
) -> DecisionMatrix:
    if threshold is not None:
        max_points = 5 * sum(c.weight for c in matrix.categories)
        if not 0 <= threshold <= max_points:
            raise ValueError(f"threshold must be between 0 and {max_points} (5 × Σ weights)")
        matrix.threshold = threshold
    if name:
        matrix.name = name[:255]
    await _snapshot(db, matrix, change_summary=change_summary or "Matrix settings updated", created_by=actor)
    await db.flush()
    return matrix


async def add_category(
    db: AsyncSession,
    matrix: DecisionMatrix,
    *,
    headline: str,
    explanation: str | None,
    weight: int,
    actor: str | None,
) -> DecisionCategory:
    if weight not in WEIGHT_RANGE:
        raise ValueError("weight must be between 1 and 5")
    if not headline.strip():
        raise ValueError("headline is required")
    cat = DecisionCategory(
        headline=headline.strip()[:255],
        explanation=(explanation or "").strip() or None,
        weight=weight,
        order=len(matrix.categories),
    )
    matrix.categories.append(cat)
    await _snapshot(db, matrix, change_summary=f"Added category '{cat.headline}'", created_by=actor)
    await db.flush()
    return cat


async def update_category(
    db: AsyncSession,
    matrix: DecisionMatrix,
    category_id: str,
    *,
    headline: str | None,
    explanation: str | None,
    weight: int | None,
    actor: str | None,
) -> DecisionCategory:
    cat = next((c for c in matrix.categories if c.id == category_id), None)
    if not cat:
        raise LookupError("Category not found on the active matrix")
    if weight is not None:
        if weight not in WEIGHT_RANGE:
            raise ValueError("weight must be between 1 and 5")
        cat.weight = weight
    if headline is not None:
        if not headline.strip():
            raise ValueError("headline cannot be empty")
        cat.headline = headline.strip()[:255]
    if explanation is not None:
        cat.explanation = explanation.strip() or None
    await _snapshot(db, matrix, change_summary=f"Updated category '{cat.headline}'", created_by=actor)
    await db.flush()
    return cat


async def delete_category(db: AsyncSession, matrix: DecisionMatrix, category_id: str, *, actor: str | None) -> None:
    cat = next((c for c in matrix.categories if c.id == category_id), None)
    if not cat:
        raise LookupError("Category not found on the active matrix")
    # Ratings of a removed criterion are meaningless — drop them with it.
    await db.execute(delete(BidCategoryRating).where(BidCategoryRating.category_id == category_id))
    headline = cat.headline
    matrix.categories.remove(cat)
    await _snapshot(db, matrix, change_summary=f"Removed category '{headline}'", created_by=actor)
    await db.flush()


async def get_history(db: AsyncSession, matrix: DecisionMatrix, limit: int = 20) -> list[dict[str, Any]]:
    rows = (
        (
            await db.execute(
                select(DecisionMatrixHistory)
                .where(DecisionMatrixHistory.matrix_id == matrix.id)
                .order_by(DecisionMatrixHistory.version.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "version": h.version,
            "change_summary": h.change_summary,
            "created_by": h.created_by,
            "created_at": h.created_at,
            "data": h.data,
        }
        for h in rows
    ]


# ── Per-bid evaluation ───────────────────────────────────────────────────────


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
            {"headline": cat.headline, "explanation": cat.explanation, "weight": cat.weight}, text, intel
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
                "headline": cat.headline,
                "explanation": cat.explanation,
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
        "matrix_version": matrix.version,
        "threshold": matrix.threshold,
        "max_points": max_points,
        "total_points": total if scored_any else None,
        "verdict": (("bid" if total >= matrix.threshold else "no_bid") if scored_any else None),
        "evaluated": scored_any,
        "categories": rows,
        "market_intel": intel,
    }
