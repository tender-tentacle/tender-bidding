"""Transparent bid scoring, document↔requirement matching, and bid/no-bid advice.

Every number is explainable: the score is a weighted sum of named criteria, each
carrying its own weight, raw value, and a human-readable detail line. The
recommendation lists the exact reasons (including reusable evidence found in
OTHER bids' document corpus — the cross-silo knowledge reuse this service exists
to create). Deterministic on purpose: mock-mode friendly and auditable; an AI
backend can later refine, but never obscure, this breakdown.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from models.bid import Bid, BidDocument, ChecklistItem
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Criterion weights (sum = 1.0). Formal dominates: most bids die on formalities.
WEIGHTS = {
    "formal_readiness": 0.35,
    "suitability_coverage": 0.25,
    "award_preparation": 0.15,
    "document_evidence": 0.15,
    "deadline_buffer": 0.10,
}

_STOPWORDS = {"the", "and", "with", "from", "each", "required", "valid", "der", "die", "das", "und", "für", "von"}


def _tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    return {t for t in re.findall(r"[a-zä-üß]{4,}", text.lower()) if t not in _STOPWORDS}


def _kind_ratio(items: list[ChecklistItem], kind: str) -> tuple[int, int]:
    of_kind = [i for i in items if i.criterion_kind == kind]
    done = [i for i in of_kind if i.status in ("done", "n_a")]
    return len(done), len(of_kind)


def _days_remaining(bid: Bid) -> int | None:
    submission = next((kd for kd in bid.key_dates if kd.kind == "submission" and kd.date), None)
    if not submission:
        return None
    dt = submission.date
    if dt is None:  # unreachable given the filter above, but narrows the type
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return (dt - datetime.now(UTC)).days


def compute_score(bid: Bid) -> dict[str, Any]:
    """Weighted, fully-itemised readiness score (0–100) for a bid."""
    items = bid.checklist_items
    criteria: list[dict[str, Any]] = []

    def add(key: str, label: str, score: float, detail: str) -> None:
        criteria.append(
            {
                "key": key,
                "label": label,
                "weight": WEIGHTS[key],
                "score": round(max(0.0, min(100.0, score)), 1),
                "detail": detail,
            }
        )

    for key, label, kind in (
        ("formal_readiness", "Formal readiness", "formal"),
        ("suitability_coverage", "Suitability coverage", "suitability"),
        ("award_preparation", "Award preparation", "award"),
    ):
        done, total = _kind_ratio(items, kind)
        add(key, label, 100.0 * done / total if total else 100.0, f"{done}/{total} {kind} requirements resolved")

    # Document evidence: requirements backed by an AI-matched upload.
    evidenced = [i for i in items if (i.ai_verification or {}).get("status") == "matched"]
    doc_target = [i for i in items if i.requirement_type in ("reference", "profile", "certificate", "declaration")]
    add(
        "document_evidence",
        "Document evidence",
        100.0 * len(evidenced) / len(doc_target) if doc_target else (100.0 if bid.documents else 0.0),
        f"{len(evidenced)}/{len(doc_target)} evidence-type requirements matched to an uploaded document",
    )

    days = _days_remaining(bid)
    if days is None:
        add("deadline_buffer", "Deadline buffer", 50.0, "No submission deadline known — neutral 50")
    else:
        add("deadline_buffer", "Deadline buffer", min(100.0, days / 21 * 100.0), f"{days} days until submission")

    total_score = round(sum(c["score"] * c["weight"] for c in criteria), 1)
    return {"total": total_score, "criteria": criteria}


async def match_documents(db: AsyncSession, bid: Bid) -> dict[str, Any]:
    """Re-match all documents (this bid + the cross-bid corpus) against open requirements.

    Same-bid keyword matches set the item's ai_verification; corpus hits from other
    bids are reported as reusable evidence but never auto-complete an item.
    """
    corpus = list((await db.execute(select(BidDocument).where(BidDocument.bid_id != bid.id))).scalars().all())
    matches: list[dict[str, Any]] = []
    for item in bid.checklist_items:
        if item.status == "done":
            continue
        item_tokens = _tokens(item.title) | _tokens(item.requirement_type)
        best: tuple[int, BidDocument, bool] | None = None  # (overlap, doc, is_own)
        for doc, own in [(d, True) for d in bid.documents] + [(d, False) for d in corpus]:
            overlap = len(item_tokens & (_tokens(doc.filename) | _tokens(doc.markdown) | _tokens(doc.doc_type)))
            if overlap >= 2 and (best is None or overlap > best[0]):
                best = (overlap, doc, own)
        if best:
            overlap, doc, own = best
            source = "this bid" if own else f"bid {doc.bid_id[:8]} (reusable corpus)"
            if own:
                item.ai_verification = {"status": "matched", "detail": f"{doc.filename} covers this ({overlap} terms)"}
            matches.append(
                {
                    "checklist_item_id": item.id,
                    "requirement": item.title,
                    "document_id": doc.id,
                    "filename": doc.filename,
                    "from_corpus": not own,
                    "overlap": overlap,
                    "source": source,
                }
            )
    await db.commit()
    return {"matches": matches, "corpus_size": len(corpus)}


async def recommend(db: AsyncSession, bid: Bid) -> dict[str, Any]:
    """Bid / no-bid / review advice with explicit reasons."""
    score = compute_score(bid)
    reasons: list[str] = []

    formal_open = sum(1 for i in bid.checklist_items if i.criterion_kind == "formal" and i.status == "open")
    days = _days_remaining(bid)

    # Reusable evidence from other bids (silo-breaking corpus).
    corpus = await match_documents(db, bid)
    reusable = [m for m in corpus["matches"] if m["from_corpus"]]
    if reusable:
        reasons.append(f"{len(reusable)} requirement(s) covered by documents already uploaded in other bids")

    if formal_open == 0:
        reasons.append("All formal requirements resolved — no exclusion risk from formalities")
    else:
        reasons.append(f"{formal_open} formal requirement(s) still open — formal defects are the top exclusion cause")
    if days is not None:
        reasons.append(f"{days} days remaining until submission")

    if formal_open > 0 and days is not None and days < 7:
        decision, confidence = "no_bid", 0.85
        reasons.insert(0, "Formal gate blocked with under a week left — exclusion risk too high")
    elif score["total"] >= 65:
        decision, confidence = "bid", min(0.95, score["total"] / 100)
        reasons.insert(0, f"Readiness score {score['total']}/100 clears the bid threshold (65)")
    elif score["total"] >= 45:
        decision, confidence = "review", 0.6
        reasons.insert(0, f"Readiness score {score['total']}/100 is borderline — human review advised")
    else:
        decision, confidence = "no_bid", 0.7
        reasons.insert(0, f"Readiness score {score['total']}/100 below the review threshold (45)")

    return {
        "recommendation": decision,
        "confidence": round(confidence, 2),
        "score": score,
        "reusable_evidence": reusable,
        "reasons": reasons,
    }
