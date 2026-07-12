"""Versioned AI-prompt configuration (mirrors the enriching config API).

The expert edits the extraction prompts here; RealAIClient syncs the *current*
template to the AI connector before each inference. Until an expert edits a
category, the hardcoded default from core.ai_client applies.
"""

from __future__ import annotations

from typing import Any

from core.ai_client import DEADLINES_PROMPT, REQUIRED_DOCUMENTS_PROMPT
from models.bid import PromptConfig, PromptConfigHistory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_PROMPTS: dict[str, str] = {
    "bidding_required_documents": REQUIRED_DOCUMENTS_PROMPT,
    "bidding_deadlines": DEADLINES_PROMPT,
}


async def get_prompt(db: AsyncSession, category: str) -> dict[str, Any]:
    if category not in DEFAULT_PROMPTS:
        raise LookupError(f"Unknown prompt category. Allowed: {sorted(DEFAULT_PROMPTS)}")
    row = (await db.execute(select(PromptConfig).where(PromptConfig.category == category))).scalar_one_or_none()
    if row:
        return {
            "category": category,
            "prompt_template": row.prompt_template,
            "version": row.version,
            "updated_at": row.updated_at,
            "is_default": False,
        }
    return {
        "category": category,
        "prompt_template": DEFAULT_PROMPTS[category].strip(),
        "version": 0,
        "updated_at": None,
        "is_default": True,
    }


async def current_template(db: AsyncSession, category: str) -> str:
    """The template the AI connector should receive (edited or default)."""
    return (await get_prompt(db, category))["prompt_template"]


async def update_prompt(
    db: AsyncSession, category: str, *, prompt_template: str, change_summary: str | None, actor: str | None
) -> dict[str, Any]:
    if category not in DEFAULT_PROMPTS:
        raise LookupError(f"Unknown prompt category. Allowed: {sorted(DEFAULT_PROMPTS)}")
    if not prompt_template.strip():
        raise ValueError("prompt_template cannot be empty")
    row = (await db.execute(select(PromptConfig).where(PromptConfig.category == category))).scalar_one_or_none()
    if row:
        row.prompt_template = prompt_template
        row.version += 1
    else:
        row = PromptConfig(category=category, prompt_template=prompt_template, version=1)
        db.add(row)
    db.add(
        PromptConfigHistory(
            category=category,
            version=row.version,
            prompt_template=prompt_template,
            change_summary=change_summary,
            created_by=actor,
        )
    )
    await db.flush()
    return await get_prompt(db, category)


async def get_history(db: AsyncSession, category: str, limit: int = 20) -> list[dict[str, Any]]:
    if category not in DEFAULT_PROMPTS:
        raise LookupError(f"Unknown prompt category. Allowed: {sorted(DEFAULT_PROMPTS)}")
    rows = (
        (
            await db.execute(
                select(PromptConfigHistory)
                .where(PromptConfigHistory.category == category)
                .order_by(PromptConfigHistory.version.desc())
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
            "prompt_template": h.prompt_template,
        }
        for h in rows
    ]
