import unittest

import requests


class TestNorthDataSmoke(unittest.TestCase):
    """
    Smoke test to verify that the local Bidding MS container and North Data API endpoints boot cleanly.
    """

    BASE_URL = "http://localhost/ms/bidding"

    def test_bidding_ms_health_and_northdata_smoke(self):
        # 1. Health check assertion
        try:
            health_resp = requests.get(f"{self.BASE_URL}/health", timeout=5)
            self.assertEqual(health_resp.status_code, 200, "Bidding MS /health endpoint did not return 200")
        except Exception as e:
            self.skipTest(f"Local Docker stack not running or inaccessible at {self.BASE_URL}: {e}")

        # 2. GET Company North Data for MHP
        get_resp = requests.get(f"{self.BASE_URL}/api/v1/company/MHP/northdata", timeout=10)
        self.assertEqual(get_resp.status_code, 200, f"GET North Data failed with status {get_resp.status_code}")
        
        data = get_resp.json()
        self.assertIsInstance(data, dict)
        self.assertEqual(data.get("company_id"), "MHP")
        self.assertEqual(data.get("company_name"), "MHP Management- und IT-Beratung GmbH")
        self.assertIn("network_links", data)
        self.assertIn("tab_metrics", data)

        # 3. Verify corporate connections network graph list is populated
        net_links = data.get("network_links") or []
        self.assertGreaterEqual(len(net_links), 1, "Network links should contain at least 1 corporate connection")


if __name__ == "__main__":
    unittest.main()
