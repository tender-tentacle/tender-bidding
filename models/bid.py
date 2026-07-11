"""Bid aggregate — the collaborative bid-workspace domain model.

One notice → one Bid, coordinated by a single `driver_user_id`. A Bid may be
split across lots (`lots_in_scope`); checklist items are bid-global or scoped to
a lot but always roll up to the one driver. Documents keep the original in Blob
and a markdown rendering + metadata here. Every mutation appends a BidActivity
row (audit / GDPR trail).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from core.database import Base
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


# Bid lifecycle
BID_STATUSES = ("draft", "in_progress", "submitted", "won", "lost", "withdrawn")
# Loss reasons feed the Win/Loss learning loop (2.7)
LOSS_REASONS = ("formal", "price", "quality", "reference_gap", "other")
# Checklist criterion kinds (2.3 / §3–4). "formal" items drive the pre-flight gate.
CRITERION_KINDS = ("formal", "suitability", "award")
CHECKLIST_STATUSES = ("open", "done", "n_a")
COLLABORATOR_ROLES = ("lead", "contributor", "reviewer")
DOCUMENT_KINDS = ("tender", "reference", "profile", "supporting")
# Sensitivity governs access/retention. "special" = GDPR special-category (court docs, CVs).
SENSITIVITIES = ("normal", "personal", "special")
KEYDATE_KINDS = ("submission", "questions", "validity")


class Bid(Base):
    __tablename__ = "bid"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    # Source in the enriching domain (tender external_id or group id) — idempotency key.
    source_ref: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    source_kind: Mapped[str] = mapped_column(String(20), default="tender")  # tender | group
    lots_in_scope: Mapped[list | None] = mapped_column(JSON, default=list)

    driver_user_id: Mapped[str | None] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(1000))
    customer: Mapped[str | None] = mapped_column(String(1000))
    portal_key: Mapped[str | None] = mapped_column(String(100))
    cluster: Mapped[str | None] = mapped_column(String(255))

    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    loss_reason: Mapped[str | None] = mapped_column(String(50))
    loss_note: Mapped[str | None] = mapped_column(Text)

    # Optimistic concurrency: writers send the version they read; mismatch → 409.
    version: Mapped[int] = mapped_column(Integer, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    collaborators: Mapped[list[BidCollaborator]] = relationship(
        back_populates="bid", cascade="all, delete-orphan", lazy="selectin"
    )
    checklist_items: Mapped[list[ChecklistItem]] = relationship(
        back_populates="bid", cascade="all, delete-orphan", lazy="selectin"
    )
    documents: Mapped[list[BidDocument]] = relationship(
        back_populates="bid", cascade="all, delete-orphan", lazy="selectin"
    )
    key_dates: Mapped[list[KeyDate]] = relationship(back_populates="bid", cascade="all, delete-orphan", lazy="selectin")


class BidCollaborator(Base):
    __tablename__ = "bid_collaborator"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    bid_id: Mapped[str] = mapped_column(ForeignKey("bid.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(20), default="contributor")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    bid: Mapped[Bid] = relationship(back_populates="collaborators")


class ChecklistItem(Base):
    __tablename__ = "bid_checklist_item"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    bid_id: Mapped[str] = mapped_column(ForeignKey("bid.id"), index=True)
    criterion_kind: Mapped[str] = mapped_column(String(20), index=True)  # formal|suitability|award
    requirement_type: Mapped[str] = mapped_column(String(50))  # reference|profile|signature|...
    title: Mapped[str] = mapped_column(String(1000))
    source_link: Mapped[str | None] = mapped_column(String(1000))  # where the requirement came from
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    ai_verification: Mapped[dict | None] = mapped_column(JSON)  # {status, detail}
    assignee_user_id: Mapped[str | None] = mapped_column(String(255), index=True)
    lot_scope: Mapped[str | None] = mapped_column(String(50))  # None = bid-global, else lot id
    order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    bid: Mapped[Bid] = relationship(back_populates="checklist_items")


class BidDocument(Base):
    __tablename__ = "bid_document"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    bid_id: Mapped[str] = mapped_column(ForeignKey("bid.id"), index=True)
    checklist_item_id: Mapped[str | None] = mapped_column(ForeignKey("bid_checklist_item.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="supporting")  # tender|reference|profile|supporting
    sensitivity: Mapped[str] = mapped_column(String(20), default="normal")  # normal|personal|special
    doc_type: Mapped[str | None] = mapped_column(String(100))
    filename: Mapped[str] = mapped_column(String(500))
    uploaded_by: Mapped[str | None] = mapped_column(String(255), index=True)
    blob_ref: Mapped[str] = mapped_column(String(500))  # original in Blob
    markdown: Mapped[str | None] = mapped_column(Text)  # rendering for AI consumption
    ai_verification: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    bid: Mapped[Bid] = relationship(back_populates="documents")


class KeyDate(Base):
    __tablename__ = "bid_key_date"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    bid_id: Mapped[str] = mapped_column(ForeignKey("bid.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # submission|questions|validity
    date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_link: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    bid: Mapped[Bid] = relationship(back_populates="key_dates")


class Comment(Base):
    __tablename__ = "bid_comment"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    bid_id: Mapped[str] = mapped_column(ForeignKey("bid.id"), index=True)
    target_type: Mapped[str] = mapped_column(String(20), default="bid")  # bid|checklist_item|document
    target_id: Mapped[str | None] = mapped_column(String(32), index=True)
    author_user_id: Mapped[str | None] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class BidActivity(Base):
    """Append-only activity/audit log (also the GDPR access trail)."""

    __tablename__ = "bid_activity"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    bid_id: Mapped[str] = mapped_column(ForeignKey("bid.id"), index=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(100))
    detail: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class PortalGuide(Base):
    """Curated static registration/submission guidance per portal (+ AI gap-fill)."""

    __tablename__ = "bid_portal_guide"

    portal_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    registration_steps: Mapped[list | None] = mapped_column(JSON, default=list)
    submission_channel: Mapped[str | None] = mapped_column(String(255))
    signature_level: Mapped[str | None] = mapped_column(String(50))  # textform|FES|QES
    notes: Mapped[str | None] = mapped_column(Text)
