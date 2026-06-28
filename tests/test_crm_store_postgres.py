import unittest
from unittest.mock import MagicMock, patch

from utils import crm_store_postgres as pg


class _FakeCursor:
    def __init__(self, *, fetchone_result=None, fetchall_result=None, rowcount=1):
        self.fetchone_result = fetchone_result
        self.fetchall_result = fetchall_result or []
        self.rowcount = rowcount
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return self.fetchone_result

    def fetchall(self):
        return self.fetchall_result

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeConn:
    def __init__(self, cursor: _FakeCursor):
        self._cursor = cursor
        self.committed = False

    def cursor(self, cursor_factory=None):
        return self._cursor

    def commit(self):
        self.committed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _patched_connect(cursor: _FakeCursor):
    conn = _FakeConn(cursor)
    return patch.object(pg, "_connect", return_value=conn), conn


class InteractionStoreTests(unittest.TestCase):
    def test_message_id_exists_false_for_blank(self):
        self.assertFalse(pg.message_id_exists(""))
        self.assertFalse(pg.message_id_exists(None))

    def test_message_id_exists_true_when_row_found(self):
        cursor = _FakeCursor(fetchone_result=(1,))
        patcher, _ = _patched_connect(cursor)
        with patcher:
            self.assertTrue(pg.message_id_exists("wamid.abc"))

    def test_message_id_exists_false_when_no_row(self):
        cursor = _FakeCursor(fetchone_result=None)
        patcher, _ = _patched_connect(cursor)
        with patcher:
            self.assertFalse(pg.message_id_exists("wamid.missing"))

    def test_insert_interaction_requires_contact_id(self):
        with self.assertRaises(ValueError):
            pg.insert_interaction({"body": "hi"})

    def test_insert_interaction_returns_true_on_fresh_insert(self):
        cursor = _FakeCursor(rowcount=1)
        patcher, conn = _patched_connect(cursor)
        with patcher:
            ok = pg.insert_interaction({
                "contact_id": "c1",
                "author": "Raj",
                "body": "Hello",
                "kind": "whatsapp_message",
                "direction": "inbound",
                "message_id": "wamid.abc",
                "status": "received",
            })
        self.assertTrue(ok)
        self.assertTrue(conn.committed)
        sql, params = cursor.executed[0]
        self.assertIn("ON CONFLICT (message_id)", sql)
        self.assertEqual(params["contact_id"], "c1")
        self.assertEqual(params["message_id"], "wamid.abc")

    def test_insert_interaction_returns_false_on_duplicate(self):
        cursor = _FakeCursor(rowcount=0)
        patcher, _ = _patched_connect(cursor)
        with patcher:
            ok = pg.insert_interaction({
                "contact_id": "c1",
                "message_id": "wamid.dup",
            })
        self.assertFalse(ok)

    def test_update_interaction_status_blank_id_returns_none(self):
        self.assertIsNone(pg.update_interaction_status("", "delivered"))

    def test_update_interaction_status_returns_match(self):
        cursor = _FakeCursor(fetchone_result={"contact_id": "c1", "status": "read"})
        patcher, conn = _patched_connect(cursor)
        with patcher:
            result = pg.update_interaction_status("wamid.abc", "read")
        self.assertEqual(result, {"contact_id": "c1", "status": "read"})
        self.assertTrue(conn.committed)

    def test_update_interaction_status_orphan_returns_none(self):
        cursor = _FakeCursor(fetchone_result=None)
        patcher, _ = _patched_connect(cursor)
        with patcher:
            result = pg.update_interaction_status("wamid.unknown", "delivered")
        self.assertIsNone(result)

    def test_load_interactions_maps_rows(self):
        cursor = _FakeCursor(fetchall_result=[{
            "id": "i1",
            "contact_id": "c1",
            "author": "Raj",
            "body": "Hello",
            "kind": "whatsapp_message",
            "direction": "inbound",
            "message_id": "wamid.abc",
            "status": "received",
            "created_at": "2026-01-01T00:00:00+00:00",
        }])
        patcher, _ = _patched_connect(cursor)
        with patcher:
            rows = pg.load_interactions("c1")
        self.assertEqual(1, len(rows))
        self.assertEqual("c1", rows[0]["contact_id"])
        self.assertEqual("wamid.abc", rows[0]["message_id"])
        self.assertEqual("Hello", rows[0]["body"])

    def test_insert_interaction_defaults_to_default_org(self):
        cursor = _FakeCursor(rowcount=1)
        patcher, _ = _patched_connect(cursor)
        with patcher:
            pg.insert_interaction({"contact_id": "c1", "message_id": "wamid.abc"})
        _, params = cursor.executed[0]
        self.assertEqual(params["organization_id"], pg.DEFAULT_ORG_ID)

    def test_insert_interaction_stamps_given_org(self):
        cursor = _FakeCursor(rowcount=1)
        patcher, _ = _patched_connect(cursor)
        with patcher:
            pg.insert_interaction({"contact_id": "c1", "message_id": "wamid.abc"}, "acme")
        _, params = cursor.executed[0]
        self.assertEqual(params["organization_id"], "acme")

    def test_update_interaction_status_returns_organization_id(self):
        cursor = _FakeCursor(
            fetchone_result={"contact_id": "c1", "status": "read", "organization_id": "acme"}
        )
        patcher, _ = _patched_connect(cursor)
        with patcher:
            result = pg.update_interaction_status("wamid.abc", "read")
        self.assertEqual(result["organization_id"], "acme")
        sql, _ = cursor.executed[0]
        self.assertIn("RETURNING contact_id, status, organization_id", sql)

    def test_load_interactions_filters_by_org(self):
        cursor = _FakeCursor(fetchall_result=[])
        patcher, _ = _patched_connect(cursor)
        with patcher:
            pg.load_interactions("c1", "acme")
        sql, params = cursor.executed[0]
        self.assertIn("organization_id = %s", sql)
        self.assertEqual(params, ("c1", "acme"))


