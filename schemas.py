"""Pydantic request/response models for the bidding API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class LotSnapshot(BaseModel):
    lot_id: str | None = None
    lot_number: int | None = None
    title: str | None = None
    description: str | None = None
    document_text: str | None = None


class BidRelayPayload(BaseModel):
    """Snapshot pushed by enriching when a tender/group is marked as a bid (ACL)."""

    source_ref: str
    source_kind: str = "tender"
    title: str
    customer: str | None = None
    source_system: str | None = None
    driver_user_id: str | None = None
    cluster: str | None = None
    deadline_at: datetime | None = None
    questions_deadline_at: datetime | None = None
    document_text: str | None = None
    description: str | None = None
    lots: list[LotSnapshot] = []


class CollaboratorIn(BaseModel):
    user_id: str
    role: str = "contributor"


class CollaboratorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str
    role: str


class ChecklistItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    criterion_kind: str
    requirement_type: str
    title: str
    source_link: str | None = None
    status: str
    ai_verification: dict | None = None
    assignee_user_id: str | None = None
    lot_scope: str | None = None
    order: int


class ChecklistItemUpdate(BaseModel):
    status: str | None = None
    assignee_user_id: str | None = None


class KeyDateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    kind: str
    date: datetime | None = None
    source_link: str | None = None
    days_remaining: int | None = None


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    kind: str
    sensitivity: str
    doc_type: str | None = None
    filename: str
    uploaded_by: str | None = None
    ai_verification: dict | None = None
    checklist_item_id: str | None = None
    created_at: datetime


class CommentIn(BaseModel):
    target_type: str = "bid"
    target_id: str | None = None
    body: str


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    target_type: str
    target_id: str | None = None
    author_user_id: str | None = None
    body: str
    created_at: datetime


class BidSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    source_ref: str
    title: str
    customer: str | None = None
    status: str
    driver_user_id: str | None = None
    portal_key: str | None = None
    version: int


class FormalGate(BaseModel):
    formal_total: int
    formal_open: int
    ready: bool
    blocking: list[dict]


class BidDetail(BidSummary):
    source_kind: str
    lots_in_scope: list | None = None
    cluster: str | None = None
    loss_reason: str | None = None
    loss_note: str | None = None
    collaborators: list[CollaboratorOut] = []
    checklist_items: list[ChecklistItemOut] = []
    documents: list[DocumentOut] = []
    key_dates: list[KeyDateOut] = []
    formal_gate: FormalGate | None = None


class StatusUpdate(BaseModel):
    status: str
    expected_version: int  # optimistic concurrency
    loss_reason: str | None = None
    loss_note: str | None = None


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    actor_user_id: str | None = None
    action: str
    detail: dict | None = None
    created_at: datetime
