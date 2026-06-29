import os
import unittest

from fastapi.testclient import TestClient

import secure_webhook_app as secure


class SecureWebhookEntrypointTests(unittest.TestCase):
    def setUp(self):
        self._required = os.environ.get("WEBHOOK_SIGNATURE_REQUIRED")
        self._secret = os.environ.get("META_APP_SECRET")
        self.client = TestClient(secure.app)

    def tearDown(self):
        if self._required is None:
            os.environ.pop("WEBHOOK_SIGNATURE_REQUIRED", None)
        else:
            os.environ["WEBHOOK_SIGNATURE_REQUIRED"] = self._required
        if self._secret is None:
            os.environ.pop("META_APP_SECRET", None)
        else:
            os.environ["META_APP_SECRET"] = self._secret

    def test_required_without_meta_secret_fails_closed(self):
        os.environ["WEBHOOK_SIGNATURE_REQUIRED"] = "true"
        os.environ.pop("META_APP_SECRET", None)

        response = self.client.post("/webhook", json={"entry": []})

        self.assertEqual(503, response.status_code)
        self.assertIn("required but not configured", response.text)

    def test_optional_without_meta_secret_keeps_dev_compatibility(self):
        os.environ.pop("WEBHOOK_SIGNATURE_REQUIRED", None)
        os.environ.pop("META_APP_SECRET", None)

        response = self.client.post("/webhook", json={"entry": []})

        self.assertEqual(200, response.status_code)

    def test_required_with_secret_still_rejects_missing_signature(self):
        os.environ["WEBHOOK_SIGNATURE_REQUIRED"] = "true"
        os.environ["META_APP_SECRET"] = "meta-secret"

        response = self.client.post("/webhook", json={"entry": []})

        self.assertEqual(403, response.status_code)


if __name__ == "__main__":
    unittest.main()