class OrgScopingTests(unittest.TestCase):
    def test_load_all_contacts_filters_by_org(self):
        cursor = _FakeCursor(fetchall_result=[])
        patcher, _ = _patched_connect(cursor)
        with patcher:
            pg.load_all_contacts("acme")
        sql, params = cursor.executed[0]
        self.assertIn("WHERE organization_id = %s", sql)
        self.assertEqual(params, ("acme",))

    def test_load_all_contacts_defaults_to_default_org(self):
        cursor = _FakeCursor(fetchall_result=[])
        patcher, _ = _patched_connect(cursor)
        with patcher:
            pg.load_all_contacts()
        _, params = cursor.executed[0]
        self.assertEqual(params, (pg.DEFAULT_ORG_ID,))

    def test_get_contact_filters_by_org(self):
        cursor = _FakeCursor(fetchone_result=None)
        patcher, _ = _patched_connect(cursor)
        with patcher:
            pg.get_contact("c1", "acme")
        sql, params = cursor.executed[0]
        self.assertIn("organization_id = %s", sql)
        self.assertEqual(params, ("c1", "acme"))

    def test_count_contacts_filters_by_org(self):
        cursor = _FakeCursor(fetchone_result=(3,))
        patcher, _ = _patched_connect(cursor)
        with patcher:
            n = pg.count_contacts("acme")
        self.assertEqual(n, 3)
        sql, params = cursor.executed[0]
        self.assertIn("organization_id = %s", sql)
        self.assertEqual(params, ("acme",))

    def test_delete_contacts_filters_by_org(self):
        cursor = _FakeCursor()
        patcher, _ = _patched_connect(cursor)
        with patcher:
            pg.delete_contacts(["c1", "c2"], "acme")
        sql, params = cursor.executed[0]
        self.assertIn("organization_id = %s", sql)
        self.assertEqual(params, (["c1", "c2"], "acme"))

    def test_bulk_upsert_sql_has_org_conflict_guard(self):
        captured = {}
        real_execute_batch = pg.execute_batch

        def _spy(cur, sql, rows, **kwargs):
            captured["sql"] = sql
            captured["rows"] = rows

        with patch.object(pg, "execute_batch", side_effect=_spy):
            cursor = _FakeCursor()
            patcher, _ = _patched_connect(cursor)
            with patcher:
                pg.bulk_upsert([{"id": "c1", "name": "Raj"}], "acme")
        self.assertIn(
            "WHERE contacts.organization_id = EXCLUDED.organization_id", captured["sql"]
        )
        self.assertEqual(captured["rows"][0][0], "c1")
        self.assertEqual(captured["rows"][0][1], "acme")

    def test_resolve_org_for_phone_number_id_found(self):
        cursor = _FakeCursor(fetchone_result=("acme",))
        patcher, _ = _patched_connect(cursor)
        with patcher:
            org = pg.resolve_org_for_phone_number_id("pid1")
        self.assertEqual(org, "acme")

    def test_resolve_org_for_phone_number_id_not_found(self):
        cursor = _FakeCursor(fetchone_result=None)
        patcher, _ = _patched_connect(cursor)
        with patcher:
            org = pg.resolve_org_for_phone_number_id("pid-unknown")
        self.assertIsNone(org)

    def test_resolve_org_for_phone_number_id_blank_returns_none_without_query(self):
        with patch.object(pg, "_connect") as connect:
            self.assertIsNone(pg.resolve_org_for_phone_number_id(""))
        connect.assert_not_called()

    def test_upsert_whatsapp_account_has_org_conflict_guard(self):
        cursor = _FakeCursor()
        patcher, _ = _patched_connect(cursor)
        with patcher:
            pg.upsert_whatsapp_account({"phone_number_id": "pid1"}, "acme")
        sql, params = cursor.executed[0]
        self.assertIn(
            "WHERE whatsapp_accounts.organization_id = EXCLUDED.organization_id", sql
        )
        self.assertEqual(params["organization_id"], "acme")

    def test_delete_whatsapp_account_filters_by_org(self):
        cursor = _FakeCursor()
        patcher, _ = _patched_connect(cursor)
        with patcher:
            pg.delete_whatsapp_account("acct1", "acme")
        sql, params = cursor.executed[0]
        self.assertIn("organization_id = %s", sql)
        self.assertEqual(params, ("acct1", "acme"))


