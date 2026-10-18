"""Decision-matrix service: upload→categories, expert backend (edit + versioned
history, enriching-config style), per-bid AI evaluation with human override, and
the weighted bid/no-bid verdict.

Verdict rule (as specified by the expert user): each category is scored 0–5,
carries a weight 1–5, and the tender is a BID when
Σ(effective_score × weight) ≥ threshold — where the effective score is the
human override when present, else the AI score. Every AI score keeps its
rationale; every override keeps who/why; every matrix change is a version with
a history snapshot. Each category carries a `headline` and the expert's prose
`explanation` — the explanation is what the AI grounds its scoring on.
"""

from __future__ import annotations

from typing import Any

from core.ai_client import get_ai_client
from core.portal_intel import get_portal_intel_client
from models.bid import (
    Bid,
    BidCategoryRating,
    DecisionCategory,
    DecisionMatrix,
    DecisionMatrixHistory,
)
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

SCORE_RANGE = range(0, 6)  # 0–5
WEIGHT_RANGE = range(1, 6)  # 1–5


async def get_active_matrix(db: AsyncSession) -> DecisionMatrix | None:
    """Retrieve the currently active decision matrix configuration.

    Queries the DecisionMatrix table for an active matrix entity, ordering by
    creation timestamp descending to fetch the latest published version.

    Agent Metadata:
      @intent: Fetch the active decision matrix definition governing bid/no-bid evaluations.
      @domain: Bidding/DecisionMatrix
      @capability: db:get_active_matrix
      @keywords: decision_matrix, active_matrix, evaluation_rules, criteria_weights
      @side_effects: none (pure query)
      @idempotent: true
      @agent_notes: Returns None if no matrix has been uploaded or activated.

    Contracts:
      @param db (AsyncSession): SQLAlchemy async session.
      @return (DecisionMatrix | None): Active DecisionMatrix instance or None.
      @raises SQLAlchemyError: If database read fails.

    Example:
      >>> matrix = await get_active_matrix(db)
      >>> if matrix:
      ...     print(matrix.name, matrix.threshold)
    """
    return (
        (
            await db.execute(
                select(DecisionMatrix).where(DecisionMatrix.active).order_by(DecisionMatrix.created_at.desc())
            )
        )
        .scalars()
        .first()
    )


def matrix_dict(matrix: DecisionMatrix) -> dict[str, Any]:
    """Serialize a DecisionMatrix domain model and its categories into a dictionary.

    Computes max_points (5 * sum of category weights) and structures the matrix
    attributes for API responses and historical snapshot archiving.

    Agent Metadata:
      @intent: Provide standard serialization and max point calculation for decision matrices.
      @domain: Bidding/DecisionMatrix
      @capability: util:serialize_matrix
      @keywords: matrix_dict, serialization, max_points, category_weights
      @side_effects: none (pure)
      @idempotent: true
      @agent_notes: Each category weight is on a 1-5 scale; each category max score is 5.

    Contracts:
      @param matrix (DecisionMatrix): DecisionMatrix entity with categories loaded.
      @return (dict[str, Any]): Dictionary containing id, name, threshold, categories, and max_points.
      @raises None: Pure function.

    Example:
      >>> data = matrix_dict(matrix)
      >>> print(data["max_points"])
    """
    return {
        "id": matrix.id,
        "name": matrix.name,
        "threshold": matrix.threshold,
        "version": matrix.version,
        "source_filename": matrix.source_filename,
        "uploaded_by": matrix.uploaded_by,
        "max_points": 5 * sum(c.weight for c in matrix.categories),
        "categories": [
            {"id": c.id, "headline": c.headline, "explanation": c.explanation, "weight": c.weight}
            for c in matrix.categories
        ],
    }


