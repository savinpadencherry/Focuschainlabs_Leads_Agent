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


if __name__ == "__main__":
    unittest.main()
