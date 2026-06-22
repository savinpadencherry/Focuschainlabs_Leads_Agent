import unittest
from datetime import date
from unittest.mock import patch

from agent.crm_search_agent import (
    local_search,
    parse_query,
    resolve_status_update,
    search_contacts,
)
from utils.crm_models import next_pipeline_status


class CrmSearchAgentTests(unittest.TestCase):
    def test_local_search_multi_token(self):
        contacts = [
            {"id": "1", "name": "Rajesh", "company": "Acme", "status": "new"},
            {"id": "2", "name": "Priya", "company": "Beta", "status": "new"},
        ]
        hits = local_search(contacts, "raj acme")
        self.assertEqual(1, len(hits))
        self.assertEqual("1", hits[0]["id"])

    def test_next_pipeline_status(self):
        self.assertEqual("contacted", next_pipeline_status("new"))
        self.assertEqual("qualified", next_pipeline_status("contacted"))
        self.assertIsNone(next_pipeline_status("won"))

    def test_parse_query_status_update_local(self):
        spec = parse_query("move Rajesh to contacted")
        self.assertEqual("status_update", spec["mode"])
        self.assertEqual("contacted", spec["status_update"]["new_status"])

    @patch("agent.crm_search_agent.llm_configured", return_value=False)
    def test_search_contacts_local_fallback(self, _mock_llm):
        contacts = [
            {"id": "1", "name": "Jewel", "company": "Spacia", "status": "new", "deal_status": "open"},
            {"id": "2", "name": "Radha", "company": "Interiors", "status": "qualified", "deal_status": "open"},
        ]
        filtered, spec = search_contacts(contacts, "jewel")
        self.assertEqual(1, len(filtered))
        self.assertEqual("filter", spec["mode"])

    def test_resolve_status_update_advance(self):
        contact = {"status": "new"}
        spec = {"status_update": {"advance_next": True, "new_status": ""}}
        self.assertEqual("contacted", resolve_status_update(contact, spec))


if __name__ == "__main__":
    unittest.main()
