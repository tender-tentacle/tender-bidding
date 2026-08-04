from datetime import UTC
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from api.v1.company_profile import CompanyProfile
from core.database import SessionLocal
from httpx import ASGITransport, AsyncClient
from main import app


@pytest.mark.asyncio
async def test_get_company_profile_happy_path():
    company_id = "test-company"
    from datetime import datetime
    
    # Insert some mock data to ensure the profile endpoint finds something
    async with SessionLocal() as db_session:
        db_session.add(CompanyProfile(company_id=company_id, description="A test company", crawled_date=datetime.now(UTC).replace(tzinfo=None)))
        await db_session.commit()

    class MockResponse:
        def __init__(self, json_data, status_code=200):
            self.json_data = json_data
            self.status_code = status_code
        def json(self):
            return self.json_data
        def raise_for_status(self):
            pass

    async def mock_post(*args, **kwargs):
        return MockResponse({"description": "From Mock", "logo_url": "test.png"})

    transport = ASGITransport(app=app)
    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=mock_post)):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/company/{company_id}/profile")
            
            assert response.status_code == 200
            data = response.json()
            assert data["company_id"] == company_id

@pytest.mark.asyncio
async def test_generate_summary_happy_path():
    company_id = "test-company"
    
    # Mock AI Client
    class MockAIClient:
        async def extract_company_summary(self, *args, **kwargs):
            return {
                "summary": "AI generated summary here.",
                "is_sufficient_data": True
            }

    transport = ASGITransport(app=app)
    with patch("core.ai_client.get_ai_client", return_value=MockAIClient()):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                f"/api/v1/company/{company_id}/summarize/hiring",
                json={}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["hiring_summary"] == "AI generated summary here."

@pytest.mark.asyncio
async def test_generate_summary_invalid_type():
    company_id = "test-company"
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            f"/api/v1/company/{company_id}/summarize/invalid_type",
            json={}
        )
        
        assert response.status_code == 400
        assert "Invalid summary type" in response.text

@pytest.mark.asyncio
async def test_generate_summary_ai_failure():
    company_id = "test-company"
    
    class MockAIClient:
        async def extract_company_summary(self, *args, **kwargs):
            raise Exception("AI is down")

    transport = ASGITransport(app=app)
    with patch("core.ai_client.get_ai_client", return_value=MockAIClient()):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                f"/api/v1/company/{company_id}/summarize/financial",
                json={}
            )
            
            # Application handles errors and returns 502
            assert response.status_code == 502
            assert "Failed to generate AI summary" in response.text

@pytest.mark.asyncio
async def test_evaluate_historic_tenders_happy_path():
    company_id = "Deutsche Gesellschaft für Internationale Zusammenarbeit (GIZ)"
    
    # Mock AI Client
    class MockAIClient:
        async def evaluate_historic_competition(self, historic_tenders, company_id):
            return {
                "incumbent_advantage_summary": "Low advantage",
                "competitor_density_summary": "High density"
            }

    class MockResponse:
        def __init__(self, json_data, status_code=200):
            self.json_data = json_data
            self.status_code = status_code
            self.text = "Mocked Response"
        def json(self):
            return self.json_data

    original_post = httpx.AsyncClient.post

    async def mock_post(self_client, url, *args, **kwargs):
        if "scrape" in str(url) or "ted" in str(url) or "8001" in str(url):
            return MockResponse([
                {"title": "Test Tender 1", "url": "http://example.com/1", "description": "Desc 1", "published_at": "2023-01-01"},
                {"title": "Test Tender 2", "url": "http://example.com/2", "description": "Desc 2", "published_at": "2023-01-02"},
            ])
        return await original_post(self_client, url, *args, **kwargs)

    transport = ASGITransport(app=app)
    with patch("core.ai_client.get_ai_client", return_value=MockAIClient()):
        with patch.object(httpx.AsyncClient, "post", new=mock_post):
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.post(
                    f"/api/v1/company/{company_id}/historic-tenders"
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["incumbent_advantage_summary"] == "Low advantage"
                assert data["competitor_density_summary"] == "High density"
