"""Decision matrix endpoints: expert upload, per-bid AI evaluation, human override.

Upload is an expert act (head of public sector): gated on the gateway-forwarded
X-User-Role (lead/admin), checked in-app. In mock mode the gate is open so the
service stays usable on test data without a gateway in front.
"""

from __future__ import annotations

from core.config import MOCK_MODE
from core.database import get_db
from core.portal_intel import get_portal_intel_client
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from models.bid import Bid
from schemas import CategoryIn, CategoryUpdateIn, MatrixUpdateIn, RatingOverrideIn
from services import activity
from services.decision_matrix import (
    add_category,
    create_matrix_from_upload,
    delete_category,
    evaluate_bid,
    get_active_matrix,
    get_evaluation,
    get_history,
    matrix_dict,
    override_rating,
    update_category,
    update_matrix,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["decision-matrix"])

_EXPERT_ROLES = {"lead", "admin"}


def _require_expert(request: Request) -> str | None:
    role = (request.headers.get("X-User-Role") or "").lower()
    if not MOCK_MODE and role not in _EXPERT_ROLES:
        raise HTTPException(status_code=403, detail=f"Editing the decision matrix requires one of {_EXPERT_ROLES}")
    return request.headers.get("X-User-ID")


async def _load_bid(db: AsyncSession, bid_id: str) -> Bid:
    bid = (await db.execute(select(Bid).where(Bid.id == bid_id))).scalar_one_or_none()
    if not bid:
        raise HTTPException(status_code=404, detail="Bid not found")
    return bid


async def _active_matrix_or_404(db: AsyncSession):
    matrix = await get_active_matrix(db)
    if not matrix:
        raise HTTPException(status_code=404, detail="No active decision matrix — upload one first.")
    return matrix


@router.post("/matrix", status_code=201)
async def upload_matrix(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload the company decision matrix; AI translates it into weighted categories."""
    actor = _require_expert(request)
    data = await file.read()
    markdown = data.decode("utf-8", errors="ignore")
    matrix = await create_matrix_from_upload(db, markdown=markdown, filename=file.filename, uploaded_by=actor)
    await db.commit()
    return matrix_dict(matrix)


@router.get("/matrix")
async def get_matrix(db: AsyncSession = Depends(get_db)):
    return matrix_dict(await _active_matrix_or_404(db))


# ── Expert backend (enriching-config style: versioned edits + history) ──────


@router.put("/matrix")
async def edit_matrix(body: MatrixUpdateIn, request: Request, db: AsyncSession = Depends(get_db)):
    """Update matrix settings (name, threshold). Every change is a new version."""
    actor = _require_expert(request)
    matrix = await _active_matrix_or_404(db)
    try:
        await update_matrix(
            db, matrix, name=body.name, threshold=body.threshold, change_summary=body.change_summary, actor=actor
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await db.commit()
    return matrix_dict(matrix)


@router.post("/matrix/categories", status_code=201)
async def create_category(body: CategoryIn, request: Request, db: AsyncSession = Depends(get_db)):
    actor = _require_expert(request)
    matrix = await _active_matrix_or_404(db)
    try:
        await add_category(
            db, matrix, headline=body.headline, explanation=body.explanation, weight=body.weight, actor=actor
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await db.commit()
    return matrix_dict(matrix)


@router.patch("/matrix/categories/{category_id}")
async def edit_category(category_id: str, body: CategoryUpdateIn, request: Request, db: AsyncSession = Depends(get_db)):
    actor = _require_expert(request)
    matrix = await _active_matrix_or_404(db)
    try:
        await update_category(
            db,
            matrix,
            category_id,
            headline=body.headline,
            explanation=body.explanation,
            weight=body.weight,
            actor=actor,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await db.commit()
    return matrix_dict(matrix)


@router.delete("/matrix/categories/{category_id}")
async def remove_category(category_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    actor = _require_expert(request)
    matrix = await _active_matrix_or_404(db)
    try:
        await delete_category(db, matrix, category_id, actor=actor)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    await db.commit()
    return matrix_dict(matrix)


@router.get("/matrix/history")
async def matrix_history(db: AsyncSession = Depends(get_db)):
    """Version history of the active matrix (who changed what, when)."""
    matrix = await _active_matrix_or_404(db)
    return await get_history(db, matrix)


@router.post("/bids/{bid_id}/matrix-evaluation")
async def run_evaluation(bid_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """AI-score every matrix category for this bid (overrides are preserved)."""
    bid = await _load_bid(db, bid_id)
    try:
        result = await evaluate_bid(db, bid)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    activity.record(
        db,
        bid.id,
        request.headers.get("X-User-ID"),
        "matrix.evaluated",
        {"total_points": result["total_points"], "threshold": result["threshold"], "verdict": result["verdict"]},
    )
    await db.commit()
    return result


@router.get("/bids/{bid_id}/matrix-evaluation")
async def read_evaluation(bid_id: str, db: AsyncSession = Depends(get_db)):
    bid = await _load_bid(db, bid_id)
    try:
        return await get_evaluation(db, bid)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.patch("/bids/{bid_id}/matrix-evaluation/{category_id}")
async def override_category(
    bid_id: str, category_id: str, body: RatingOverrideIn, request: Request, db: AsyncSession = Depends(get_db)
):
    """Human-in-the-loop override for one category (score=null clears the override)."""
    bid = await _load_bid(db, bid_id)
    try:
        rating = await override_rating(
            db, bid, category_id, score=body.score, note=body.note, actor=request.headers.get("X-User-ID")
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    activity.record(
        db,
        bid.id,
        request.headers.get("X-User-ID"),
        "matrix.overridden",
        {"category_id": category_id, "score": body.score, "note": body.note, "ai_score": rating.ai_score},
    )
    await db.commit()
    return await get_evaluation(db, bid)


@router.get("/bids/{bid_id}/market-intel")
async def market_intel(bid_id: str, db: AsyncSession = Depends(get_db)):
    """Competitor scan from public portals (TED/bund.de; mocked in v1)."""
    bid = await _load_bid(db, bid_id)
    return await get_portal_intel_client().competitor_scan(bid.customer, bid.cpv_codes)
