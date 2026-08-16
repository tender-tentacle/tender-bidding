import unittest
import urllib.parse

import requests


class TestCompanyDeepResearchNewsSmoke(unittest.TestCase):
    """
    Smoke test to verify that the Bidding MS deep research company news & newsroom/blog endpoints boot cleanly
    and process 'MHP Management- und IT-Beratung GmbH' using the deep research option.
    """

    BASE_URL = "http://localhost/ms/bidding"
    COMPANY_NAME = "MHP Management- und IT-Beratung GmbH"

    def test_company_deep_research_news_smoke(self):
        encoded_company = urllib.parse.quote(self.COMPANY_NAME)

        # 1. Health check assertion
        try:
            health_resp = requests.get(f"{self.BASE_URL}/health", timeout=5)
            self.assertEqual(health_resp.status_code, 200, "Bidding MS /health endpoint did not return 200")
        except Exception as e:
            self.skipTest(f"Local Docker stack not running or inaccessible at {self.BASE_URL}: {e}")

        # 2. POST Scrape & Deep Research News for MHP
        scrape_url = f"{self.BASE_URL}/api/v1/company/{encoded_company}/news/scrape"
        scrape_resp = requests.post(scrape_url, timeout=30)
        self.assertEqual(scrape_resp.status_code, 200, f"POST news scrape failed with status {scrape_resp.status_code}")

        data = scrape_resp.json()
        self.assertIsInstance(data, list, "Scraped company news response should be a list")

        # 3. GET Company News for MHP
        get_url = f"{self.BASE_URL}/api/v1/company/{encoded_company}/news"
        get_resp = requests.get(get_url, timeout=10)
        self.assertEqual(get_resp.status_code, 200, f"GET news failed with status {get_resp.status_code}")

        cached_data = get_resp.json()
        self.assertIsInstance(cached_data, list)

        # 4. Assert structure of news items (checking source_type: press or company_blog)
        if len(cached_data) > 0:
            first_item = cached_data[0]
            self.assertIn("title", first_item)
            self.assertIn("source_type", first_item)
            self.assertIn(first_item.get("source_type"), ["press", "company_blog", None])


if __name__ == "__main__":
    unittest.main()
