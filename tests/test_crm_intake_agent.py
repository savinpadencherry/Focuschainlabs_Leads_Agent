import unittest
from unittest.mock import patch

from agent.crm_intake_agent import (
    _clean_fields,
    _critical_missing,
    intake_completeness,
    merge_intake_fields,
    parse_contact,
)


class CrmIntakeAgentTests(unittest.TestCase):
    def test_critical_missing_requires_identity_and_channel(self):
        self.assertEqual(["company or name", "phone or email"], _critical_missing({}))
        self.assertEqual(["phone or email"], _critical_missing({"company": "Acme"}))
        self.assertEqual(["company or name"], _critical_missing({"email": "a@b.com"}))
        self.assertEqual([], _critical_missing({"name": "A", "phone": "+91 98xxx"}))

    def test_clean_fields_constrains_enums(self):
        fields = _clean_fields(
            {
                "fields": {
                    "status": "bogus",
                    "deal_status": "bogus",
                    "source": "bogus",
                    "company": "Acme",
                }
            }
        )
        self.assertEqual("new", fields["status"])
        self.assertEqual("open", fields["deal_status"])
        self.assertEqual("other", fields["source"])
        self.assertEqual("Acme", fields["company"])

    def test_merge_intake_fields_keeps_prior_values(self):
        existing = {"company": "Acme", "name": "Raj", "phone": "", "email": ""}
        incoming = {"company": "", "name": "", "phone": "+91 98xxx", "email": ""}
        merged = merge_intake_fields(existing, incoming)
        self.assertEqual("Acme", merged["company"])
        self.assertEqual("Raj", merged["name"])
        self.assertEqual("+91 98xxx", merged["phone"])

    def test_intake_completeness_counts_and_gaps(self):
        filled, total, gaps = intake_completeness(
            {"company": "Acme", "name": "Raj", "phone": "+91 98xxx", "status": "new"}
        )
        self.assertGreater(filled, 0)
        self.assertEqual(total, 14)
        self.assertEqual([], gaps)

    @patch("agent.crm_intake_agent.generate_json")
    def test_parse_contact_merges_existing_round(self, mock_generate_json):
        mock_generate_json.return_value = {
            "fields": {
                "company": "",
                "name": "",
                "title": "",
                "email": "raj@acme.com",
                "phone": "",
                "industry": "",
                "owner": "",
                "value": "",
                "client": "",
                "status": "new",
                "deal_status": "open",
                "source": "other",
                "notes": "",
                "next_follow_up": "",
            },
            "missing": [],
            "follow_up": "",
            "summary": "Raj at Acme",
        }
        existing = {"company": "Acme", "name": "Rajesh Kumar"}
        result = parse_contact(text="email is raj@acme.com", existing=existing, today="2026-06-07")

        self.assertTrue(result["ok"])
        self.assertEqual("Acme", result["fields"]["company"])
        self.assertEqual("Rajesh Kumar", result["fields"]["name"])
        self.assertEqual("raj@acme.com", result["fields"]["email"])
        self.assertEqual([], result["missing"])

    @patch("agent.crm_intake_agent.generate_json")
    def test_parse_contact_degrades_when_model_returns_nothing(self, mock_generate_json):
        mock_generate_json.return_value = {}
        result = parse_contact(text="something unclear", today="2026-06-07")
        self.assertFalse(result["ok"])
        self.assertIn("company or name", result["missing"])


if __name__ == "__main__":
    unittest.main()
