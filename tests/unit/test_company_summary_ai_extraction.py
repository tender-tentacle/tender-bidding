from unittest.mock import AsyncMock, patch

import pytest
from core.ai_client import RealAIClient


@pytest.mark.asyncio
async def test_extract_company_summary_success():
    client = RealAIClient()
    
    class MockResponse:
        def __init__(self, json_data, status_code=200):
            self.json_data = json_data
            self.status_code = status_code
        def json(self):
            return self.json_data
        
    async def mock_post(*args, **kwargs):
        return MockResponse({"status": "success", "data": {
            "summary": "Great financial performance.",
            "is_sufficient_data": True
        }})
    
    # We patch _sync_prompt to avoid DB access
    with patch("core.ai_client._sync_prompt", new=AsyncMock()):
        with patch("core.ai_client._configured_prompt", new=AsyncMock(return_value="test")):
            with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=mock_post)):
                result = await client.extract_company_summary("financial", {"data": "test company data"})
                assert result["summary"] == "Great financial performance."
                assert result["is_sufficient_data"] is True

@pytest.mark.asyncio
async def test_extract_company_summary_insufficient_data():
    client = RealAIClient()
    
    class MockResponse:
        def __init__(self, json_data, status_code=200):
            self.json_data = json_data
            self.status_code = status_code
        def json(self):
            return self.json_data
            
    async def mock_post(*args, **kwargs):
        return MockResponse({"status": "success", "data": {
            "summary": "Not enough info.",
            "is_sufficient_data": False
        }})
    
    with patch("core.ai_client._sync_prompt", new=AsyncMock()):
        with patch("core.ai_client._configured_prompt", new=AsyncMock(return_value="test")):
            with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=mock_post)):
                result = await client.extract_company_summary("hiring", {"data": "test"})
                assert result["is_sufficient_data"] is False
                assert "Not enough info" in result["summary"]
