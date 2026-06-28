import unittest

from utils import inbound_batch


class _FakePg:
    def __init__(self, rows, contacts, org_ids=None):
        self.rows = rows
        self.contacts = contacts
        self.org_ids = org_ids or []
        self.upserts = []      # (contacts, org)
        self.processed = []    # flat list of marked ids

    def load_unprocessed_inbound(self, organization_id, limit=5000):
        return list(self.rows)

    def get_contact(self, contact_id, organization_id):
        return self.contacts.get(contact_id)

    def bulk_upsert(self, contacts, organization_id, merge_mobile_fields=True):
        self.upserts.append((contacts, organization_id))
        return len(contacts)

    def mark_interactions_processed(self, ids):
        self.processed.extend(ids)
        return len(ids)

    def org_ids_with_unprocessed_inbound(self):
        return list(self.org_ids)


def _parse_ok(calls):
    def _p(*, text, existing):
        calls.append(text)
        return {"ok": True, "fields": {"company": "Acme", "notes": "interested in demo"}}
    return _p


class ProcessOrgTests(unittest.TestCase):
    def _rows(self):
        return [
            {"id": "i1", "contact_id": "c1", "body": "hi there"},
            {"id": "i2", "contact_id": "c1", "body": "any update?"},
            {"id": "i3", "contact_id": "c2", "body": "send pricing"},
        ]

    def test_one_llm_call_per_contact_not_per_message(self):
        calls = []
        pg = _FakePg(self._rows(), {"c1": {"id": "c1"}, "c2": {"id": "c2"}})
        stats = inbound_batch.process_org("org1", pg=pg, parse=_parse_ok(calls), max_calls=100)
        self.assertEqual(stats["contacts"], 2)
        self.assertEqual(stats["messages"], 3)
        self.assertEqual(stats["llm_calls"], 2)   # one per contact, not per message
        self.assertEqual(stats["updated"], 2)
        self.assertEqual(set(pg.processed), {"i1", "i2", "i3"})
        # c1's call concatenated both of its messages
        self.assertIn("hi there", calls[0])
        self.assertIn("any update?", calls[0])

    def test_budget_cap_stops_and_leaves_rest_unprocessed(self):
        calls = []
        pg = _FakePg(self._rows(), {"c1": {"id": "c1"}, "c2": {"id": "c2"}})
        stats = inbound_batch.process_org("org1", pg=pg, parse=_parse_ok(calls), max_calls=1)
        self.assertTrue(stats["budget_stopped"])
        self.assertEqual(stats["llm_calls"], 1)
        # only the first contact's messages were marked processed
        self.assertEqual(set(pg.processed), {"i1", "i2"})

    def test_orphaned_contact_is_marked_processed_and_skipped(self):
        calls = []
        pg = _FakePg(
            [{"id": "i9", "contact_id": "ghost", "body": "hello"}], contacts={}
        )
        stats = inbound_batch.process_org("org1", pg=pg, parse=_parse_ok(calls), max_calls=100)
        self.assertEqual(stats["skipped_no_contact"], 1)
        self.assertEqual(stats["llm_calls"], 0)
        self.assertEqual(pg.processed, ["i9"])      # stamped so we don't retry forever

    def test_dry_run_writes_nothing(self):
        calls = []
        pg = _FakePg(self._rows(), {"c1": {"id": "c1"}, "c2": {"id": "c2"}})
        stats = inbound_batch.process_org(
            "org1", pg=pg, parse=_parse_ok(calls), max_calls=100, dry_run=True
        )
        self.assertEqual(stats["llm_calls"], 2)     # still calls the model (read-only)
        self.assertEqual(pg.upserts, [])
        self.assertEqual(pg.processed, [])

    def test_passes_organization_id_to_upsert(self):
        pg = _FakePg(
            [{"id": "i1", "contact_id": "c1", "body": "hi"}], {"c1": {"id": "c1"}}
        )
        inbound_batch.process_org("sn_realtors", pg=pg, parse=_parse_ok([]), max_calls=100)
        self.assertEqual(pg.upserts[0][1], "sn_realtors")


class MergeContactTests(unittest.TestCase):
    def test_fills_empty_fields_only(self):
        merged = inbound_batch._merge_contact(
            {"id": "c1", "company": "Existing Co", "email": ""},
            {"company": "New Co", "email": "a@b.com"},
        )
        self.assertEqual(merged["company"], "Existing Co")  # not clobbered
        self.assertEqual(merged["email"], "a@b.com")        # filled

    def test_accumulates_notes(self):
        merged = inbound_batch._merge_contact(
            {"id": "c1", "notes": "old note"}, {"notes": "new note"}
        )
        self.assertIn("old note", merged["notes"])
        self.assertIn("new note", merged["notes"])

    def test_does_not_duplicate_existing_note(self):
        merged = inbound_batch._merge_contact(
            {"id": "c1", "notes": "already here"}, {"notes": "already here"}
        )
        self.assertEqual(merged["notes"].count("already here"), 1)


class ProcessAllTests(unittest.TestCase):
    def test_iterates_every_active_org(self):
        pg = _FakePg([], {}, org_ids=["focuschainlabs", "sn_realtors"])
        results = inbound_batch.process_all(pg=pg, parse=_parse_ok([]))
        self.assertEqual([r["org"] for r in results], ["focuschainlabs", "sn_realtors"])


if __name__ == "__main__":
    unittest.main()
