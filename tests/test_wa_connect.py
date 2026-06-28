import json
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from utils import wa_embedded_signup as es


class _SecretBase(unittest.TestCase):
    def setUp(self):
        self._keys = (
            "WA_CONNECT_SECRET", "META_APP_ID", "META_APP_SECRET",
            "META_CONFIG_ID", "WEBHOOK_PUBLIC_URL",
        )
        self._backup = {k: os.environ.get(k) for k in self._keys}
        os.environ["WA_CONNECT_SECRET"] = "test-secret"

    def tearDown(self):
        for k, v in self._backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class StateSigningTests(_SecretBase):
    def test_roundtrip_returns_org(self):
        state = es.make_state("sn_realtors")
        self.assertEqual(es.verify_state(state), "sn_realtors")

    def test_tampered_signature_rejected(self):
        state = es.make_state("acme")
        raw, sig = state.split(".", 1)
        forged = raw + "." + ("0" * len(sig))
        self.assertIsNone(es.verify_state(forged))

    def test_tampered_payload_rejected(self):
        # Swap the payload for a different org but keep the old signature.
        state = es.make_state("acme")
        _, sig = state.split(".", 1)
        other_raw = es.make_state("victim").split(".", 1)[0]
        self.assertIsNone(es.verify_state(f"{other_raw}.{sig}"))

    def test_expired_state_rejected(self):
        state = es.make_state("acme", ttl=-1)
        self.assertIsNone(es.verify_state(state))

    def test_different_secret_rejected(self):
        state = es.make_state("acme")
        os.environ["WA_CONNECT_SECRET"] = "a-different-secret"
        self.assertIsNone(es.verify_state(state))

    def test_garbage_inputs_rejected(self):
        for bad in ("", "nodot", "a.b.c", "....", None):
            self.assertIsNone(es.verify_state(bad))  # type: ignore[arg-type]

    def test_no_secret_means_no_verification(self):
        os.environ.pop("WA_CONNECT_SECRET", None)
        self.assertIsNone(es.verify_state("anything.sig"))


class ConfigProbeTests(_SecretBase):
    def test_embedded_signup_configured_requires_all_public_bits(self):
        self.assertFalse(es.embedded_signup_configured())
        os.environ["META_APP_ID"] = "111"
        os.environ["META_CONFIG_ID"] = "222"
        os.environ["WEBHOOK_PUBLIC_URL"] = "https://wh.example.com/"
        self.assertTrue(es.embedded_signup_configured())

    def test_exchange_configured_requires_secret(self):
        self.assertFalse(es.exchange_configured())
        os.environ["META_APP_ID"] = "111"
        os.environ["META_APP_SECRET"] = "shh"
        self.assertTrue(es.exchange_configured())

    def test_launcher_html_embeds_signed_state_and_post_url(self):
        os.environ["META_APP_ID"] = "111"
        os.environ["META_CONFIG_ID"] = "222"
        os.environ["WEBHOOK_PUBLIC_URL"] = "https://wh.example.com"
        html = es.launcher_html("sn_realtors")
        self.assertIn("https://wh.example.com/connect/whatsapp", html)
        self.assertIn("config_id", html)
        # the embedded state must verify back to the org
        import re
        m = re.search(r'state:\s*"([^"]+)"', html)
        self.assertIsNotNone(m)
        self.assertEqual(es.verify_state(m.group(1)), "sn_realtors")


class ConnectEndpointTests(_SecretBase):
    def setUp(self):
        super().setUp()
        os.environ["META_APP_ID"] = "111"
        os.environ["META_APP_SECRET"] = "shh"
        import whatsapp_webhook as wh
        self.client = TestClient(wh.app)

    def test_valid_state_completes_connection(self):
        state = es.make_state("sn_realtors")
        with patch.object(es, "complete_connection", return_value={
            "phone_number_id": "PID1", "phone_number": "+91123",
            "waba_id": "W1", "organization_id": "sn_realtors",
        }) as complete:
            resp = self.client.post("/connect/whatsapp", json={
                "code": "AUTHCODE", "state": state, "waba_id": "W1",
                "phone_number_id": "PID1",
            })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        # org came from the signed state, not the body
        _, kwargs = complete.call_args
        self.assertEqual(kwargs["organization_id"], "sn_realtors")

    def test_invalid_state_is_401(self):
        resp = self.client.post("/connect/whatsapp", json={
            "code": "AUTHCODE", "state": "forged.sig",
        })
        self.assertEqual(resp.status_code, 401)

    def test_missing_code_is_400(self):
        state = es.make_state("acme")
        resp = self.client.post("/connect/whatsapp", json={"state": state})
        self.assertEqual(resp.status_code, 400)

    def test_not_configured_is_503(self):
        os.environ.pop("META_APP_SECRET", None)
        resp = self.client.post("/connect/whatsapp", json={"code": "x", "state": "y"})
        self.assertEqual(resp.status_code, 503)

    def test_exchange_failure_returns_502(self):
        state = es.make_state("acme")
        with patch.object(es, "complete_connection", side_effect=RuntimeError("meta down")):
            resp = self.client.post("/connect/whatsapp", json={
                "code": "AUTHCODE", "state": state,
            })
        self.assertEqual(resp.status_code, 502)
        self.assertFalse(resp.json()["ok"])


if __name__ == "__main__":
    unittest.main()
