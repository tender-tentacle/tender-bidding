import json
import os
import unittest


class TestNorthDataPactContract(unittest.TestCase):
    """
    Pact contract verification test for Bidding MS North Data endpoints.
    """

    def setUp(self):
        self.pact_file_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "pacts", "userdashboard-biddingms-northdata.json"
        )

    def test_pact_json_validity(self):
        self.assertTrue(os.path.exists(self.pact_file_path), f"Pact file not found: {self.pact_file_path}")
        with open(self.pact_file_path, "r", encoding="utf-8") as f:
            pact_data = json.load(f)

        self.assertEqual(pact_data.get("consumer", {}).get("name"), "UserDashboard")
        self.assertEqual(pact_data.get("provider", {}).get("name"), "BiddingMS")
        self.assertEqual(len(pact_data.get("interactions", [])), 2)

        # Interaction 1: GET /api/v1/company/MHP/northdata
        get_interaction = pact_data["interactions"][0]
        self.assertEqual(get_interaction["request"]["method"], "GET")
        self.assertEqual(get_interaction["request"]["path"], "/api/v1/company/MHP/northdata")
        self.assertEqual(get_interaction["response"]["status"], 200)

        body = get_interaction["response"]["body"]
        self.assertEqual(body["company_id"], "MHP")
        self.assertEqual(body["company_name"], "MHP Management- und IT-Beratung GmbH")
        self.assertIn("network_links", body)
        self.assertIn("balance_sheet", body)
        self.assertIn("financials", body)

        # Interaction 2: POST /api/v1/company/MHP/northdata/scrape
        post_interaction = pact_data["interactions"][1]
        self.assertEqual(post_interaction["request"]["method"], "POST")
        self.assertEqual(post_interaction["request"]["path"], "/api/v1/company/MHP/northdata/scrape")
        self.assertEqual(post_interaction["response"]["status"], 200)


if __name__ == "__main__":
    unittest.main()
