"""Document upload/list. Original → Blob; markdown + metadata → SQL; AI verifies
the upload against its linked checklist requirement."""

from __future__ import annotations

from core.ai_client import get_ai_client
from core.blob_client import get_blob_client
from core.database import get_db
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from models.bid import DOCUMENT_KINDS, SENSITIVITIES, Bid, BidDocument, ChecklistItem
from schemas import DocumentOut
from services import activity
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/bids", tags=["documents"])


def _to_markdown(filename: str, data: bytes) -> str:
    """Best-effort markdown rendering for AI consumption (v1: decode text-like files)."""
    lower = filename.lower()
    if lower.endswith((".md", ".txt", ".csv")):
        try:
            return data.decode("utf-8", errors="ignore")
        except Exception:
            return ""
    # PDFs/DOCX would be converted by a real parser; v1 stores a placeholder note.
    return f"[binary document: {filename}] — text extraction deferred to a parser."


@router.post("/{bid_id}/documents", response_model=DocumentOut, status_code=201)
async def upload_document(
    bid_id: str,
    request: Request,
    file: UploadFile = File(...),
    kind: str = Form("supporting"),
    doc_type: str | None = Form(None),
    sensitivity: str = Form("normal"),
    checklist_item_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    bid = (await db.execute(select(Bid).where(Bid.id == bid_id))).scalar_one_or_none()
    if not bid:
        raise HTTPException(status_code=404, detail="Bid not found")
    if kind not in DOCUMENT_KINDS:
        raise HTTPException(status_code=400, detail=f"Invalid kind. Allowed: {DOCUMENT_KINDS}")
    if sensitivity not in SENSITIVITIES:
        raise HTTPException(status_code=400, detail=f"Invalid sensitivity. Allowed: {SENSITIVITIES}")

    data = await file.read()
    filename = file.filename or "upload.bin"
    blob_ref = await get_blob_client().upload(data, filename)
    markdown = _to_markdown(filename, data)

    # AI verification against the linked checklist requirement, if any.
    verification = None
    if checklist_item_id:
        item = (
            await db.execute(
                select(ChecklistItem).where(ChecklistItem.id == checklist_item_id, ChecklistItem.bid_id == bid_id)
            )
        ).scalar_one_or_none()
        if item:
            verification = await get_ai_client().verify_document(item.title, markdown)
            item.ai_verification = verification
            if verification.get("status") == "matched" and item.status == "open":
                item.status = "done"

    doc = BidDocument(
        bid_id=bid_id,
        checklist_item_id=checklist_item_id,
        kind=kind,
        sensitivity=sensitivity,
        doc_type=doc_type,
        filename=filename,
        uploaded_by=request.headers.get("X-User-ID"),
        blob_ref=blob_ref,
        markdown=markdown,
        ai_verification=verification,
    )
    db.add(doc)
    activity.record(
        db,
        bid_id,
        request.headers.get("X-User-ID"),
        "document.uploaded",
        {"filename": filename, "kind": kind, "sensitivity": sensitivity, "verification": verification},
    )
    await db.commit()
    await db.refresh(doc)
    return doc


@router.get("/{bid_id}/documents", response_model=list[DocumentOut])
async def list_documents(bid_id: str, db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(BidDocument).where(BidDocument.bid_id == bid_id))).scalars().all()
