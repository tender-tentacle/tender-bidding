"""Bid creation from an enriching snapshot (idempotent)."""

from __future__ import annotations

from typing import Any

from core.logger import setup_logger
from models.bid import Bid, BidCollaborator
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from services import activity
from services.checklist_service import build_checklist, build_key_dates
from services.portal_guide import portal_key_for

logger = setup_logger("bidding-service")


def snapshot_dict(payload: Any) -> dict[str, Any]:
    """Normalise an incoming tender relay payload into the AI snapshot dictionary format.

    Extracts dictionary attributes from either a Pydantic model instance or a raw dict,
    guaranteeing default structure such as an empty list for 'lots' if omitted.

    Agent Metadata:
      @intent: Provide standard dictionary normalization for polymorphic incoming tender payloads.
      @domain: Bidding/Application
      @capability: util:payload_normalization
      @keywords: normalize, snapshot, pydantic, tender_payload, serialization
      @side_effects: none (pure)
      @idempotent: true
      @agent_notes: Checks hasattr(payload, 'model_dump') before falling back to dict casting.

    Contracts:
      @param payload (Any): Pydantic BaseModel instance or dictionary containing tender snapshot data.
      @return (dict[str, Any]): Normalized dictionary with 'lots' guaranteed.
      @raises None: Pure function.

    Example:
      >>> data = snapshot_dict(pydantic_tender_obj)
      >>> isinstance(data["lots"], list)
      True
    """
    d = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
    d.setdefault("lots", [])
    return d


async def get_by_source_ref(db: AsyncSession, source_ref: str) -> Bid | None:
    """Retrieve a Bid entity by its source reference, primary ID, or enriching ID.

    Queries the Bid database table loading related collaborators, checklist items,
    documents, required documents, and key dates via selectinload to avoid N+1 queries.
    Orders by version and creation date descending to return the latest revision.

    Agent Metadata:
      @intent: Fetch a fully-hydrated Bid aggregate root using any external or internal identifier.
      @domain: Bidding/Persistence
      @capability: db:bid_read
      @keywords: bid, source_ref, enriching_id, selectinload, aggregate_root
      @side_effects: none (pure query)
      @idempotent: true
      @agent_notes: Uses populate_existing=True to refresh session cache if already loaded.

    Contracts:
      @param db (AsyncSession): Active asynchronous database session.
      @param source_ref (str): Notice source reference, UUID primary key, or upstream enriching_id.
      @return (Bid | None): Fully populated Bid instance if found, or None.
      @raises SQLAlchemyError: If database read encounters an issue.

    Example:
      >>> bid = await get_by_source_ref(db, "ted-2026-001234")
    """
    return (
        await db.execute(
            select(Bid)
            .options(
                selectinload(Bid.collaborators),
                selectinload(Bid.checklist_items),
                selectinload(Bid.documents),
                selectinload(Bid.required_documents),
                selectinload(Bid.key_dates),
            )
            .where(or_(Bid.source_ref == source_ref, Bid.id == source_ref, Bid.enriching_id == source_ref))
            .order_by(Bid.version.desc(), Bid.created_at.desc())
            .execution_options(populate_existing=True)
        )
    ).scalars().first()


async def create_bid_from_snapshot(db: AsyncSession, payload: Any) -> tuple[Bid, bool]:
    """Create or retrieve a Bid with AI-generated checklist and deadlines from a snapshot.

    Idempotently creates a new Bid workspace or returns an existing one identified by
    source_ref. If the snapshot is provisional (tender flagged as interesting), the bid is
    created in 'exploring' status. If committed (triage='bid'), it is created in 'draft'
    status. If an 'exploring' workspace already exists and a committed snapshot arrives,
    it promotes the workspace to 'draft' while preserving all existing analysis.

    Agent Metadata:
      @intent: Orchestrate idempotent bid workspace initialization, checklist generation, and triage promotion.
      @domain: Bidding/Application
      @capability: bid:create_from_snapshot
      @keywords: create_bid, snapshot, idempotency, checklist_generation, exploring, draft, triage_promote
      @side_effects: db:mutate (inserts Bid, ChecklistItem, KeyDate, BidCollaborator, BidActivity; commits)
      @idempotent: true
      @agent_notes: Idempotent on source_ref. Automatically links driver_user_id as lead collaborator.

    Contracts:
      @param db (AsyncSession): SQLAlchemy async session for mutations.
      @param payload (Any): Raw snapshot dictionary or Pydantic tender schema.
      @return (tuple[Bid, bool]): Tuple of (bid_instance, created_flag) where created_flag is False if already existed.
      @raises SQLAlchemyError: If persistence operations or commits fail.

    Example:
      >>> bid, created = await create_bid_from_snapshot(db, snapshot_payload)
      >>> if created:
      ...     print(f"Created new bid {bid.id}")
    """
    snap = snapshot_dict(payload)
    provisional = bool(snap.get("provisional"))
    existing = await get_by_source_ref(db, snap["source_ref"])
    if existing:
        if existing.status == "exploring" and not provisional:
            await _promote(db, existing, snap)
        return existing, False

    bid = Bid(
        source_ref=snap["source_ref"],
        source_kind=snap.get("source_kind", "tender"),
        title=snap.get("title") or "Untitled bid",
        customer=snap.get("customer"),
        cluster=snap.get("cluster"),
        driver_user_id=snap.get("driver_user_id"),
        portal_key=portal_key_for(snap.get("source_system")),
        lots_in_scope=[
            lot.get("lot_id") or lot.get("lot_number") if isinstance(lot, dict) else str(lot)
            for lot in (snap.get("lots") or [])
        ],
        cpv_codes=snap.get("cpv_codes") or [],
        selection_criteria=snap.get("selection_criteria"),
        # Classification Matches
        matched_labels=snap.get("matched_labels") or [],
        matched_sectors=snap.get("matched_sectors") or [],
        matched_services=snap.get("matched_services") or [],
        matched_people=snap.get("matched_people") or [],
        matched_campaigns=snap.get("matched_campaigns") or [],
        matched_trends=snap.get("matched_trends") or [],
        matched_practices=snap.get("matched_practices") or [],
        matched_clusters=snap.get("matched_clusters") or [],
        matched_ressorts=snap.get("matched_ressorts") or [],
        matched_horizontals=snap.get("matched_horizontals") or [],
        classification_matches=snap.get("classification_matches") or [],
        status="exploring" if provisional else "draft",
    )
    bid.checklist_items = await build_checklist(snap)
    bid.key_dates = await build_key_dates(snap)
    if snap.get("driver_user_id"):
        bid.collaborators = [BidCollaborator(user_id=snap["driver_user_id"], role="lead")]

    db.add(bid)
    await db.flush()
    activity.record(
        db,
        bid.id,
        snap.get("driver_user_id"),
        "bid.created",
        {"source_ref": bid.source_ref, "checklist_items": len(bid.checklist_items), "provisional": provisional},
    )
    bid_id = bid.id
    source_ref_val = bid.source_ref
    item_count = len(bid.checklist_items)
    await db.commit()
    logger.info(
        f"🎯 Created {'provisional ' if provisional else ''}bid {bid_id} from {source_ref_val} "
        f"({item_count} checklist items)"
    )
    created_bid = await get_by_source_ref(db, source_ref_val)
    return created_bid, True


