"""Checklist + deadline generation and regeneration (diff).

Builds the requirement checklist and key dates from a tender snapshot via the
AI backend (mocked in v1). Regeneration is additive: existing items keep their
human state (status/assignee/comments); only genuinely new requirements are
appended — so re-importing an amended notice / Bieterfrage answer never wipes work.
"""

from __future__ import annotations

from typing import Any

from core.ai_client import get_ai_client
from core.logger import setup_logger
from models.bid import Bid, ChecklistItem, KeyDate

logger = setup_logger("bidding-checklist")


async def build_checklist(snapshot: dict[str, Any]) -> list[ChecklistItem]:
    """Build a structured requirement checklist from a tender snapshot via AI.

    Invokes the configured AI client to parse tender criteria and notice documents,
    deriving categorized checklist items across formal, suitability, and award dimensions
    along with required evidence types, source provenance, and metadata.

    Agent Metadata:
      @intent: Transform raw tender notice criteria into actionable, trackable checklist items.
      @domain: Bidding/Checklist
      @capability: generate:checklist
      @keywords: checklist, tender_snapshot, requirements, formal, suitability, award, ai_extraction
      @side_effects: network:outbound (when AI connector is active)
      @idempotent: true
      @agent_notes: Resulting entities are transient (unattached to session); caller must associate them with a Bid.

    Contracts:
      @param snapshot (dict[str, Any]): Normalized tender snapshot containing title, description, criteria, and lot info.
      @return (list[ChecklistItem]): Instantiated ChecklistItem domain model objects ready for persistence.
      @raises RuntimeError: If the AI backend fails during checklist generation.

    Example:
      >>> items = await build_checklist(snapshot_dict)
      >>> print(len(items))
      10
    """
    ai = get_ai_client()
    raw = await ai.generate_checklist(snapshot)
    return [
        ChecklistItem(
            criterion_kind=i["criterion_kind"],
            requirement_type=i["requirement_type"],
            title=i["title"],
            source_link=i.get("source_link"),
            status=i.get("status", "open"),
            order=i.get("order", 0),
            metadata_json=i.get("metadata_json"),
        )
        for i in raw
    ]


async def build_key_dates(snapshot: dict[str, Any]) -> list[KeyDate]:
    """Extract key procurement milestone dates from a tender snapshot.

    Parses ISO timestamps for critical tender milestones (submission deadlines,
    questions deadlines, registration windows, and validity periods) using the AI client
    and normalizes them into KeyDate domain models with UTC timestamps.

    Agent Metadata:
      @intent: Detect and structure time-sensitive procurement deadlines from notices.
      @domain: Bidding/Checklist
      @capability: extract:deadlines
      @keywords: deadlines, key_dates, submission_deadline, bieterfragen, bindefrist, time_audit
      @side_effects: network:outbound (when AI connector is active)
      @idempotent: true
      @agent_notes: Kind is truncated to max 20 characters to comply with DB column constraints.

    Contracts:
      @param snapshot (dict[str, Any]): Tender snapshot dictionary with date strings.
      @return (list[KeyDate]): List of uncommitted KeyDate entities.
      @raises None: Safely handles unparseable date formats by falling back to None.

    Example:
      >>> dates = await build_key_dates(snapshot_dict)
      >>> print([d.kind for d in dates])
      ['submission', 'questions']
    """
    from datetime import datetime

    ai = get_ai_client()
    raw = await ai.extract_deadlines(snapshot)
    out: list[KeyDate] = []
    for d in raw:
        dt = d.get("date")
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            except ValueError:
                dt = None
        kind_str = str(d.get("kind") or "submission")[:20]
        out.append(KeyDate(kind=kind_str, date=dt, source_link=d.get("source_link")))
    return out


async def regenerate_checklist(bid: Bid, snapshot: dict[str, Any]) -> dict[str, int]:
    """Additively merge freshly-generated checklist requirements into an existing bid.

    Extracts a fresh set of requirements from an updated tender notice or corrigendum
    and performs a non-destructive, additive diff against existing bid checklist items.
    Existing items keep their human-assigned status, assignees, and comments; only
    genuinely new items are appended with incremented order indices.

    Agent Metadata:
      @intent: Update bid requirements upon notice amendment without wiping human work or status.
      @domain: Bidding/Checklist
      @capability: merge:checklist_additive
      @keywords: diff, merge, additive_regeneration, corrigendum, checklist_items, non_destructive
      @side_effects: db:mutate (appends new ChecklistItem instances to bid relationship)
      @idempotent: true
      @agent_notes: De-duplicates items using composite key (criterion_kind, title). Caller must commit session.

    Contracts:
      @param bid (Bid): The existing Bid entity with checklist_items loaded.
      @param snapshot (dict[str, Any]): Updated tender snapshot dictionary.
      @return (dict[str, int]): Summary mapping containing counts for 'added' and 'kept' items.
      @raises RuntimeError: If AI generation fails.

    Example:
      >>> diff = await regenerate_checklist(bid, latest_snapshot)
      >>> print(f"Added {diff['added']} new items, preserved {diff['kept']} existing.")
    """
    ai = get_ai_client()
    fresh = await ai.generate_checklist(snapshot)
    existing_keys = {(i.criterion_kind, i.title) for i in bid.checklist_items}
    next_order = (max((i.order for i in bid.checklist_items), default=-1)) + 1

    added = 0
    for item in fresh:
        key = (item["criterion_kind"], item["title"])
        if key in existing_keys:
            continue
        bid.checklist_items.append(
            ChecklistItem(
                criterion_kind=item["criterion_kind"],
                requirement_type=item["requirement_type"],
                title=item["title"],
                source_link=item.get("source_link"),
                status="open",
                order=next_order,
                metadata_json=item.get("metadata_json"),
            )
        )
        next_order += 1
        added += 1

    return {"added": added, "kept": len(existing_keys)}


def formal_gate(bid: Bid) -> dict[str, Any]:
    """Evaluate pre-flight formal gate to determine submission readiness.

    Verifies whether all checklist items designated under criterion_kind == 'formal'
    (e.g., signatures, non-exclusion declarations, mandatory forms, submission channels)
    have been resolved. Since formal defects constitute the single largest cause of
    immediate procurement exclusion, this gate acts as a strict guardrail before submission.

    Agent Metadata:
      @intent: Prevent disqualification by enforcing a strict blocker on unresolved formal requirements.
      @domain: Bidding/Checklist
      @capability: gate:formal_readiness
      @keywords: formal_gate, preflight, compliance, formal_defects, exclusion_prevention, blocker
      @side_effects: none (pure)
      @idempotent: true
      @agent_notes: If ready is False, the bid must not transition to submitted status.

    Contracts:
      @param bid (Bid): Bid entity with populated checklist_items.
      @return (dict[str, Any]): Summary dict with 'formal_total', 'formal_open', 'ready' (bool), and 'blocking' list.
      @raises None: Pure function.

    Example:
      >>> gate = formal_gate(bid)
      >>> if not gate["ready"]:
      ...     print("Blocked by:", [b["title"] for b in gate["blocking"]])
    """
    formal = [i for i in bid.checklist_items if i.criterion_kind == "formal"]
    open_formal = [i for i in formal if i.status == "open"]
    return {
        "formal_total": len(formal),
        "formal_open": len(open_formal),
        "ready": len(open_formal) == 0,
        "blocking": [{"id": i.id, "title": i.title} for i in open_formal],
    }