async def _snapshot(db: AsyncSession, matrix: DecisionMatrix, *, change_summary: str, created_by: str | None) -> None:
    """Record an immutable version snapshot of a decision matrix and bump version number.

    Archives the current matrix state into DecisionMatrixHistory and increments
    matrix.version by 1, mirroring the audit pattern of the enriching service.

    Agent Metadata:
      @intent: Maintain immutable audit history and version progression for governance compliance.
      @domain: Bidding/DecisionMatrix
      @capability: audit:snapshot_matrix
      @keywords: snapshot, matrix_history, version_bump, audit, changelog
      @side_effects: db:mutate (inserts DecisionMatrixHistory, increments matrix.version)
      @idempotent: false
      @agent_notes: Appends to session unit of work; caller controls flushing or committing.

    Contracts:
      @param db (AsyncSession): Database session.
      @param matrix (DecisionMatrix): DecisionMatrix entity being versioned.
      @param change_summary (str): Narrative description of the modification.
      @param created_by (str | None): User ID of the editor.
      @return None: Mutates matrix in-place and adds history record.
      @raises None: Session operation.

    Example:
      >>> await _snapshot(db, matrix, change_summary="Increased threshold to 45", created_by="admin_1")
    """
    db.add(
        DecisionMatrixHistory(
            matrix_id=matrix.id,
            version=matrix.version,
            change_summary=change_summary,
            created_by=created_by,
            data=matrix_dict(matrix),
        )
    )
    matrix.version += 1


async def create_matrix_from_upload(
    db: AsyncSession, *, markdown: str, filename: str | None, uploaded_by: str | None
) -> DecisionMatrix:
    """Translate an uploaded decision matrix document via AI and activate it.

    Parses markdown document text using the AI client into weighted categories and
    a threshold, deactivates any previously active matrices, persists the new DecisionMatrix
    with its categories, and stores the initial version 1 history snapshot.

    Agent Metadata:
      @intent: Ingest uploaded criteria documents into a structured, active decision matrix.
      @domain: Bidding/DecisionMatrix
      @capability: matrix:create_from_upload
      @keywords: upload_matrix, ai_extraction, criteria, weights, threshold, activate
      @side_effects: db:mutate (deactivates existing matrices, inserts DecisionMatrix, categories, history; flushes)
      @idempotent: false
      @agent_notes: Flushes twice to capture generated IDs in history; caller must commit session.

    Contracts:
      @param db (AsyncSession): Active SQLAlchemy async session.
      @param markdown (str): Document text containing criteria definitions and weights.
      @param filename (str | None): Original uploaded filename for provenance.
      @param uploaded_by (str | None): User identifier of the uploader.
      @return (DecisionMatrix): Persisted and activated DecisionMatrix entity.
      @raises RuntimeError: If AI extraction fails.

    Example:
      >>> matrix = await create_matrix_from_upload(db, markdown=text, filename="matrix.md", uploaded_by="admin")
    """
    extracted = await get_ai_client().extract_decision_matrix(markdown)

    for old in (await db.execute(select(DecisionMatrix).where(DecisionMatrix.active))).scalars():
        old.active = False

    matrix = DecisionMatrix(
        name=extracted["name"],
        source_filename=filename,
        uploaded_by=uploaded_by,
        threshold=extracted["threshold"],
        active=True,
        categories=[
            DecisionCategory(
                headline=c["headline"],
                explanation=c.get("explanation"),
                weight=min(5, max(1, int(c.get("weight", 3)))),
                order=i,
            )
            for i, c in enumerate(extracted["categories"])
        ],
    )
    db.add(matrix)
    await db.flush()
    await _snapshot(db, matrix, change_summary=f"Uploaded from {filename or 'document'}", created_by=uploaded_by)
    await db.flush()
    return matrix


# ── Expert backend (edit + history) ─────────────────────────────────────────


