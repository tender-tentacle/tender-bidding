"""Cross-bid document library (US-101).

Search every document ever uploaded to any bid — by topic (full-text +
semantic), document kind, client, and CPV code — so a new bid package is
assembled from proven assets instead of starting from zero.

Sensitivity is enforced from the IAM role the gateway forwards:
  - normal   → every authenticated user
  - personal → bid collaborators/leads and admins ("member"/"lead"/"admin")
  - special  → GDPR special category (CVs, court docs): admins and the uploader

Each result groups identical files (same name + content) across bids and lists
every bid that used them — including whether that bid was WON, which is the
strongest possible signal that an asset is proven.
"""

from __future__ import annotations

import hashlib
from typing import Any

from core.ai_client import get_ai_client
from models.bid import Bid, BidDocument
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Role → visible sensitivity levels. Unknown/absent role = least privilege.
_ROLE_SENSITIVITIES = {
    "admin": {"normal", "personal", "special"},
    "lead": {"normal", "personal"},
    "member": {"normal", "personal"},
}


def visible_sensitivities(role: str | None) -> set[str]:
    """Calculate the permitted document sensitivity clearance levels for a given user IAM role.

    Evaluates RBAC role mappings ('admin', 'lead', 'member') against document sensitivity
    tiers ('normal', 'personal', 'special'). Follows least-privilege security defaults by
    falling back to {'normal'} for unknown or omitted roles.

    Agent Metadata:
      @intent: Enforce strict role-based access control (RBAC) and GDPR sensitivity boundaries on document search.
      @domain: Bidding/DocumentLibrary
      @capability: auth:determine_sensitivity
      @keywords: rbac, sensitivity, access_control, gdpr, clearance, least_privilege
      @side_effects: none (pure)
      @idempotent: true
      @agent_notes: Admins see special/personal/normal; leads/members see personal/normal; others see only normal.

    Contracts:
      @param role (str | None): User's authenticated role identifier from gateway headers.
      @return (set[str]): Set of allowable sensitivity string tags.
      @raises None: Pure function.

    Example:
      >>> levels = visible_sensitivities("member")
      >>> assert levels == {"normal", "personal"}
    """
    return _ROLE_SENSITIVITIES.get((role or "").lower(), {"normal"})


def _fingerprint(doc: BidDocument) -> str:
    """Generate a 16-character content fingerprint hash for a document.

    Hashes the normalized lower-case filename combined with the raw markdown text
    using SHA-1 to deduplicate identical files across multiple bids in search results.

    Agent Metadata:
      @intent: Deduplicate and group identical document assets across different bids.
      @domain: Bidding/DocumentLibrary
      @capability: util:document_fingerprint
      @keywords: fingerprint, sha1, hash, deduplication, content_identity
      @side_effects: none (pure)
      @idempotent: true
      @agent_notes: Truncates SHA-1 hex digest to 16 characters.

    Contracts:
      @param doc (BidDocument): The document entity to fingerprint.
      @return (str): 16-character hexadecimal fingerprint.
      @raises None: Pure function.

    Example:
      >>> fp = _fingerprint(doc)
      >>> len(fp)
      16
    """
    payload = f"{(doc.filename or '').lower()}|{doc.markdown or ''}"
    return hashlib.sha1(payload.encode()).hexdigest()[:16]


def _snippet(markdown: str | None, limit: int = 240) -> str:
    """Generate a clean whitespace-collapsed preview snippet of markdown text.

    Collapses consecutive whitespace sequences and truncates the string to the
    configured character limit, appending an ellipsis ('…') if truncated.

    Agent Metadata:
      @intent: Produce compact, readable previews of document content for search hit lists.
      @domain: Bidding/DocumentLibrary
      @capability: util:snippet_generation
      @keywords: snippet, preview, truncate, text_normalization
      @side_effects: none (pure)
      @idempotent: true
      @agent_notes: Appends '…' only if length strictly exceeds limit.

    Contracts:
      @param markdown (str | None): Raw markdown content.
      @param limit (int): Maximum character length before truncation (default 240).
      @return (str): Collapsed and truncated preview snippet.
      @raises None: Pure function.

    Example:
      >>> snip = _snippet("## Heading\n\nLong paragraph text...", limit=50)
    """
    text = " ".join((markdown or "").split())
    return text[:limit] + ("…" if len(text) > limit else "")


