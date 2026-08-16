import json
import os
import unittest


class TestBiddingAiSentimentPactContract(unittest.TestCase):
    """
    Pact contract verification test for Bidding MS calling AI Connector /api/v1/sentiment/batch-score endpoint.
    """

    def setUp(self):
        self.pact_file_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "pacts", "biddingms-aims-sentiment.json"
        )

    def test_pact_json_validity(self):
        self.assertTrue(os.path.exists(self.pact_file_path), f"Pact file not found: {self.pact_file_path}")
        with open(self.pact_file_path, encoding="utf-8") as f:
            pact_data = json.load(f)

        self.assertEqual(pact_data.get("consumer", {}).get("name"), "BiddingMS")
        self.assertEqual(pact_data.get("provider", {}).get("name"), "AIMS")
        self.assertEqual(len(pact_data.get("interactions", [])), 1)

        interaction = pact_data["interactions"][0]
        self.assertEqual(interaction["request"]["method"], "POST")
        self.assertEqual(interaction["request"]["path"], "/api/v1/sentiment/batch-score")
        self.assertEqual(interaction["response"]["status"], 200)

        req_body = interaction["request"]["body"]
        self.assertIn("company_name", req_body)
        self.assertIn("prompt_template", req_body)
        self.assertIn("articles", req_body)

        resp_body = interaction["response"]["body"]
        self.assertIn("scored_articles", resp_body)
        scored_art = resp_body["scored_articles"][0]
        self.assertIn("sentiment_score", scored_art)
        self.assertIn("sentiment_label", scored_art)
        self.assertIn("rationale", scored_art)
        self.assertIn("is_relevant", scored_art)


if __name__ == "__main__":
    unittest.main()
