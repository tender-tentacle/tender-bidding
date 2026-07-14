"""Unit tests for Required Documents and Application Deadlines AI extraction."""

import pytest
from core.ai_client import MockAIClient


@pytest.mark.asyncio
async def test_extract_required_documents():
    ai = MockAIClient()
    docs = await ai.extract_required_documents({"title": "Test Tender"})
    assert len(docs) > 0
    for d in docs:
        assert "id" in d and d["id"] is not None and d["id"] != ""
    categories = {d["category"] for d in docs}
    assert "suitability" in categories
    assert "self-declaration" in categories
    assert "proposal" in categories
    assert any(d["document_name"] == "Handelsregisterauszug" for d in docs)
    # Check that CVs are precise sub-elements
    cv_docs = [d for d in docs if "cv" in d["document_name"].lower() or "lebenslauf" in d["document_name"].lower()]
    assert len(cv_docs) >= 3  # E.g. Project Lead CV, Senior Dev 1 CV, Senior Dev 2 CV
    # Check for three sub-elements of Referenzen
    ref_docs = [d for d in docs if "referenz" in d["document_name"].lower()]
    assert len(ref_docs) >= 3



@pytest.mark.asyncio
async def test_extract_bidding_deadlines_fallback():
    ai = MockAIClient()
    deadlines = await ai.extract_bidding_deadlines({})
    assert len(deadlines) == 4
    kinds = {d["kind"] for d in deadlines}
    assert kinds == {"submission", "questions", "registration", "validity"}


@pytest.mark.asyncio
async def test_extract_bidding_deadlines_from_snapshot():
    ai = MockAIClient()
    snapshot = {"deadline_at": "2026-09-30T12:00:00Z", "questions_deadline_at": "2026-09-15T18:00:00Z"}
    deadlines = await ai.extract_bidding_deadlines(snapshot)
    sub = next(d for d in deadlines if d["kind"] == "submission")
    q = next(d for d in deadlines if d["kind"] == "questions")

    assert sub["date"] == "2026-09-30T12:00:00Z"
    assert q["date"] == "2026-09-15T18:00:00Z"
