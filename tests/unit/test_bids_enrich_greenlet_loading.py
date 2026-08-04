import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.orm import selectinload
from services.bid_service import get_by_source_ref
from models.bid import Bid

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
    
    assert any("collaborators" in o for o in opt_names), f"Missing selectinload(Bid.collaborators) in options: {opt_names}"
    assert any("documents" in o for o in opt_names), f"Missing selectinload(Bid.documents) in options: {opt_names}"
    assert any("required_documents" in o for o in opt_names), f"Missing selectinload(Bid.required_documents) in options: {opt_names}"
    assert any("key_dates" in o for o in opt_names), f"Missing selectinload(Bid.key_dates) in options: {opt_names}"