class DailyBatchQueueTests(unittest.TestCase):
    def test_insert_interaction_processed_stamps_processed_at(self):
        cursor = _FakeCursor(rowcount=1)
        patcher, _ = _patched_connect(cursor)
        with patcher:
            pg.insert_interaction(
                {"contact_id": "c1", "message_id": "wamid.x"}, "acme", processed=True
            )
        _, params = cursor.executed[0]
        self.assertIsNotNone(params["processed_at"])

    def test_insert_interaction_unprocessed_leaves_processed_at_null(self):
        cursor = _FakeCursor(rowcount=1)
        patcher, _ = _patched_connect(cursor)
        with patcher:
            pg.insert_interaction({"contact_id": "c1", "message_id": "wamid.y"}, "acme")
        _, params = cursor.executed[0]
        self.assertIsNone(params["processed_at"])

    def test_load_unprocessed_inbound_filters_org_and_pending(self):
        cursor = _FakeCursor(fetchall_result=[
            {"id": "i1", "contact_id": "c1", "body": "hi", "created_at": "2026-01-01T00:00:00+00:00"},
        ])
        patcher, _ = _patched_connect(cursor)
        with patcher:
            rows = pg.load_unprocessed_inbound("acme")
        sql, params = cursor.executed[0]
        self.assertIn("processed_at IS NULL", sql)
        self.assertIn("direction = 'inbound'", sql)
        self.assertEqual(params[0], "acme")
        self.assertEqual(rows[0]["contact_id"], "c1")

    def test_mark_interactions_processed_updates_rows(self):
        cursor = _FakeCursor(rowcount=2)
        patcher, _ = _patched_connect(cursor)
        with patcher:
            n = pg.mark_interactions_processed(["i1", "i2"])
        self.assertEqual(n, 2)
        sql, params = cursor.executed[0]
        self.assertIn("SET processed_at = now()", sql)
        self.assertEqual(params, (["i1", "i2"],))

    def test_mark_interactions_processed_noop_on_empty(self):
        cursor = _FakeCursor()
        patcher, _ = _patched_connect(cursor)
        with patcher:
            self.assertEqual(pg.mark_interactions_processed([]), 0)
        self.assertEqual(cursor.executed, [])

    def test_org_ids_with_unprocessed_inbound(self):
        cursor = _FakeCursor(fetchall_result=[("focuschainlabs",), ("sn_realtors",)])
        patcher, _ = _patched_connect(cursor)
        with patcher:
            ids = pg.org_ids_with_unprocessed_inbound()
        self.assertEqual(ids, ["focuschainlabs", "sn_realtors"])


if __name__ == "__main__":
    unittest.main()
