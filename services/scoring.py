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
    """Tokenize text into lowercase alphabetic tokens filtering stopwords.

    Splits input text into normalized lower-case tokens of at least 4 characters,
    stripping common German and English procurement stopwords to support robust
    lexical matching between requirements and document bodies.

    Agent Metadata:
      @intent: Normalize free-form tender or requirement text into high-signal keyword sets for matching.
      @domain: Bidding/Scoring
      @capability: util:tokenize
      @keywords: tokenize, regex, stopwords, lexical_matching, token_overlap
      @side_effects: none (pure)
      @idempotent: true
      @agent_notes: Strips German and English stopwords; ignores tokens shorter than 4 characters.

    Contracts:
      @param text (str | None): Raw input string or None.
      @return (set[str]): Set of unique filtered lowercase keyword tokens.
      @raises None: Does not raise exceptions.

    Example:
      >>> toks = _tokens("ISO 27001 Zertifizierung erforderlich")
      >>> "zertifizierung" in toks
      True
    """
    if not text:
        return set()
    return {t for t in re.findall(r"[a-zä-üß]{4,}", text.lower()) if t not in _STOPWORDS}


def _kind_ratio(items: list[ChecklistItem], kind: str) -> tuple[int, int]:
    """Calculate the completion ratio for checklist items of a given criterion kind.

    Filters checklist items matching the specified criterion kind ('formal', 'suitability',
    or 'award') and calculates the count of resolved items ('done' or 'n_a') against the
    total items of that kind.

    Agent Metadata:
      @intent: Measure progress against specific procurement criterion categories.
      @domain: Bidding/Scoring
      @capability: score:criterion_progress
      @keywords: criterion, completion_ratio, checklist, formal, suitability, award
      @side_effects: none (pure)
      @idempotent: true
      @agent_notes: Items with status 'done' or 'n_a' are considered resolved.

    Contracts:
      @param items (list[ChecklistItem]): Collection of checklist items associated with a bid.
      @param kind (str): Target criterion kind (e.g. 'formal', 'suitability', 'award').
      @return (tuple[int, int]): Tuple of (resolved_count, total_count).
      @raises None: Pure function.

    Example:
      >>> resolved, total = _kind_ratio(bid.checklist_items, "formal")
    """
    of_kind = [i for i in items if i.criterion_kind == kind]
    done = [i for i in of_kind if i.status in ("done", "n_a")]
    return len(done), len(of_kind)