async def update_matrix(
    db: AsyncSession,
    matrix: DecisionMatrix,
    *,
    name: str | None,
    threshold: int | None,
    change_summary: str | None,
    actor: str | None,
) -> DecisionMatrix:
    """Update top-level decision matrix configuration settings and record history.

    Validates that the specified point threshold is within bounds (0 to 5 * sum of weights),
    updates matrix attributes, generates a version snapshot, and flushes changes.

    Agent Metadata:
      @intent: Allow human experts to adjust global decision matrix parameters.
      @domain: Bidding/DecisionMatrix
      @capability: matrix:update_settings
      @keywords: update_matrix, threshold, max_points, version_snapshot
      @side_effects: db:mutate (updates matrix, inserts history snapshot, flushes)
      @idempotent: false
      @agent_notes: Validates threshold <= 5 * sum(weights).

    Contracts:
      @param db (AsyncSession): SQLAlchemy async session.
      @param matrix (DecisionMatrix): Target matrix entity.
      @param name (str | None): Optional new display name (truncated to 255 chars).
      @param threshold (int | None): Optional new threshold in weighted points.
      @param change_summary (str | None): Audit summary.
      @param actor (str | None): User modifying the settings.
      @return (DecisionMatrix): Updated matrix instance.
      @raises ValueError: If threshold is outside [0, max_points].

    Example:
      >>> updated = await update_matrix(db, matrix, name="2026 Public Matrix", threshold=48, change_summary="Raise threshold", actor="lead")
    """
    if threshold is not None:
        max_points = 5 * sum(c.weight for c in matrix.categories)
        if not 0 <= threshold <= max_points:
            raise ValueError(f"threshold must be between 0 and {max_points} (5 × Σ weights)")
        matrix.threshold = threshold
    if name:
        matrix.name = name[:255]
    await _snapshot(db, matrix, change_summary=change_summary or "Matrix settings updated", created_by=actor)
    await db.flush()
    return matrix


async def add_category(
    db: AsyncSession,
    matrix: DecisionMatrix,
    *,
    headline: str,
    explanation: str | None,
    weight: int,
    actor: str | None,
) -> DecisionCategory:
    """Append a new evaluation category criterion to the decision matrix.

    Validates that the weight is between 1 and 5 and headline is non-empty,
    creates the DecisionCategory with sequential ordering, appends it to the matrix,
    snapshots the version, and flushes to the database.

    Agent Metadata:
      @intent: Extend the decision matrix with an additional weighted evaluation category.
      @domain: Bidding/DecisionMatrix
      @capability: matrix:add_category
      @keywords: add_category, criterion, category_weight, headline, explanation
      @side_effects: db:mutate (appends category, inserts history snapshot, flushes)
      @idempotent: false
      @agent_notes: Weight must be in range 1-5; explanation grounds the AI scoring.

    Contracts:
      @param db (AsyncSession): Database session.
      @param matrix (DecisionMatrix): Active matrix to modify.
      @param headline (str): Name or title of the category.
      @param explanation (str | None): Narrative guidance for AI evaluation.
      @param weight (int): Category importance weight (1 to 5).
      @param actor (str | None): User creating the category.
      @return (DecisionCategory): Newly created category domain entity.
      @raises ValueError: If weight not in 1..5 or headline is whitespace.

    Example:
      >>> cat = await add_category(db, matrix, headline="ESG Compliance", explanation="Sustainability standards", weight=4, actor="lead")
    """
    if weight not in WEIGHT_RANGE:
        raise ValueError("weight must be between 1 and 5")
    if not headline.strip():
        raise ValueError("headline is required")
    cat = DecisionCategory(
        headline=headline.strip()[:255],
        explanation=(explanation or "").strip() or None,
        weight=weight,
        order=len(matrix.categories),
    )
    matrix.categories.append(cat)
    await _snapshot(db, matrix, change_summary=f"Added category '{cat.headline}'", created_by=actor)
    await db.flush()
    return cat


async def update_category(
    db: AsyncSession,
    matrix: DecisionMatrix,
    category_id: str,
    *,
    headline: str | None,
    explanation: str | None,
    weight: int | None,
    actor: str | None,
) -> DecisionCategory:
    """Modify an existing category on the active decision matrix.

    Updates headline, explanation, or weight for a category on the matrix,
    validates constraints, records a version snapshot, and flushes.

    Agent Metadata:
      @intent: Edit an existing evaluation category on the active matrix.
      @domain: Bidding/DecisionMatrix
      @capability: matrix:update_category
      @keywords: update_category, edit_criterion, weight_adjustment
      @side_effects: db:mutate (modifies category, inserts history snapshot, flushes)
      @idempotent: false
      @agent_notes: Raises LookupError if category_id does not belong to the matrix.

    Contracts:
      @param db (AsyncSession): SQLAlchemy async session.
      @param matrix (DecisionMatrix): The active matrix containing the category.
      @param category_id (str): Primary key of the category to modify.
      @param headline (str | None): Updated headline text.
      @param explanation (str | None): Updated guidance explanation.
      @param weight (int | None): Updated weight (1-5).
      @param actor (str | None): Editor user identifier.
      @return (DecisionCategory): The updated category instance.
      @raises LookupError: If category_id not found on the matrix.
      @raises ValueError: If weight is out of bounds or headline is empty string.

    Example:
      >>> cat = await update_category(db, matrix, cat_id, headline=None, explanation="Updated guidance", weight=5, actor="lead")
    """
    cat = next((c for c in matrix.categories if c.id == category_id), None)
    if not cat:
        raise LookupError("Category not found on the active matrix")
    if weight not in WEIGHT_RANGE if weight is not None else False:
        raise ValueError("weight must be between 1 and 5")
    if headline is not None:
        if not headline.strip():
            raise ValueError("headline cannot be empty")
        cat.headline = headline.strip()[:255]
    if weight is not None:
        cat.weight = weight
    if explanation is not None:
        cat.explanation = explanation.strip() or None
    await _snapshot(db, matrix, change_summary=f"Updated category '{cat.headline}'", created_by=actor)
    await db.flush()
    return cat


