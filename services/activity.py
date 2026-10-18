"""Append-only activity/audit log helper."""

from __future__ import annotations

from typing import Any

from models.bid import BidActivity
from sqlalchemy.ext.asyncio import AsyncSession


def record(db: AsyncSession, bid_id: str, actor: str | None, action: str, detail: dict[str, Any] | None = None) -> None:
    """Append an immutable activity audit log row for a bid workspace.

    Creates and queues a new BidActivity entity in the active transaction, recording
    the acting user, high-level action verb (e.g. 'bid.created', 'bid.promoted'),
    and contextual payload. Serves as both business lifecycle history and GDPR audit log.

    Agent Metadata:
      @intent: Capture an immutable audit trail of all lifecycle events and mutations on bids.
      @domain: Bidding/Audit
      @capability: audit:record_activity
      @keywords: activity_log, audit_trail, gdpr, bid_lifecycle, tracking
      @side_effects: db:mutate (adds entity to session unit of work, uncommitted)
      @idempotent: false
      @agent_notes: Does not commit; caller is responsible for transaction boundaries.

    Contracts:
      @param db (AsyncSession): Active SQLAlchemy async session.
      @param bid_id (str): Primary key identifier of the target Bid.
      @param actor (str | None): User identifier of the actor, or None if system-initiated.
      @param action (str): Dotted lifecycle action token (e.g. 'bid.created', 'bid.archived').
      @param detail (dict[str, Any] | None): Optional JSON-serializable metadata dictionary.
      @return None: Appends to session state.
      @raises None: Pure object addition.

    Example:
      >>> record(db, bid.id, "user_123", "bid.promoted", {"from": "exploring", "to": "draft"})
    """
    db.add(BidActivity(bid_id=bid_id, actor_user_id=actor, action=action, detail=detail))
