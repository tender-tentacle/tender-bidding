"""Bidding config API (enriching pattern): AI prompt templates per extraction
category, versioned with history. Expert-gated like the matrix endpoints."""

from __future__ import annotations

from core.config import MOCK_MODE
from core.database import get_db
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from services.prompt_config import DEFAULT_PROMPTS, get_history, get_prompt, update_prompt
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/config", tags=["configuration"])

_EXPERT_ROLES = {"lead", "admin"}


class PromptUpdate(BaseModel):
    prompt_template: str
    change_summary: str | None = None


def _require_expert(request: Request) -> str | None:
    role = (request.headers.get("X-User-Role") or "").lower()
    if not MOCK_MODE and role not in _EXPERT_ROLES:
        raise HTTPException(status_code=403, detail=f"Editing prompts requires one of {_EXPERT_ROLES}")
    return request.headers.get("X-User-ID")


@router.get("")
async def all_configs(db: AsyncSession = Depends(get_db)):
    return {cat: await get_prompt(db, cat) for cat in sorted(DEFAULT_PROMPTS)}


@router.get("/{category}")
async def one_config(category: str, db: AsyncSession = Depends(get_db)):
    try:
        return await get_prompt(db, category)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{category}")
async def edit_config(category: str, body: PromptUpdate, request: Request, db: AsyncSession = Depends(get_db)):
    actor = _require_expert(request)
    try:
        result = await update_prompt(
            db, category, prompt_template=body.prompt_template, change_summary=body.change_summary, actor=actor
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await db.commit()
    return result


@router.get("/{category}/history")
async def config_history(category: str, db: AsyncSession = Depends(get_db)):
    try:
        return await get_history(db, category)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
