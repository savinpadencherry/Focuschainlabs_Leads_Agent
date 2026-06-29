import os
import unittest
from unittest.mock import MagicMock, patch

from utils import whatsapp
from utils.webhook_security import (
    webhook_signature_configured,
    webhook_signature_required,
)


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {"messages": [{"id": "wamid.test"}]}


class TenantScopedOutboundTests(unittest.TestCase):
    def _pg(self, account_by_pid=None):
        pg = MagicMock()
        pg.get_whatsapp_account_by_pid.return_value = account_by_pid
        return pg

    def test_focuschain_broadcast_uses_focuschain_account(self):
        account = {
            "organization_id": "focuschainlabs",
            "phone_number_id": "FCL_PID",
            "access_token": "FCL_TOKEN",
            "active": True,
        }
        pg = self._pg()
        with patch.object(whatsapp, "_postgres_store", return_value=pg), \
             patch.object(whatsapp, "_streamlit_tenant_account", return_value=(True, account)), \
             patch.object(whatsapp.requests, "post", return_value=_Response()) as post:
            whatsapp.send_whatsapp_text("919999999999", "hello")

        self.assertIn("/FCL_PID/messages", post.call_args.args[0])
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"],
            "Bearer FCL_TOKEN",
        )

    def test_sn_realtors_template_uses_sn_account(self):
        account = {
            "organization_id": "sn_realtors",
            "phone_number_id": "SN_PID",
            "access_token": "SN_TOKEN",
            "active": True,
        }
        pg = self._pg()
        with patch.object(whatsapp, "_postgres_store", return_value=pg), \
             patch.object(whatsapp, "_streamlit_tenant_account", return_value=(True, account)), \
             patch.object(whatsapp.requests, "post", return_value=_Response()) as post:
            whatsapp.send_whatsapp_template(
                "918888888888",
                "property_offer",
                body_params=["Hi Suraj"],
            )

        self.assertIn("/SN_PID/messages", post.call_args.args[0])
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"],
            "Bearer SN_TOKEN",
        )
        self.assertEqual(post.call_args.kwargs["json"]["type"], "template")

    def test_multiple_accounts_without_admin_selection_blocks_send(self):
        pg = self._pg()
        with patch.object(whatsapp, "_postgres_store", return_value=pg), \
             patch.object(
                 whatsapp,
                 "_streamlit_tenant_account",
                 side_effect=RuntimeError("select the sending number"),
             ), \
             patch.object(whatsapp.requests, "post") as post:
            with self.assertRaisesRegex(RuntimeError, "select the sending number"):
                whatsapp.send_whatsapp_text("919999999999", "hello")
        post.assert_not_called()

    def test_unknown_pid_never_falls_back_to_global_credentials(self):
        pg = self._pg(account_by_pid=None)
        env = {
            "WHATSAPP_PHONE_NUMBER_ID": "GLOBAL_PID",
            "WHATSAPP_ACCESS_TOKEN": "GLOBAL_TOKEN",
        }
        with patch.dict(os.environ, env, clear=False), \
             patch.object(whatsapp, "_postgres_store", return_value=pg), \
             patch.object(whatsapp.requests, "post") as post:
            with self.assertRaisesRegex(RuntimeError, "not registered"):
                whatsapp.send_whatsapp_text(
                    "919999999999",
                    "hello",
                    phone_number_id="UNKNOWN_PID",
                )
        post.assert_not_called()

    def test_registered_pid_uses_database_token_not_global_or_caller_token(self):
        account = {
            "organization_id": "focuschainlabs",
            "phone_number_id": "FCL_PID",
            "access_token": "DATABASE_TOKEN",
            "active": True,
        }
        pg = self._pg(account_by_pid=account)
        env = {"WHATSAPP_ACCESS_TOKEN": "GLOBAL_TOKEN"}
        with patch.dict(os.environ, env, clear=False), \
             patch.object(whatsapp, "_postgres_store", return_value=pg), \
             patch.object(whatsapp.requests, "post", return_value=_Response()) as post:
            whatsapp.send_whatsapp_text(
                "919999999999",
                "hello",
                phone_number_id="FCL_PID",
                access_token="CALLER_TOKEN",
            )

        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"],
            "Bearer DATABASE_TOKEN",
        )


class WebhookSignatureFailClosedTests(unittest.TestCase):
    def test_required_switch_parsing(self):
        for value in ("1", "true", "TRUE", "yes"):
            with self.subTest(value=value), patch.dict(
                os.environ, {"WEBHOOK_SIGNATURE_REQUIRED": value}, clear=False
            ):
                self.assertTrue(webhook_signature_required())

    def test_required_webhook_without_app_secret_is_not_configured(self):
        with patch.dict(
            os.environ,
            {"WEBHOOK_SIGNATURE_REQUIRED": "true", "META_APP_SECRET": ""},
            clear=False,
        ):
            self.assertTrue(webhook_signature_required())
            self.assertFalse(webhook_signature_configured())

    def test_required_webhook_with_app_secret_is_configured(self):
        with patch.dict(
            os.environ,
            {"WEBHOOK_SIGNATURE_REQUIRED": "true", "META_APP_SECRET": "meta-secret"},
            clear=False,
        ):
            self.assertTrue(webhook_signature_required())
            self.assertTrue(webhook_signature_configured())


if __name__ == "__main__":
    unittest.main()