def _days_remaining(bid: Bid) -> int | None:
    """Compute integer calendar days remaining until the bid submission deadline.

    Inspects key dates on the bid for a 'submission' milestone, coerces timezone
    to UTC if needed, and computes the delta in days against the current UTC timestamp.

    Agent Metadata:
      @intent: Determine submission countdown to factor deadline pressure into readiness scoring.
      @domain: Bidding/Scoring
      @capability: time:submission_countdown
      @keywords: deadline, submission, key_dates, countdown, buffer
      @side_effects: none (pure)
      @idempotent: conditional
      @agent_notes: Evaluates relative to current datetime (UTC). Returns None if submission date is absent.

    Contracts:
      @param bid (Bid): The target bid entity containing key dates.
      @return (int | None): Days remaining until submission or None if submission date unset.
      @raises None: Handles missing or naive timestamps safely.

    Example:
      >>> days = _days_remaining(bid)
    """
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
    """Compute weighted, fully-itemised readiness score (0–100) for a bid.

    Calculates an explainable readiness score across 5 weighted dimensions:
    formal readiness (0.35), suitability coverage (0.25), award preparation (0.15),
    document evidence match rate (0.15), and deadline buffer (0.10). Every criterion
    produces a human-readable detail string and bounded score.

    Agent Metadata:
      @intent: Produce an explainable, auditable readiness score from bid checklist and timeline data.
      @domain: Bidding/Scoring
      @capability: score:compute_readiness
      @keywords: score, readiness, weights, formal_readiness, suitability, award, deadline_buffer
      @side_effects: none (pure)
      @idempotent: conditional
      @agent_notes: Pure computation based on bid state and time; does not modify DB.

    Contracts:
      @param bid (Bid): The Bid instance with checklist items, documents, and key dates loaded.
      @return (dict[str, Any]): Dictionary containing 'total' score (0-100) and 'criteria' list with breakdowns.
      @raises None: Handles empty checklists or absent deadlines gracefully with defaults.

    Example:
      >>> score_card = compute_score(bid)
      >>> print(score_card["total"])
      78.5
    """
    items = bid.checklist_items
    criteria: list[dict[str, Any]] = []

    def add(key: str, label: str, score: float, detail: str) -> None:
        """Append an itemized criterion score dictionary to the criteria breakdown list.

        Agent Metadata:
          @intent: Record bounded score and weights for an individual evaluation criterion.
          @domain: Bidding/Scoring
          @capability: score:record_criterion
          @keywords: criterion, score_entry, weight_clamp
          @side_effects: none (mutates local closure list)
          @idempotent: false
          @agent_notes: Clamps score to [0.0, 100.0] and rounds to 1 decimal place.

        Contracts:
          @param key (str): Weight identifier key present in WEIGHTS dictionary.
          @param label (str): Human-readable display label.
          @param score (float): Raw score value before clamping.
          @param detail (str): Human-readable explanatory explanation string.
          @return None: Appends in-place to criteria list.
          @raises None: Pure helper closure.

        Example:
          >>> add("formal_readiness", "Formal readiness", 100.0, "All resolved")
        """
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
    """Match bid documents and cross-bid corpus assets against open requirements.

    Executes lexical token overlap analysis between unresolved checklist items and
    all uploaded documents (both from this bid and from the historical cross-bid corpus).
    Matches against own documents update the checklist item's AI verification status,
    while cross-bid matches are surfaced as reusable evidence candidates without auto-completing.

    Agent Metadata:
      @intent: Break down organizational silos by discovering reusable document evidence across all bids.
      @domain: Bidding/Scoring
      @capability: match:document_requirements
      @keywords: document_matching, corpus_reuse, checklist, evidence, lexical_overlap
      @side_effects: db:mutate (updates checklist_item.ai_verification and commits)
      @idempotent: true
      @agent_notes: Cross-bid corpus matches do NOT mark items done to maintain human governance. Commits session.

    Contracts:
      @param db (AsyncSession): SQLAlchemy asynchronous database session.
      @param bid (Bid): The Bid entity whose checklist items and documents are being matched.
      @return (dict[str, Any]): Dictionary containing 'matches' list and 'corpus_size' count.
      @raises SQLAlchemyError: If database read or commit fails.

    Example:
      >>> match_result = await match_documents(db, bid)
      >>> print(match_result["corpus_size"])
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
    """Synthesize bid/no-bid/review recommendation with transparent rationale.

    Synthesizes multiple evidence streams: quantitative readiness score, formal gate
    blockers, submission timeline, cross-bid corpus evidence, and the strategic
    decision matrix evaluation. Produces a definitive recommendation ('bid', 'no_bid',
    or 'review') with confidence levels and prioritized explanatory bullet points.

    Agent Metadata:
      @intent: Deliver decisive, explainable bid/no-bid recommendations grounded in risk and strategic matrix scoring.
      @domain: Bidding/Scoring
      @capability: evaluate:bid_recommendation
      @keywords: recommendation, bid_no_bid, formal_gate, readiness_score, decision_matrix, confidence
      @side_effects: db:mutate (via match_documents DB commit)
      @idempotent: conditional
      @agent_notes: Strategic decision matrix evaluation takes precedence over operational readiness thresholds when active.

    Contracts:
      @param db (AsyncSession): SQLAlchemy async session for loading corpus and matrix evaluation.
      @param bid (Bid): The Bid instance to evaluate.
      @return (dict[str, Any]): Dictionary with recommendation, confidence, score breakdown, matrix summary, and reasons.
      @raises SQLAlchemyError: If database queries fail.

    Example:
      >>> advice = await recommend(db, bid)
      >>> if advice["recommendation"] == "bid":
      ...     proceed_to_proposal()
    """
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

    # Strategic layer: an evaluated decision matrix leads the recommendation.
    # The expert's weighted criteria decide bid/no-bid; the operational readiness
    # reasoning above stays as supporting context.
    matrix_summary = None
    from services.decision_matrix import get_evaluation

    try:
        evaluation = await get_evaluation(db, bid)
    except LookupError:
        evaluation = None
    if evaluation and evaluation["evaluated"]:
        matrix_summary = {
            "matrix_name": evaluation["matrix_name"],
            "total_points": evaluation["total_points"],
            "threshold": evaluation["threshold"],
            "max_points": evaluation["max_points"],
            "verdict": evaluation["verdict"],
            "overrides": sum(1 for c in evaluation["categories"] if c["human_score"] is not None),
        }
        decision = evaluation["verdict"]
        margin = abs(evaluation["total_points"] - evaluation["threshold"]) / max(1, evaluation["max_points"])
        confidence = round(min(0.95, 0.6 + margin), 2)
        reasons.insert(
            0,
            f"Decision matrix '{evaluation['matrix_name']}': {evaluation['total_points']}/{evaluation['max_points']} "
            f"weighted points vs threshold {evaluation['threshold']} → {evaluation['verdict'].upper().replace('_', ' ')}"
            + (f" ({matrix_summary['overrides']} human override(s) applied)" if matrix_summary["overrides"] else ""),
        )

    return {
        "recommendation": decision,
        "confidence": round(confidence, 2),
        "score": score,
        "matrix": matrix_summary,
        "reusable_evidence": reusable,
        "reasons": reasons,
    }