async def delete_category(db: AsyncSession, matrix: DecisionMatrix, category_id: str, *, actor: str | None) -> None:
    """Delete a category from the decision matrix and purge its associated ratings.

    Removes the specified category from the matrix, cascades deletion to all
    BidCategoryRating rows referencing it across all bids, creates a history snapshot,
    and flushes changes.

    Agent Metadata:
      @intent: Remove a retired evaluation category and clean up invalid orphan ratings.
      @domain: Bidding/DecisionMatrix
      @capability: matrix:delete_category
      @keywords: delete_category, cascade_delete, ratings_cleanup, matrix_edit
      @side_effects: db:mutate (deletes ratings, removes category, inserts history, flushes)
      @idempotent: false
      @agent_notes: Deletes BidCategoryRating rows matching category_id immediately via query.

    Contracts:
      @param db (AsyncSession): Database session.
      @param matrix (DecisionMatrix): The matrix containing the category.
      @param category_id (str): Category identifier to delete.
      @param actor (str | None): User performing the deletion.
      @return None: Mutates and flushes in-place.
      @raises LookupError: If category does not exist on the matrix.

    Example:
      >>> await delete_category(db, matrix, cat_id, actor="admin")
    """
    cat = next((c for c in matrix.categories if c.id == category_id), None)
    if not cat:
        raise LookupError("Category not found on the active matrix")
    # Ratings of a removed criterion are meaningless — drop them with it.
    await db.execute(delete(BidCategoryRating).where(BidCategoryRating.category_id == category_id))
    headline = cat.headline
    matrix.categories.remove(cat)
    await _snapshot(db, matrix, change_summary=f"Removed category '{headline}'", created_by=actor)
    await db.flush()


