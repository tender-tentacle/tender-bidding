"""Append-only activity/audit log helper."""

from __future__ import annotations

from typing import Any

from models.bid import BidActivity
from sqlalchemy.ext.asyncio import AsyncSession


def record(db: AsyncSession, bid_id: str, actor: str | None, action: str, detail: dict[str, Any] | None = None) -> None:
    """Append an activity row (caller commits). Doubles as the GDPR audit trail."""
    db.add(BidActivity(bid_id=bid_id, actor_user_id=actor, action=action, detail=detail))
