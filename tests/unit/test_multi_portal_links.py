import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from api.v1.company_reputation import get_company_reputation


class TestMultiPortalLinks(unittest.IsolatedAsyncioTestCase):
    async def test_company_reputation_handles_list_of_urls(self):
        """Verify that company reputation service accepts arrays of URLs in portal_links."""
        db_mock = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_mock.execute.return_value = mock_result

        mock_portal_data = {
            "data": {
                "portal_links": {
                    "newsroom_url": [
                        "https://newsroom.giz.de/primary",
                        "https://newsroom.giz.de/secondary"
                    ],
                    "kununu_url": ["https://kununu.com/de/giz"]
                }
            }
        }

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_portal_data
            mock_post.return_value = mock_resp

            res = await get_company_reputation("GIZ GmbH", db_mock)

            self.assertIn("news", res)
            news_entries = res["news"]
            self.assertEqual(len(news_entries), 2)
            self.assertEqual(news_entries[0]["url"], "https://newsroom.giz.de/primary")
            self.assertEqual(news_entries[1]["url"], "https://newsroom.giz.de/secondary")


if __name__ == "__main__":
    unittest.main()
