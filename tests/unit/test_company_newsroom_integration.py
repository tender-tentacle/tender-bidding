import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from api.v1.company_news import get_company_news


class TestCompanyNewsroomIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_get_company_news_fetches_portal_links_and_crawls_newsroom(self):
        """Verify that get_company_news queries master-data for portal links and calls /api/v1/scrape/newsroom."""
        mock_db = AsyncMock()
        mock_exec_result = MagicMock()
        mock_exec_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_exec_result

        mock_master_data_resp = MagicMock()
        mock_master_data_resp.status_code = 200
        mock_master_data_resp.json.return_value = {
            "target_companies": [
                {
                    "id": "72049c98-78ca-4a46-b84d-016a94f5aa22",
                    "name": "Deutsche Gesellschaft für Internationale Zusammenarbeit (GIZ) GmbH",
                    "portal_links": {"newsroom": ["https://www.giz.de/en/newsroom"]},
                }
            ]
        }

        mock_scrape_resp = MagicMock()
        mock_scrape_resp.status_code = 200
        mock_scrape_resp.json.return_value = [
            {
                "hash": "abc123hash",
                "title": "GIZ Climate Action News",
                "link": "https://www.giz.de/en/news/climate",
                "content": "GIZ launches new climate initiative.",
                "category": "Newsroom",
                "published_at": "2026-07-24",
            }
        ]

        async def mock_get(*args, **kwargs):
            return mock_master_data_resp

        async def mock_post(*args, **kwargs):
            return mock_scrape_resp

        with (
            patch("httpx.AsyncClient.get", side_effect=mock_get),
            patch("httpx.AsyncClient.post", side_effect=mock_post),
        ):
            results = await get_company_news("72049c98-78ca-4a46-b84d-016a94f5aa22", mock_db)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].title, "GIZ Climate Action News")
            self.assertEqual(results[0].link, "https://www.giz.de/en/news/climate")


if __name__ == "__main__":
    unittest.main()
