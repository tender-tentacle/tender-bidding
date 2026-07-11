"""Checklist item updates (check off, assign)."""

from __future__ import annotations

from core.database import get_db
from fastapi import APIRouter, Depends, HTTPException, Request
from models.bid import CHECKLIST_STATUSES, ChecklistItem
from schemas import ChecklistItemOut, ChecklistItemUpdate
from services import activity
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/bids", tags=["checklist"])


@router.patch("/{bid_id}/checklist/{item_id}", response_model=ChecklistItemOut)
async def update_item(
    bid_id: str, item_id: str, body: ChecklistItemUpdate, request: Request, db: AsyncSession = Depends(get_db)
):
    item = (
        await db.execute(select(ChecklistItem).where(ChecklistItem.id == item_id, ChecklistItem.bid_id == bid_id))
    ).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Checklist item not found")

    if body.status is not None:
        if body.status not in CHECKLIST_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status. Allowed: {CHECKLIST_STATUSES}")
        item.status = body.status
    if body.assignee_user_id is not None:
        item.assignee_user_id = body.assignee_user_id

    activity.record(
        db,
        bid_id,
        request.headers.get("X-User-ID"),
        "checklist.item_updated",
        {"item_id": item_id, "status": item.status, "assignee": item.assignee_user_id},
    )
    await db.commit()
    await db.refresh(item)
    return item