async def search_documents(
    db: AsyncSession,
    *,
    q: str | None = None,
    kind: str | None = None,
    client: str | None = None,
    cpv: str | None = None,
    role: str | None = None,
    user_id: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    """Search and rank the cross-bid document repository with sensitivity filtering and usage history.

    Queries all documents uploaded across any historical or active bids. Filters hits
    by sensitivity clearance, document kind, target customer/client, and CPV procurement codes.
    When a topic query string 'q' is provided, ranks results using hybrid scoring combining
    full-text exact matches and AI semantic embeddings. Identical documents across multiple
    bids are grouped by content fingerprint, tracking usage history and highlighting whether
    they were used in bids that were WON ('proven' assets).

    Agent Metadata:
      @intent: Discover and reuse high-performing, winning bid assets across organizational silos.
      @domain: Bidding/DocumentLibrary
      @capability: search:cross_bid_documents
      @keywords: document_library, cross_bid_reuse, semantic_search, proven_assets, rbac_filtering
      @side_effects: network:outbound (when semantic scoring queries AI connector)
      @idempotent: true
      @agent_notes: Sensitivity gate ensures users only see files within their clearance or uploaded by themselves.

    Contracts:
      @param db (AsyncSession): Active SQLAlchemy async session.
      @param q (str | None): Optional search query for hybrid lexical/semantic ranking.
      @param kind (str | None): Optional document category filter (e.g. 'reference', 'profile').
      @param client (str | None): Optional buyer or customer name substring filter.
      @param cpv (str | None): Optional CPV code filter matching bid cpv_codes.
      @param role (str | None): User's authenticated IAM role (determines sensitivity visibility).
      @param user_id (str | None): User ID of the searching user (uploader override for sensitivity).
      @param limit (int): Maximum grouped search results to return (default 25).
      @return (dict[str, Any]): Dictionary with 'results' list, 'total' count, and 'visible_sensitivities'.
      @raises SQLAlchemyError: If query execution fails.

    Example:
      >>> search_res = await search_documents(db, q="cloud migration", role="lead", limit=10)
      >>> print(search_res["results"][0]["proven"])
    """
    rows = (
        await db.execute(
            select(BidDocument, Bid).join(Bid, BidDocument.bid_id == Bid.id).order_by(BidDocument.created_at.desc())
        )
    ).all()

    allowed = visible_sensitivities(role)
    candidates: list[tuple[BidDocument, Bid]] = []
    for doc, bid in rows:
        # Sensitivity gate (uploader always sees their own documents).
        if doc.sensitivity not in allowed and not (user_id and doc.uploaded_by == user_id):
            continue
        if kind and doc.kind != kind:
            continue
        if client and client.lower() not in (bid.customer or "").lower():
            continue
        if cpv and cpv not in (bid.cpv_codes or []):
            continue
        candidates.append((doc, bid))

    # Rank by relevance when a topic is given: full-text hit + semantic score.
    if q:
        texts = [f"{d.filename} {d.doc_type or ''} {d.markdown or ''}" for d, _ in candidates]
        semantic = await get_ai_client().semantic_scores(q, texts)
        ranked = []
        for (doc, bid), sem in zip(candidates, semantic, strict=True):
            fulltext = 1.0 if q.lower() in (doc.markdown or "").lower() or q.lower() in doc.filename.lower() else 0.0
            score = round(0.5 * fulltext + 0.5 * sem, 3)
            if score > 0:
                ranked.append((score, doc, bid))
        ranked.sort(key=lambda t: t[0], reverse=True)
    else:
        ranked = [(0.0, doc, bid) for doc, bid in candidates]

    # Group identical files used across several bids into one result with usages.
    grouped: dict[str, dict[str, Any]] = {}
    for score, doc, bid in ranked:
        fp = _fingerprint(doc)
        usage = {
            "bid_id": bid.id,
            "bid_title": bid.title,
            "bid_status": bid.status,
            "won": bid.status == "won",
            "customer": bid.customer,
            "cpv_codes": bid.cpv_codes or [],
        }
        if fp in grouped:
            grouped[fp]["usages"].append(usage)
            grouped[fp]["score"] = max(grouped[fp]["score"], score)
        else:
            grouped[fp] = {
                "fingerprint": fp,
                "document_id": doc.id,
                "filename": doc.filename,
                "kind": doc.kind,
                "sensitivity": doc.sensitivity,
                "doc_type": doc.doc_type,
                "snippet": _snippet(doc.markdown),
                "score": score,
                "usages": [usage],
            }

    results = sorted(grouped.values(), key=lambda r: r["score"], reverse=True)[:limit]
    for r in results:
        r["proven"] = any(u["won"] for u in r["usages"])
    return {"results": results, "total": len(grouped), "visible_sensitivities": sorted(allowed)}
