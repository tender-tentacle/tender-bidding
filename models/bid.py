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
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


# Bid lifecycle. "exploring" = provisional workspace created when a tender is
# merely marked *interesting* in enriching (FEAT-051): analysis runs, but the
# bid is not committed until triage says "bid" (→ promoted to "draft").
BID_STATUSES = ("exploring", "draft", "in_progress", "submitted", "won", "lost", "withdrawn")
# Loss reasons feed the Win/Loss learning loop (2.7)
LOSS_REASONS = ("formal", "price", "quality", "reference_gap", "other")
# Checklist criterion kinds (2.3 / §3–4). "formal" items drive the pre-flight gate.
CRITERION_KINDS = ("formal", "suitability", "award")
CHECKLIST_STATUSES = ("open", "done", "n_a")
COLLABORATOR_ROLES = ("lead", "contributor", "reviewer")
DOCUMENT_KINDS = ("tender", "reference", "profile", "certificate", "declaration", "supporting")
# Sensitivity governs access/retention. "special" = GDPR special-category (court docs, CVs).
SENSITIVITIES = ("normal", "personal", "special")
KEYDATE_KINDS = ("submission", "questions", "validity", "registration", "application")


class Bid(Base):
    __tablename__ = "bid"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    # Source in the enriching domain (tender external_id or group id) — idempotency key.
    source_ref: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    source_kind: Mapped[str] = mapped_column(String(20), default="tender")  # tender | group
    # Enriching-domain UUID (tender/group id). source_ref stays the idempotency
    # key (external_id); this lets the dashboard look bids up by either.
    enriching_id: Mapped[str | None] = mapped_column(String(64), index=True)
    lots_in_scope: Mapped[list | None] = mapped_column(JSON, default=list)
    cpv_codes: Mapped[list | None] = mapped_column(JSON, default=list)  # from the tender snapshot
    selection_criteria: Mapped[dict | None] = mapped_column(JSON)

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
    required_documents: Mapped[list[RequiredDocument]] = relationship(
        back_populates="bid", cascade="all, delete-orphan", lazy="selectin"
    )


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
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # ESPD 4C extracted criteria
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


class RequiredDocument(Base):
    __tablename__ = "bid_required_document"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    bid_id: Mapped[str] = mapped_column(ForeignKey("bid.id"), index=True)
    document_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(100))  # suitability | self-declaration | proposal | consortium
    short_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    link_original_doc: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    link_parsed_doc: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    quote_original: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=True)
    extracted_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    status: Mapped[str] = mapped_column(String(20), default="open")  # open | done | needs_review | gap
    user_override: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    uploaded_filename: Mapped[str | None] = mapped_column(String(500), nullable=True)

    bid: Mapped[Bid] = relationship(back_populates="required_documents")


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


class DecisionMatrix(Base):
    """Company bid/no-bid decision matrix (FEAT: strategic decision support).

    Uploaded by the expert (head of public sector); AI translates the document
    into weighted categories. One matrix is active at a time — evaluations
    always run against the active matrix.
    """

    __tablename__ = "bid_decision_matrix"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    source_filename: Mapped[str | None] = mapped_column(String(500))
    uploaded_by: Mapped[str | None] = mapped_column(String(255))
    # Verdict rule: Σ(effective_score × weight) ≥ threshold → bid, else no_bid.
    threshold: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # Expert-backend versioning (same pattern as the enriching config API).
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    categories: Mapped[list[DecisionCategory]] = relationship(
        back_populates="matrix", cascade="all, delete-orphan", lazy="selectin", order_by="DecisionCategory.order"
    )


class DecisionCategory(Base):
    """One decision criterion ("sub step") of the matrix. Weight 1–5.

    `headline` is the short criterion label; `explanation` is the expert's
    full intent in prose — the AI grounds its 0–5 scoring on both, so a richer
    explanation directly improves the evaluation.
    """

    __tablename__ = "bid_decision_category"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    matrix_id: Mapped[str] = mapped_column(ForeignKey("bid_decision_matrix.id"), index=True)
    headline: Mapped[str] = mapped_column(String(255))
    explanation: Mapped[str | None] = mapped_column(Text)
    weight: Mapped[int] = mapped_column(Integer, default=3)  # 1–5
    order: Mapped[int] = mapped_column(Integer, default=0)

    matrix: Mapped[DecisionMatrix] = relationship(back_populates="categories")


class PromptConfig(Base):
    """Editable AI prompt per extraction category (enriching-config pattern).

    Categories: bidding_required_documents | bidding_deadlines. The RealAIClient
    syncs the current template to the AI connector before each inference; the
    hardcoded defaults apply until an expert edits them.
    """

    __tablename__ = "bid_prompt_config"

    category: Mapped[str] = mapped_column(String(100), primary_key=True)
    prompt_template: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class PromptConfigHistory(Base):
    __tablename__ = "bid_prompt_config_history"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    category: Mapped[str] = mapped_column(String(100), index=True)
    version: Mapped[int] = mapped_column(Integer)
    prompt_template: Mapped[str] = mapped_column(Text)
    change_summary: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class DecisionMatrixHistory(Base):
    """Version snapshots of the matrix (enriching-config-style history)."""

    __tablename__ = "bid_decision_matrix_history"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    matrix_id: Mapped[str] = mapped_column(ForeignKey("bid_decision_matrix.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    change_summary: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[str | None] = mapped_column(String(255))
    data: Mapped[dict | None] = mapped_column(JSON)  # full matrix snapshot at that version
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class BidCategoryRating(Base):
    """Per-bid rating of one decision category. Scores 0–5.

    The AI proposes (score + rationale, incl. portal intelligence); the human in
    the loop may override — the override always wins in the verdict.
    """

    __tablename__ = "bid_category_rating"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    bid_id: Mapped[str] = mapped_column(ForeignKey("bid.id"), index=True)
    category_id: Mapped[str] = mapped_column(ForeignKey("bid_decision_category.id"), index=True)
    ai_score: Mapped[int | None] = mapped_column(Integer)  # 0–5
    ai_rationale: Mapped[str | None] = mapped_column(Text)
    human_score: Mapped[int | None] = mapped_column(Integer)  # 0–5, overrides ai_score
    human_note: Mapped[str | None] = mapped_column(Text)
    overridden_by: Mapped[str | None] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    category: Mapped[DecisionCategory] = relationship(lazy="selectin")


class PortalGuide(Base):
    """Curated static registration/submission guidance per portal (+ AI gap-fill)."""

    __tablename__ = "bid_portal_guide"

    portal_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    registration_steps: Mapped[list | None] = mapped_column(JSON, default=list)
    submission_channel: Mapped[str | None] = mapped_column(String(255))
    signature_level: Mapped[str | None] = mapped_column(String(50))  # textform|FES|QES
    notes: Mapped[str | None] = mapped_column(Text)