async def _promote(db: AsyncSession, bid: Bid, snap: dict[str, Any]) -> None:
    """Promote an exploring bid workspace to committed draft status.

    Transitions a provisional bid (status 'exploring') into a full 'draft' bid
    when upstream triage confirms a 'bid' decision. Bumps version number, attaches
    driver as lead collaborator if unassigned, records the audit trail, and commits.

    Agent Metadata:
      @intent: Convert an exploratory research workspace to a committed bid without losing analysis.
      @domain: Bidding/Application
      @capability: bid:promote_status
      @keywords: promote, exploring, draft, triage, audit_log, lead_driver
      @side_effects: db:mutate (updates bid status, version, collaborator; writes activity; commits)
      @idempotent: true
      @agent_notes: Increments bid.version and flushes audit event.

    Contracts:
      @param db (AsyncSession): SQLAlchemy async session.
      @param bid (Bid): The existing Bid entity in 'exploring' state.
      @param snap (dict[str, Any]): Current snapshot dictionary with driver information.
      @return None: Mutates and commits in-place.
      @raises SQLAlchemyError: If commit fails.

    Example:
      >>> await _promote(db, bid, snapshot_data)
    """
    bid.status = "draft"
    bid.version += 1
    driver = snap.get("driver_user_id")
    if driver and not bid.driver_user_id:
        bid.driver_user_id = driver
        if driver not in {c.user_id for c in bid.collaborators}:
            bid.collaborators.append(BidCollaborator(user_id=driver, role="lead"))
    activity.record(db, bid.id, driver, "bid.promoted", {"from": "exploring", "to": "draft"})
    await db.commit()
    logger.info(f"⬆️ Promoted exploring bid {bid.id} ({bid.source_ref}) to draft")


async def discard_by_source_ref(db: AsyncSession, source_ref: str, actor: str | None = None) -> tuple[Bid | None, bool]:
    """Archive a provisional exploring workspace following a no-bid triage verdict.

    Safely marks an 'exploring' workspace as 'withdrawn' when upstream triage decides
    against bidding. Protects committed bids ('draft', 'submitted', 'won') by refusing
    to auto-discard them from upstream triage signals, requiring manual withdrawal.

    Agent Metadata:
      @intent: Archive provisional bid evaluations upon negative triage while protecting committed bids.
      @domain: Bidding/Application
      @capability: bid:archive_provisional
      @keywords: discard, archive, no_bid, withdrawn, provisional_guard, audit_trail
      @side_effects: db:mutate (updates status to 'withdrawn', records activity, commits)
      @idempotent: true
      @agent_notes: Will return (bid, False) if the bid exists but is NOT in 'exploring' status.

    Contracts:
      @param db (AsyncSession): Active database session.
      @param source_ref (str): Source identifier of the bid to discard.
      @param actor (str | None): User ID of the user or agent triggering the discard.
      @return (tuple[Bid | None, bool]): Tuple of (bid, archived_boolean).
      @raises SQLAlchemyError: On database error.

    Example:
      >>> bid, archived = await discard_by_source_ref(db, "ted-2026-001234", actor="user_123")
    """
    bid = await get_by_source_ref(db, source_ref)
    if not bid:
        return None, False
    if bid.status != "exploring":
        return bid, False
    bid.status = "withdrawn"
    bid.version += 1
    activity.record(db, bid.id, actor, "bid.archived", {"reason": "triage_no_bid", "from": "exploring"})
    await db.commit()
    logger.info(f"🗄️ Archived exploring bid {bid.id} ({source_ref}) after no-bid triage")
    return bid, True
