import unittest

from utils.wa_events import (
    append_outbound_event,
    apply_interaction,
    apply_status_update,
    campaign_summary,
    find_contact_by_message_id,
)


class WaEventsTests(unittest.TestCase):
    def test_outbound_and_status_tracking(self):
        contact = {"id": "1", "name": "Raj", "status": "new", "phone": "+919876543210"}
        append_outbound_event(contact, message_id="wamid.abc", body="Hello", campaign_id="wa_test")
        self.assertEqual(1, len(contact["wa_events"]))
        ok = apply_status_update(contact, "wamid.abc", "read")
        self.assertTrue(ok)
        self.assertEqual("read", contact["wa_events"][0]["status"])
        self.assertEqual("contacted", contact["status"])
        self.assertIn("wa-read", contact.get("tags") or [])

    def test_find_by_message_id(self):
        contacts = [
            {"id": "1", "wa_events": [{"message_id": "wamid.xyz"}]},
            {"id": "2", "wa_events": []},
        ]
        self.assertEqual(0, find_contact_by_message_id(contacts, "wamid.xyz"))
        self.assertEqual(-1, find_contact_by_message_id(contacts, "missing"))

    def test_interaction_maps_stage(self):
        contact = {"id": "1", "status": "new", "tags": []}
        apply_interaction(contact, interaction_id="interested", interaction_title="Yes, interested")
        self.assertEqual("qualified", contact["status"])
        self.assertTrue(any("wa-click" in t for t in contact["tags"]))

    def test_campaign_summary(self):
        contacts = [
            {
                "wa_events": [
                    {"direction": "outbound", "campaign_id": "c1", "status": "read"},
                    {"direction": "outbound", "campaign_id": "c1", "status": "delivered"},
                ]
            }
        ]
        stats = campaign_summary(contacts, "c1")
        self.assertEqual(2, stats["total"])
        self.assertEqual(1, stats["read"])


if __name__ == "__main__":
    unittest.main()
