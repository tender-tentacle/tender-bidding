"""Unit tests: mock AI checklist split, verification, portal mapping."""

import pytest
from core.ai_client import AWARD, FORMAL, SUITABILITY, MockAIClient
from services.portal_guide import portal_key_for


@pytest.mark.asyncio
async def test_checklist_split_by_criterion_kind():
    ai = MockAIClient()
    items = await ai.generate_checklist({"source_ref": "X", "document_text": "cloud services"})
    kinds = {i["criterion_kind"] for i in items}
    assert kinds == {FORMAL, SUITABILITY, AWARD}
    # Formal items exist (they drive the pre-flight gate) and are ordered.
    assert any(i["criterion_kind"] == FORMAL for i in items)
    assert [i["order"] for i in items] == list(range(len(items)))


@pytest.mark.asyncio
async def test_consortium_item_only_when_hinted():
    ai = MockAIClient()
    without = await ai.generate_checklist({"source_ref": "X", "document_text": "simple service"})
    assert not any(i["requirement_type"] == "commitment_declaration" for i in without)
    with_ = await ai.generate_checklist({"source_ref": "X", "document_text": "Bietergemeinschaft mit Nachunternehmer"})
    assert any(i["requirement_type"] == "commitment_declaration" for i in with_)


@pytest.mark.asyncio
async def test_verify_document_matched_vs_gap():
    ai = MockAIClient()
    matched = await ai.verify_document("Personnel concept with CVs", "Here are the CVs and personnel qualifications.")
    assert matched["status"] == "matched"
    gap = await ai.verify_document("Personnel concept with CVs", "Unrelated invoice text.")
    assert gap["status"] == "gap"
    empty = await ai.verify_document("Anything", "")
    assert empty["status"] == "needs_review"


def test_portal_key_mapping():
    assert portal_key_for("Öffentliche Vergabe") == "oeffentliche-vergabe"
    assert portal_key_for("TED Europe") == "ted-europe"
    assert portal_key_for("DTVP") == "dtvp"
    assert portal_key_for("unknown-portal") is None
