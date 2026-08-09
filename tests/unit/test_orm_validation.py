import pytest
from models.bid import Bid, KeyDate, RequiredDocument


def test_bid_orm_validation_happy_path():
    """Happy path: Bid instantiation with valid attributes."""
    b = Bid(
        source_ref="ext-12345", source_kind="tender", title="Test Tender Bid", customer="City of Berlin", status="draft"
    )
    assert b.source_ref == "ext-12345"
    assert b.source_kind == "tender"


def test_bid_orm_validation_boundary():
    """Boundary test: Bid source_kind at max length (20)."""
    max_kind = "k" * 20
    b = Bid(source_ref="ref-123", source_kind=max_kind)
    assert b.source_kind == max_kind


def test_bid_orm_validation_overflow():
    """Overflow test: Bid source_kind max length + 1 (21) fails fast with ValueError."""
    with pytest.raises(ValueError) as exc_info:
        Bid(source_ref="ref-123", source_kind="k" * 21)
    assert "String length (21) exceeds maximum allowed column length (20)" in str(exc_info.value)


def test_required_document_category_overflow():
    """RequiredDocument category validation (100)."""
    req_doc = RequiredDocument(bid_id="bid-1", document_name="Certificate", category="Certificates")
    assert req_doc.category == "Certificates"

    with pytest.raises(ValueError):
        RequiredDocument(bid_id="bid-1", document_name="Certificate", category="c" * 101)


def test_key_date_kind_overflow():
    """KeyDate kind validation (20)."""
    kd = KeyDate(bid_id="bid-1", kind="submission")
    assert kd.kind == "submission"

    with pytest.raises(ValueError):
        KeyDate(bid_id="bid-1", kind="k" * 21)
