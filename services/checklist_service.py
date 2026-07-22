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
        out.append(KeyDate(kind=d["kind"], date=dt, source_link=d.get("source_link")))
    return out


async def regenerate_checklist(bid: Bid, snapshot: dict[str, Any]) -> dict[str, int]:
    """Additively merge a freshly-generated checklist into an existing bid.

    Returns a small diff summary. Existing items (matched by
    criterion_kind+title) are preserved with their human state; new ones appended.
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
    """Pre-flight gate: are all FORMAL items resolved? (2.3/2.6)

    A bid must not be marked submittable while any formal item is still open —
    formal defects are the top cause of exclusion.
    """
    formal = [i for i in bid.checklist_items if i.criterion_kind == "formal"]
    open_formal = [i for i in formal if i.status == "open"]
    return {
        "formal_total": len(formal),
        "formal_open": len(open_formal),
        "ready": len(open_formal) == 0,
        "blocking": [{"id": i.id, "title": i.title} for i in open_formal],
    }
