import json
import os
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


class ResolveOrgTests(unittest.TestCase):
    """Multi-tenancy: inbound phone_number_id -> organization_id resolution."""

    def test_no_postgres_configured_returns_default_without_query(self):
        with patch.object(pg, "postgres_configured", return_value=False), \
             patch.object(pg, "resolve_org_for_phone_number_id") as resolve:
            org = wh._resolve_org("pid1")
        self.assertEqual(org, pg.DEFAULT_ORG_ID)
        resolve.assert_not_called()

    def test_known_number_resolves_to_its_org(self):
        with patch.object(pg, "postgres_configured", return_value=True), \
             patch.object(pg, "resolve_org_for_phone_number_id", return_value="acme"):
            org = wh._resolve_org("pid1")
        self.assertEqual(org, "acme")

    def test_unknown_number_is_rejected_not_defaulted(self):
        # Hardening H3: an unregistered number must NOT fall to the default tenant.
        with patch.object(pg, "postgres_configured", return_value=True), \
             patch.object(pg, "resolve_org_for_phone_number_id", return_value=None):
            org = wh._resolve_org("pid-unregistered")
        self.assertIsNone(org)

    def test_db_error_propagates(self):
        # DB error must propagate so receive() returns 5xx and Meta retries —
        # not be swallowed into the default tenant.
        with patch.object(pg, "postgres_configured", return_value=True), \
             patch.object(pg, "resolve_org_for_phone_number_id",
                          side_effect=RuntimeError("db down")):
            with self.assertRaises(RuntimeError):
                wh._resolve_org("pid1")


class RejectUnregisteredNumberTests(unittest.TestCase):
    """H3: inbound from an unregistered number is rejected, never stored."""

    def setUp(self):
        wh._SEEN_IDS.clear()
        self.client = TestClient(wh.app)
        self._sec = os.environ.pop("META_APP_SECRET", None)

    def tearDown(self):
        if self._sec is not None:
            os.environ["META_APP_SECRET"] = self._sec

    def _payload(self):
        return {"entry": [{"changes": [{"value": {
            "metadata": {"phone_number_id": "ghostpid"},
            "messages": [{"id": "wamid.x", "from": "919", "type": "text",
                          "text": {"body": "hi"}, "timestamp": "1700000000"}],
        }}]}]}

    def test_unregistered_number_rejected(self):
        with patch.object(wh, "_resolve_org", return_value=None), \
             patch.object(wh, "_handle_message") as handle:
            resp = self.client.post("/webhook", json=self._payload())
        handle.assert_not_called()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["handled"], 0)
        self.assertEqual(resp.json()["rejected"], 1)

    def test_registered_number_processed(self):
        with patch.object(wh, "_resolve_org", return_value="acme"), \
             patch.object(wh, "_handle_message", return_value=("created", "c1")) as handle:
            resp = self.client.post("/webhook", json=self._payload())
        handle.assert_called_once()
        self.assertEqual(resp.json()["handled"], 1)
        # org from resolution is passed to the handler
        self.assertEqual(handle.call_args[0][1], "acme")


