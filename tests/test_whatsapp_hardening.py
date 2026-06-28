import hashlib
import hmac
import unittest
from unittest.mock import MagicMock, patch

from utils import whatsapp


class SignatureTests(unittest.TestCase):
    def _sig(self, body: bytes, secret: str) -> str:
        return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    def test_valid_signature_accepted(self):
        body = b'{"entry":[]}'
        self.assertTrue(
            whatsapp.verify_signature(body, self._sig(body, "secret"), "secret")
        )

    def test_wrong_secret_rejected(self):
        body = b'{"entry":[]}'
        self.assertFalse(
            whatsapp.verify_signature(body, self._sig(body, "secret"), "other")
        )

    def test_tampered_body_rejected(self):
        sig = self._sig(b'{"a":1}', "secret")
        self.assertFalse(whatsapp.verify_signature(b'{"a":2}', sig, "secret"))

    def test_missing_secret_rejected(self):
        self.assertFalse(whatsapp.verify_signature(b"x", "sha256=abc", ""))

    def test_malformed_header_rejected(self):
        for bad in ("", "abc", "md5=xyz", None):
            self.assertFalse(whatsapp.verify_signature(b"x", bad, "secret"))  # type: ignore[arg-type]


class OutboundTokenTests(unittest.TestCase):
    """H5: outbound uses the connected number's own token + phone_number_id."""

    def test_send_uses_supplied_account_token_and_pid(self):
        fake = MagicMock()
        fake.json.return_value = {"messages": [{"id": "m1"}]}
        fake.raise_for_status = lambda: None
        with patch.object(whatsapp.requests, "post", return_value=fake) as post:
            whatsapp.send_whatsapp_text(
                "919", "hi", phone_number_id="PID9", access_token="TOKEN9"
            )
        url = post.call_args[0][0]
        headers = post.call_args.kwargs["headers"]
        self.assertIn("PID9", url)
        self.assertEqual(headers["Authorization"], "Bearer TOKEN9")

    def test_account_credentials_helper(self):
        import whatsapp_webhook as wh
        from utils import crm_store_postgres as pg

        with patch.object(pg, "postgres_configured", return_value=True), \
             patch.object(pg, "get_whatsapp_account_by_pid",
                          return_value={"access_token": "T", "phone_number_id": "P"}):
            creds = wh._account_credentials("P")
        self.assertEqual(creds["access_token"], "T")

    def test_account_credentials_empty_without_postgres(self):
        import whatsapp_webhook as wh
        from utils import crm_store_postgres as pg

        with patch.object(pg, "postgres_configured", return_value=False):
            self.assertEqual(wh._account_credentials("P"), {})


if __name__ == "__main__":
    unittest.main()
