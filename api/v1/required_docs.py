from datetime import datetime
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from core.ai_client import get_ai_client
from core.blob_client import get_blob_client
from core.database import get_db
from models.bid import Bid, RequiredDocument
from schemas import RequiredDocumentOut
from services import activity
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

router = APIRouter(prefix="/bids", tags=["required-documents"])

class RequiredDocOverrideIn(BaseModel):
    status: str

def _to_markdown(filename: str, data: bytes) -> str:
    lower = filename.lower()
    if lower.endswith((".md", ".txt", ".csv")):
        try:
            return data.decode("utf-8", errors="ignore")
        except Exception:
            return ""
    return f"[binary document: {filename}] — text extraction deferred to a parser."

@router.post("/{bid_id}/required-documents/{rd_id}/upload", response_model=RequiredDocumentOut, status_code=201)
async def upload_required_document(
    bid_id: str,
    rd_id: str,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    bid = (await db.execute(select(Bid).where(Bid.id == bid_id))).scalar_one_or_none()
    if not bid:
        raise HTTPException(status_code=404, detail="Bid not found")
    
    rd = (await db.execute(select(RequiredDocument).where(RequiredDocument.id == rd_id, RequiredDocument.bid_id == bid_id))).scalar_one_or_none()
    if not rd:
        raise HTTPException(status_code=404, detail="Required Document not found")
        
    data = await file.read()
    filename = file.filename or "upload.bin"
    
    # Store blob reference
    blob_ref = await get_blob_client().upload(data, filename)
    markdown = _to_markdown(filename, data)
    
    # Analyze alignment against description/short_summary using verify_document
    target_text = rd.description or rd.short_summary or rd.document_name
    verification = await get_ai_client().verify_document(target_text, markdown)
    
    from datetime import UTC
    rd.status = "done" if verification.get("status") == "matched" else "gap"
    rd.uploaded_by = request.headers.get("X-User-ID") or "anonymous"
    rd.uploaded_at = datetime.now(UTC)
    rd.uploaded_filename = filename
    rd.link_original_doc = f"/ms/dashboard/mock-documents/{filename}"
    rd.link_parsed_doc = f"/ms/dashboard/mock-documents/{filename}?parsed=true"
    rd.user_override = False # Reset user override on new uploads
    
    activity.record(
        db,
        bid_id,
        rd.uploaded_by,
        "required_document.uploaded",
        {"rd_id": rd.id, "filename": filename, "verification": verification}
    )
    await db.commit()
    await db.refresh(rd)
    return rd

@router.post("/{bid_id}/required-documents/{rd_id}/override", response_model=RequiredDocumentOut)
async def override_required_document_status(
    bid_id: str,
    rd_id: str,
    body: RequiredDocOverrideIn,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    bid = (await db.execute(select(Bid).where(Bid.id == bid_id))).scalar_one_or_none()
    if not bid:
        raise HTTPException(status_code=404, detail="Bid not found")
        
    rd = (await db.execute(select(RequiredDocument).where(RequiredDocument.id == rd_id, RequiredDocument.bid_id == bid_id))).scalar_one_or_none()
    if not rd:
        raise HTTPException(status_code=404, detail="Required Document not found")
        
    if body.status not in ("open", "done", "needs_review", "gap"):
        raise HTTPException(status_code=400, detail="Invalid status")
        
    rd.status = body.status
    rd.user_override = True
    
    actor = request.headers.get("X-User-ID") or "anonymous"
    activity.record(
        db,
        bid_id,
        actor,
        "required_document.override",
        {"rd_id": rd.id, "status": body.status}
    )
    await db.commit()
    await db.refresh(rd)
    return rd
