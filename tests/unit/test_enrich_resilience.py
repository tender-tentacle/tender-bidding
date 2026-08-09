from unittest.mock import AsyncMock

import pytest
from api.v1.bids import (
    _create_key_dates,
    _create_required_documents,
    _resolve_attachment_links,
)


@pytest.mark.asyncio
async def test_create_required_documents_handles_missing_and_duplicate_ids():
    """Verify that documents without explicit 'id' fields get unique primary keys and don't collide."""
    mock_db = AsyncMock()
    added_docs = []
    mock_db.add = lambda doc: added_docs.append(doc)

    bid_id = "test_bid_123"
    docs_payload = [
        {"document_name": "Doc A", "category": "suitability"},
        {"document_name": "Doc B", "category": "suitability"},  # No 'id' field, same as Doc A
        {"id": "same_id", "document_name": "Doc C"},
        {"id": "same_id", "document_name": "Doc D"},  # Duplicate 'id' field
    ]
    attachments = ["string_attachment_not_dict"]  # Non-dict attachment entry

    _create_required_documents(mock_db, docs_payload, attachments, bid_id)

    assert len(added_docs) == 4
    # All primary keys must be distinct to prevent DB IntegrityError 500
    doc_ids = [d.id for d in added_docs]
    assert len(set(doc_ids)) == 4, f"Primary key collision detected: {doc_ids}"

def test_resolve_attachment_links_handles_non_dict_attachments():
    """Verify that string or non-dict items in attachments list don't crash with AttributeError."""
    attachments = ["http://example.com/doc.pdf", None, 123, {"title": "Valid.pdf", "url": "http://example.com/valid.pdf"}]
    
    # Should not raise AttributeError: 'str' object has no attribute 'get'
    link_orig, link_parsed = _resolve_attachment_links("Valid.pdf", attachments)
    assert link_orig == "http://example.com/valid.pdf"

def test_create_key_dates_handles_non_dict_payload():
    """Verify that non-dict items in deadlines_payload don't crash."""
    mock_db = AsyncMock()
    deadlines = ["2026-12-31", None, {"kind": "submission", "date": "2026-12-31T23:59:59Z"}]
    
    _create_key_dates(mock_db, deadlines, "bid_123")
    assert mock_db.add.call_count == 1
