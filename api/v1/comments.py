"""Comments on a bid, checklist item, or document."""

from __future__ import annotations

from core.database import get_db
from fastapi import APIRouter, Depends, HTTPException, Request
from models.bid import Bid, Comment
from schemas import CommentIn, CommentOut
from services import activity
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/bids", tags=["comments"])

_TARGETS = ("bid", "checklist_item", "document")


@router.post("/{bid_id}/comments", response_model=CommentOut, status_code=201)
async def add_comment(bid_id: str, body: CommentIn, request: Request, db: AsyncSession = Depends(get_db)):
    bid = (await db.execute(select(Bid).where(Bid.id == bid_id))).scalar_one_or_none()
    if not bid:
        raise HTTPException(status_code=404, detail="Bid not found")
    if body.target_type not in _TARGETS:
        raise HTTPException(status_code=400, detail=f"Invalid target_type. Allowed: {_TARGETS}")

    comment = Comment(
        bid_id=bid_id,
        target_type=body.target_type,
        target_id=body.target_id,
        author_user_id=request.headers.get("X-User-ID"),
        body=body.body,
    )
    db.add(comment)
    activity.record(db, bid_id, request.headers.get("X-User-ID"), "comment.added", {"target": body.target_type})
    await db.commit()
    await db.refresh(comment)
    return comment


@router.get("/{bid_id}/comments", response_model=list[CommentOut])
async def list_comments(bid_id: str, db: AsyncSession = Depends(get_db)):
    return (
        (await db.execute(select(Comment).where(Comment.bid_id == bid_id).order_by(Comment.created_at))).scalars().all()
    )