class SignatureVerificationTests(unittest.TestCase):
    """H2: X-Hub-Signature-256 enforced when META_APP_SECRET is set."""

    def setUp(self):
        wh._SEEN_IDS.clear()
        self.client = TestClient(wh.app)
        self._sec = os.environ.get("META_APP_SECRET")
        os.environ["META_APP_SECRET"] = "test-app-secret"

    def tearDown(self):
        if self._sec is None:
            os.environ.pop("META_APP_SECRET", None)
        else:
            os.environ["META_APP_SECRET"] = self._sec

    def test_missing_signature_is_403(self):
        resp = self.client.post("/webhook", json={"entry": []})
        self.assertEqual(resp.status_code, 403)

    def test_bad_signature_is_403(self):
        resp = self.client.post(
            "/webhook", content=b'{"entry":[]}',
            headers={"X-Hub-Signature-256": "sha256=deadbeef",
                     "Content-Type": "application/json"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_valid_signature_passes(self):
        import hashlib
        import hmac
        body = b'{"entry":[]}'
        sig = hmac.new(b"test-app-secret", body, hashlib.sha256).hexdigest()
        resp = self.client.post(
            "/webhook", content=body,
            headers={"X-Hub-Signature-256": f"sha256={sig}",
                     "Content-Type": "application/json"},
        )
        self.assertEqual(resp.status_code, 200)


class ApiKeyOrgResolutionTests(unittest.TestCase):
    """REST API: gated by MOBILE_API_ENABLED (H8), then bearer token -> org."""

    def setUp(self):
        self._env_backup = {
            k: os.environ.get(k) for k in ("API_KEYS", "API_SECRET_KEY", "MOBILE_API_ENABLED")
        }
        os.environ["MOBILE_API_ENABLED"] = "true"  # most tests assume it's on

    def tearDown(self):
        for k, v in self._env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _request_with_auth(self, token: str | None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return MagicMock(headers=headers)

    def test_disabled_by_default_is_503(self):
        os.environ.pop("MOBILE_API_ENABLED", None)
        os.environ["API_KEYS"] = json.dumps({"key-acme": "acme"})
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            wh._require_api_key(self._request_with_auth("key-acme"))
        self.assertEqual(ctx.exception.status_code, 503)

    def test_api_keys_json_maps_token_to_org(self):
        os.environ["API_KEYS"] = json.dumps({"key-acme": "acme", "key-beta": "beta"})
        os.environ.pop("API_SECRET_KEY", None)
        self.assertEqual(wh._require_api_key(self._request_with_auth("key-acme")), "acme")
        self.assertEqual(wh._require_api_key(self._request_with_auth("key-beta")), "beta")

    def test_legacy_api_secret_key_maps_to_default_org(self):
        os.environ.pop("API_KEYS", None)
        os.environ["API_SECRET_KEY"] = "legacy-secret"
        org = wh._require_api_key(self._request_with_auth("legacy-secret"))
        self.assertEqual(org, pg.DEFAULT_ORG_ID)

    def test_unknown_token_is_unauthorized(self):
        os.environ["API_KEYS"] = json.dumps({"key-acme": "acme"})
        os.environ.pop("API_SECRET_KEY", None)
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            wh._require_api_key(self._request_with_auth("not-a-real-key"))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_no_keys_configured_is_503(self):
        os.environ.pop("API_KEYS", None)
        os.environ.pop("API_SECRET_KEY", None)
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            wh._require_api_key(self._request_with_auth("anything"))
        self.assertEqual(ctx.exception.status_code, 503)


class TokenRedactionTests(unittest.TestCase):
    """H4: WhatsApp access_token never leaves via the REST API."""

    def test_public_account_strips_access_token(self):
        acct = {"id": "1", "phone_number_id": "pid", "access_token": "SECRET",
                "display_name": "Acme", "organization_id": "acme"}
        out = wh._public_account(acct)
        self.assertNotIn("access_token", out)
        self.assertEqual(out["phone_number_id"], "pid")

    def test_list_endpoint_redacts_token(self):
        os.environ["MOBILE_API_ENABLED"] = "true"
        os.environ["API_KEYS"] = json.dumps({"k": "acme"})
        client = TestClient(wh.app)
        fake_pg = MagicMock()
        fake_pg.load_whatsapp_accounts.return_value = [
            {"id": "1", "phone_number_id": "pid", "access_token": "SECRET",
             "organization_id": "acme"},
        ]
        try:
            with patch.object(wh, "_pg", return_value=fake_pg):
                resp = client.get("/api/whatsapp-accounts",
                                  headers={"Authorization": "Bearer k"})
            self.assertEqual(resp.status_code, 200)
            self.assertNotIn("access_token", resp.text)
            self.assertNotIn("SECRET", resp.text)
        finally:
            os.environ.pop("MOBILE_API_ENABLED", None)
            os.environ.pop("API_KEYS", None)


if __name__ == "__main__":
    unittest.main()
