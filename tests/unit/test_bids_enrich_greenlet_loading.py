from unittest.mock import AsyncMock, MagicMock

import pytest
from services.bid_service import get_by_source_ref


@pytest.mark.asyncio
async def test_get_by_source_ref_includes_selectinload_options():
    """Verify get_by_source_ref includes eager loading options for all required Bid relationships."""
    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res

    await get_by_source_ref(mock_db, "test-source-ref")

    assert mock_db.execute.call_count == 1
    call_stmt = mock_db.execute.call_args[0][0]

    # Check that selectinload options are attached to the statement
    opts = call_stmt._with_options
    opt_names = [str(o.path) if hasattr(o, "path") else str(o) for o in opts]

    assert any("collaborators" in o for o in opt_names), (
        f"Missing selectinload(Bid.collaborators) in options: {opt_names}"
    )
    assert any("checklist_items" in o for o in opt_names), (
        f"Missing selectinload(Bid.checklist_items) in options: {opt_names}"
    )
    assert any("documents" in o for o in opt_names), f"Missing selectinload(Bid.documents) in options: {opt_names}"
    assert any("required_documents" in o for o in opt_names), (
        f"Missing selectinload(Bid.required_documents) in options: {opt_names}"
    )
    assert any("key_dates" in o for o in opt_names), f"Missing selectinload(Bid.key_dates) in options: {opt_names}"


@pytest.mark.asyncio
async def test_bids_api_load_and_get_by_source_include_checklist_items():
    """Verify _load and get_bid_by_source in api/v1/bids.py eagerly load checklist_items."""
    from api.v1.bids import _load, get_bid_by_source

    mock_db = AsyncMock()
    mock_res = MagicMock()
    from models.bid import Bid

    dummy_bid = Bid(
        id="test-bid-id",
        source_ref="test-source-ref",
        title="Test Bid",
        status="draft",
        version=1,
        source_kind="tender",
        matched_labels=[],
        matched_sectors=[],
        matched_services=[],
        matched_people=[],
        matched_campaigns=[],
        matched_trends=[],
        matched_practices=[],
        matched_clusters=[],
        matched_ressorts=[],
        matched_horizontals=[],
        classification_matches=[],
        checklist_items=[],
        collaborators=[],
        documents=[],
        required_documents=[],
        key_dates=[],
    )
    mock_res.scalar_one_or_none.return_value = dummy_bid
    mock_db.execute.return_value = mock_res

    # Test _load
    await _load(mock_db, "test-bid-id")
    stmt_load = mock_db.execute.call_args[0][0]
    opts_load = [str(o.path) if hasattr(o, "path") else str(o) for o in stmt_load._with_options]
    assert any("checklist_items" in o for o in opts_load), (
        f"_load missing selectinload(Bid.checklist_items): {opts_load}"
    )

    mock_db.reset_mock()
    mock_db.execute.return_value = mock_res

    # Test get_bid_by_source
    await get_bid_by_source("test-source-ref", mock_db)
    stmt_src = mock_db.execute.call_args[0][0]
    opts_src = [str(o.path) if hasattr(o, "path") else str(o) for o in stmt_src._with_options]
    assert any("checklist_items" in o for o in opts_src), (
        f"get_bid_by_source missing selectinload(Bid.checklist_items): {opts_src}"
    )


@pytest.mark.asyncio
async def test_bid_activity_model_allows_long_bid_ids():
    """Verify BidActivity model has String(255) capacity for 36-char UUID bid_ids."""
    from models.bid import BidActivity
    from services.activity import record

    # Check model column DDL length
    bid_id_col = BidActivity.__table__.columns["bid_id"]
    assert bid_id_col.type.length == 255, f"BidActivity.bid_id column length should be 255, got {bid_id_col.type.length}"

    # Test record helper with 36-character UUID string (group ID)
    group_uuid = "4ec81455-a590-48af-8c2f-e667135cca81"
    mock_db = MagicMock()
    record(mock_db, group_uuid, "test-actor", "bid.requirements_enriched", {"documents": 6})

    assert mock_db.add.call_count == 1
    added_obj = mock_db.add.call_args[0][0]
    assert isinstance(added_obj, BidActivity)
    assert added_obj.bid_id == group_uuid
    assert len(added_obj.bid_id) == 36



