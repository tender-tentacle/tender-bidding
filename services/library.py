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
    return _ROLE_SENSITIVITIES.get((role or "").lower(), {"normal"})


def _fingerprint(doc: BidDocument) -> str:
    payload = f"{(doc.filename or '').lower()}|{doc.markdown or ''}"
    return hashlib.sha1(payload.encode()).hexdigest()[:16]


def _snippet(markdown: str | None, limit: int = 240) -> str:
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
    """Search the corpus. Returns ranked, usage-annotated, sensitivity-filtered hits."""
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
