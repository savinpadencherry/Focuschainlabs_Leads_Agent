import json
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import whatsapp_webhook as wh
from utils import crm_store_postgres as pg


class AlreadySeenTests(unittest.TestCase):
    def setUp(self):
        wh._SEEN_IDS.clear()

    def test_blank_id_never_seen(self):
        self.assertFalse(wh._already_seen(""))

    def test_in_memory_hit_short_circuits_db(self):
        wh._SEEN_IDS["wamid.cached"] = None
        with patch.object(pg, "postgres_configured", return_value=True) as configured:
            self.assertTrue(wh._already_seen("wamid.cached"))
        configured.assert_not_called()

    def test_durable_hit_when_not_in_memory(self):
        with patch.object(pg, "postgres_configured", return_value=True), \
             patch.object(pg, "message_id_exists", return_value=True) as exists:
            self.assertTrue(wh._already_seen("wamid.fromdb"))
        exists.assert_called_once_with("wamid.fromdb")
        self.assertIn("wamid.fromdb", wh._SEEN_IDS)

    def test_unseen_message_marks_seen_and_returns_false(self):
        with patch.object(pg, "postgres_configured", return_value=True), \
             patch.object(pg, "message_id_exists", return_value=False):
            self.assertFalse(wh._already_seen("wamid.new"))
        self.assertIn("wamid.new", wh._SEEN_IDS)

    def test_db_error_falls_back_to_in_memory_only(self):
        with patch.object(pg, "postgres_configured", return_value=True), \
             patch.object(pg, "message_id_exists", side_effect=RuntimeError("db down")):
            self.assertFalse(wh._already_seen("wamid.dbdown"))
        self.assertIn("wamid.dbdown", wh._SEEN_IDS)

    def test_no_postgres_configured_uses_memory_only(self):
        with patch.object(pg, "postgres_configured", return_value=False):
            self.assertFalse(wh._already_seen("wamid.nopg"))
            self.assertTrue(wh._already_seen("wamid.nopg"))


class ReceiveStatusCodeTests(unittest.TestCase):
    """Sprint 1: a persistence failure must surface as 5xx so Meta retries."""

    def setUp(self):
        wh._SEEN_IDS.clear()
        self.client = TestClient(wh.app)

    def _payload(self):
        return {
            "entry": [{
                "changes": [{
                    "value": {
                        "metadata": {"phone_number_id": "pid1", "display_phone_number": "10000000000"},
                        "contacts": [{"wa_id": "919876543210", "profile": {"name": "Raj"}}],
                        "messages": [{
                            "id": "wamid.abc123",
                            "from": "919876543210",
                            "type": "text",
                            "text": {"body": "Hello there"},
                            "timestamp": "1700000000",
                        }],
                    }
                }]
            }]
        }

    def test_returns_200_when_message_handled_successfully(self):
        with patch.object(wh, "_handle_message", return_value=("created", "c1")) as handle:
            resp = self.client.post("/webhook", json=self._payload())
        handle.assert_called_once()
        self.assertEqual(200, resp.status_code)
        self.assertEqual("ok", resp.json()["status"])

    def test_returns_500_when_storing_message_raises(self):
        with patch.object(wh, "_handle_message", side_effect=RuntimeError("CRM save failed")):
            resp = self.client.post("/webhook", json=self._payload())
        self.assertEqual(500, resp.status_code)
        self.assertEqual("partial_failure", resp.json()["status"])

    def test_duplicate_message_id_is_skipped_not_reprocessed(self):
        wh._SEEN_IDS["wamid.abc123"] = None
        with patch.object(wh, "_handle_message") as handle:
            resp = self.client.post("/webhook", json=self._payload())
        handle.assert_not_called()
        self.assertEqual(200, resp.status_code)
        self.assertEqual(0, resp.json()["handled"])


class HealthRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(wh.app)

    def test_healthz_ok(self):
        resp = self.client.get("/healthz")
        self.assertEqual(200, resp.status_code)
        self.assertTrue(resp.json()["ok"])

    def test_status_ok(self):
        resp = self.client.get("/status")
        self.assertEqual(200, resp.status_code)
        self.assertTrue(resp.json()["ok"])


if __name__ == "__main__":
    unittest.main()
