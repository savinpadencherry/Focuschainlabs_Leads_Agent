import unittest

from utils.crm_models import merge_contacts, normalize_contact


class CrmModelTests(unittest.TestCase):
    def test_terminal_deal_state_and_stage_stay_consistent(self):
        closed_from_state = normalize_contact(
            {"name": "A", "status": "proposal", "deal_status": "won"}
        )
        closed_from_stage = normalize_contact(
            {"name": "B", "status": "lost", "deal_status": "open"}
        )

        self.assertEqual(("won", "won"), (closed_from_state["status"], closed_from_state["deal_status"]))
        self.assertEqual(("lost", "lost"), (closed_from_stage["status"], closed_from_stage["deal_status"]))

    def test_activity_and_secondary_contacts_are_normalized(self):
        contact = normalize_contact(
            {
                "name": "A",
                "comments": [{"id": "note-1", "body": "Call booked"}],
                "email_events": [{"id": "mail-1", "direction": "invalid", "subject": "Hello"}],
                "contact_people": [{"id": "person-1", "name": "Priya", "role": "Decision maker"}],
            }
        )

        self.assertEqual("manual", contact["comments"][0]["source"])
        self.assertEqual("sent", contact["email_events"][0]["direction"])
        self.assertEqual("Decision maker", contact["contact_people"][0]["role"])

    def test_merge_deduplicates_nested_records_and_preserves_existing_context(self):
        existing = normalize_contact(
            {
                "id": "lead-1",
                "name": "A",
                "comments": [{"id": "note-1", "body": "Existing note"}],
                "contact_people": [{"id": "person-1", "name": "Priya", "role": "Decision maker"}],
            }
        )
        incoming = normalize_contact(
            {
                "id": "lead-2",
                "name": "A",
                "comments": [{"id": "note-1", "body": ""}, {"id": "note-2", "body": "New note"}],
                "contact_people": [{"id": "person-1", "name": "Priya", "role": ""}],
            }
        )

        merged = merge_contacts(existing, incoming)

        self.assertEqual(2, len(merged["comments"]))
        self.assertEqual("Existing note", merged["comments"][0]["body"])
        self.assertEqual("Decision maker", merged["contact_people"][0]["role"])


if __name__ == "__main__":
    unittest.main()