async def get_history(db: AsyncSession, matrix: DecisionMatrix, limit: int = 20) -> list[dict[str, Any]]:
    """Retrieve the audit revision log for a decision matrix.

    Queries DecisionMatrixHistory rows for the matrix ordered by version descending,
    returning structured version snapshots with change summaries and timestamps.

    Agent Metadata:
      @intent: Audit historical modifications, category changes, and threshold shifts on the matrix.
      @domain: Bidding/DecisionMatrix
      @capability: matrix:get_history
      @keywords: matrix_history, version_log, audit_trail, changelog
      @side_effects: none (pure query)
      @idempotent: true
      @agent_notes: Capped by limit parameter (default 20).

    Contracts:
      @param db (AsyncSession): SQLAlchemy async session.
      @param matrix (DecisionMatrix): DecisionMatrix entity.
      @param limit (int): Maximum history records to retrieve (default 20).
      @return (list[dict[str, Any]]): List of historical matrix snapshots.
      @raises SQLAlchemyError: If query fails.

    Example:
      >>> history = await get_history(db, matrix, limit=10)
    """
    rows = (
        (
            await db.execute(
                select(DecisionMatrixHistory)
                .where(DecisionMatrixHistory.matrix_id == matrix.id)
                .order_by(DecisionMatrixHistory.version.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "version": h.version,
            "change_summary": h.change_summary,
            "created_by": h.created_by,
            "created_at": h.created_at,
            "data": h.data,
        }
        for h in rows
    ]


# ── Per-bid evaluation ───────────────────────────────────────────────────────


def _bid_text(bid: Bid) -> str:
    """Concatenate full bid corpus text for AI category evaluation grounding.

    Gathers bid title, customer name, checklist item titles, and document filenames
    and markdown contents into a unified text corpus for AI evidence scoring.

    Agent Metadata:
      @intent: Assemble complete contextual textual evidence from a bid for AI evaluation.
      @domain: Bidding/DecisionMatrix
      @capability: util:assemble_bid_corpus
      @keywords: bid_text, corpus, evidence, text_assembly
      @side_effects: none (pure)
      @idempotent: true
      @agent_notes: Joins all elements with newline characters.

    Contracts:
      @param bid (Bid): Bid instance with checklist items and documents loaded.
      @return (str): Combined newline-delimited corpus string.
      @raises None: Pure function.

    Example:
      >>> corpus = _bid_text(bid)
    """
    parts = [bid.title, bid.customer or ""]
    parts += [i.title for i in bid.checklist_items]
    parts += [f"{d.filename} {d.markdown or ''}" for d in bid.documents]
    return "\n".join(parts)


async def evaluate_bid(db: AsyncSession, bid: Bid) -> dict[str, Any]:
    """AI-score every category of the active decision matrix for this bid.

    Gathers the bid corpus and competitor market intelligence from public portals,
    queries the AI client to evaluate each category (0–5) with an explanatory rationale,
    and upserts BidCategoryRating records. Human overrides are strictly preserved across
    re-evaluations — the AI only updates its own score and rationale proposals.

    Agent Metadata:
      @intent: Generate comprehensive AI readiness and strategic fit scoring across all matrix criteria.
      @domain: Bidding/DecisionMatrix
      @capability: matrix:evaluate_bid
      @keywords: evaluate_bid, ai_scoring, category_ratings, competitor_scan, portal_intel, overrides_safe
      @side_effects: db:mutate (upserts BidCategoryRating records, flushes)
      @idempotent: true
      @agent_notes: Flushes ratings to DB and returns the evaluated summary via get_evaluation.

    Contracts:
      @param db (AsyncSession): Active SQLAlchemy async database session.
      @param bid (Bid): The Bid instance to evaluate.
      @return (dict[str, Any]): Full evaluation report with verdict, scores, categories, and market intel.
      @raises LookupError: If no active decision matrix is configured.
      @raises RuntimeError: If AI evaluation fails.

    Example:
      >>> eval_report = await evaluate_bid(db, bid)
      >>> print(eval_report["verdict"], eval_report["total_points"])
    """
    matrix = await get_active_matrix(db)
    if not matrix:
        raise LookupError("No active decision matrix — upload one first.")

    intel = await get_portal_intel_client().competitor_scan(bid.customer, bid.cpv_codes)
    text = _bid_text(bid)

    existing = {
        r.category_id: r
        for r in (await db.execute(select(BidCategoryRating).where(BidCategoryRating.bid_id == bid.id))).scalars()
    }
    ai = get_ai_client()
    for cat in matrix.categories:
        result = await ai.score_category(
            {"headline": cat.headline, "explanation": cat.explanation, "weight": cat.weight}, text, intel
        )
        rating = existing.get(cat.id)
        if rating:
            rating.ai_score = result["score"]
            rating.ai_rationale = result["rationale"]
        else:
            db.add(
                BidCategoryRating(
                    bid_id=bid.id, category_id=cat.id, ai_score=result["score"], ai_rationale=result["rationale"]
                )
            )
    await db.flush()
    return await get_evaluation(db, bid, intel=intel)


async def override_rating(
    db: AsyncSession, bid: Bid, category_id: str, *, score: int | None, note: str | None, actor: str | None
) -> BidCategoryRating:
    """Set or clear a human-in-the-loop score override for a matrix category.

    Allows bid managers and leads to override the AI's proposed score (0-5) with a human score
    and explanatory note, or clear it by passing score=None. Upserts the rating row and
    records the authoring actor ID.

    Agent Metadata:
      @intent: Enable human governance and override of AI-proposed category scores.
      @domain: Bidding/DecisionMatrix
      @capability: matrix:override_rating
      @keywords: override_rating, human_in_the_loop, human_score, governance, audit
      @side_effects: db:mutate (upserts BidCategoryRating and flushes)
      @idempotent: true
      @agent_notes: Score must be 0-5 or None (to clear override). Flushes session.

    Contracts:
      @param db (AsyncSession): Active database session.
      @param bid (Bid): The Bid instance.
      @param category_id (str): Decision matrix category identifier.
      @param score (int | None): Human override score (0-5), or None to reset.
      @param note (str | None): Justification note for the override.
      @param actor (str | None): User identifier of the reviewer.
      @return (BidCategoryRating): Updated rating entity.
      @raises ValueError: If score is outside 0..5.

    Example:
      >>> rating = await override_rating(db, bid, cat_id, score=4, note="Strong relationship with buyer", actor="lead_1")
    """
    if score is not None and score not in SCORE_RANGE:
        raise ValueError("score must be between 0 and 5")
    rating = (
        await db.execute(
            select(BidCategoryRating).where(
                BidCategoryRating.bid_id == bid.id, BidCategoryRating.category_id == category_id
            )
        )
    ).scalar_one_or_none()
    if not rating:
        rating = BidCategoryRating(bid_id=bid.id, category_id=category_id)
        db.add(rating)
    rating.human_score = score
    rating.human_note = note
    rating.overridden_by = actor if score is not None else None
    await db.flush()
    return rating


async def get_evaluation(db: AsyncSession, bid: Bid, intel: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compile the complete decision matrix evaluation, weighted total, and bid/no-bid verdict.

    Combines the active matrix schema with the bid's saved category ratings. For each category,
    applies the human override score if present, otherwise the AI proposed score. Calculates
    total weighted points vs matrix threshold to render the strategic 'bid' or 'no_bid' verdict.

    Agent Metadata:
      @intent: Calculate the official weighted bid/no-bid verdict based on matrix rules and human overrides.
      @domain: Bidding/DecisionMatrix
      @capability: matrix:get_evaluation
      @keywords: evaluation, verdict, weighted_points, threshold, strategic_decision, overrides
      @side_effects: none (pure query)
      @idempotent: true
      @agent_notes: Effective score prioritizes human_score over ai_score.

    Contracts:
      @param db (AsyncSession): SQLAlchemy async session.
      @param bid (Bid): Bid instance to evaluate.
      @param intel (dict[str, Any] | None): Optional competitor intel context payload to embed.
      @return (dict[str, Any]): Full evaluation report including threshold, total_points, verdict, and categories.
      @raises LookupError: If no active decision matrix exists.

    Example:
      >>> eval_res = await get_evaluation(db, bid)
      >>> print(eval_res["verdict"])
    """
    matrix = await get_active_matrix(db)
    if not matrix:
        raise LookupError("No active decision matrix — upload one first.")

    ratings = {
        r.category_id: r
        for r in (await db.execute(select(BidCategoryRating).where(BidCategoryRating.bid_id == bid.id))).scalars()
    }

    rows: list[dict[str, Any]] = []
    total = 0
    scored_any = False
    for cat in matrix.categories:
        r = ratings.get(cat.id)
        effective = r.human_score if r and r.human_score is not None else (r.ai_score if r else None)
        if effective is not None:
            scored_any = True
            total += effective * cat.weight
        rows.append(
            {
                "category_id": cat.id,
                "headline": cat.headline,
                "explanation": cat.explanation,
                "weight": cat.weight,
                "ai_score": r.ai_score if r else None,
                "ai_rationale": r.ai_rationale if r else None,
                "human_score": r.human_score if r else None,
                "human_note": r.human_note if r else None,
                "overridden_by": r.overridden_by if r else None,
                "effective_score": effective,
                "weighted_points": (effective * cat.weight) if effective is not None else None,
            }
        )

    max_points = 5 * sum(c.weight for c in matrix.categories)
    return {
        "matrix_id": matrix.id,
        "matrix_name": matrix.name,
        "matrix_version": matrix.version,
        "threshold": matrix.threshold,
        "max_points": max_points,
        "total_points": total if scored_any else None,
        "verdict": (("bid" if total >= matrix.threshold else "no_bid") if scored_any else None),
        "evaluated": scored_any,
        "categories": rows,
        "market_intel": intel,
    }
