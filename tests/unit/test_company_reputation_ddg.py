import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from api.v1.company_reputation import get_company_reputation


class TestCompanyReputationDDG(unittest.IsolatedAsyncioTestCase):
    async def test_company_reputation_fetches_ddg_news_and_jobs(self):
        """Verify that get_company_reputation fetches and merges real news and jobs from DDG reputation scraper."""
        db_mock = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_mock.execute.return_value = mock_result
        db_mock.add = MagicMock()
        db_mock.commit = AsyncMock()

        mock_news = [
            {
                "scraped_at": "2026-08-04T12:00:00Z",
                "url": "https://news.example.com/1",
                "content": "Article 1",
                "type": "news",
            },
            {
                "scraped_at": "2026-08-04T12:00:00Z",
                "url": "https://news.example.com/2",
                "content": "Article 2",
                "type": "news",
            },
        ]
        mock_jobs = [
            {
                "scraped_at": "2026-08-04T12:00:00Z",
                "url": "https://jobs.example.com/1",
                "content": "Job 1",
                "type": "jobs",
            }
        ]

        async def mock_post(url, **kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            if "company-portals" in url:
                mock_resp.json.return_value = {
                    "data": {"portal_links": {"newsroom_url": "https://newsroom.example.com"}}
                }
            elif "reputation/ddg" in url:
                payload = kwargs.get("json", {})
                if payload.get("search_type") == "news":
                    mock_resp.json.return_value = mock_news
                else:
                    mock_resp.json.return_value = mock_jobs
            return mock_resp

        with patch("httpx.AsyncClient.post", side_effect=mock_post):
            res = await get_company_reputation("TestCorp", db_mock)

            self.assertIn("news", res)
            self.assertIn("jobs", res)
            # 1 discovered portal URL + 2 scraped news articles = 3 total news items
            self.assertEqual(len(res["news"]), 3)
            # 1 scraped job offer = 1 total job item
            self.assertEqual(len(res["jobs"]), 1)


if __name__ == "__main__":
    unittest.main()
