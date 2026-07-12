"""Document Library (US-101): search the cross-bid corpus.

Identity comes from the gateway: nginx `auth_request` verifies the session and
forwards X-User-ID / X-User-Role. Sensitivity filtering happens in-app (never
trust the gateway alone), defaulting to least privilege when headers are absent.
"""

from __future__ import annotations

from core.database import get_db
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from models.bid import DOCUMENT_KINDS
from services.library import search_documents
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/library", tags=["library"])


@router.get("/search")
async def search_library(
    request: Request,
    q: str | None = Query(None, description="Topic — full-text + semantic"),
    kind: str | None = Query(None, description=f"Document kind, one of {DOCUMENT_KINDS}"),
    client: str | None = Query(None, description="Client/customer name (substring)"),
    cpv: str | None = Query(None, description="CPV code of the owning bid's tender"),
    limit: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    if kind and kind not in DOCUMENT_KINDS:
        raise HTTPException(status_code=400, detail=f"Invalid kind. Allowed: {DOCUMENT_KINDS}")
    return await search_documents(
        db,
        q=q,
        kind=kind,
        client=client,
        cpv=cpv,
        role=request.headers.get("X-User-Role"),
        user_id=request.headers.get("X-User-ID"),
        limit=limit,
    )
