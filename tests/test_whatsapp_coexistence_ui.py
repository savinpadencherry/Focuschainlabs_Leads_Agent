import os
import sys
import types
import unittest
from unittest.mock import patch


# whatsapp_connect_ui only needs Streamlit objects while rendering. Provide a
# tiny import-time stub so these pure configuration helpers stay unit-testable in
# lightweight CI environments.
_streamlit = types.ModuleType("streamlit")
_streamlit.session_state = {}
_components_pkg = types.ModuleType("streamlit.components")
_components_v1 = types.ModuleType("streamlit.components.v1")
_components_v1.html = lambda *args, **kwargs: None
_streamlit.components = _components_pkg
_components_pkg.v1 = _components_v1
sys.modules.setdefault("streamlit", _streamlit)
sys.modules.setdefault("streamlit.components", _components_pkg)
sys.modules.setdefault("streamlit.components.v1", _components_v1)

from utils import org_config  # noqa: E402
import whatsapp_connect_ui as wa_ui  # noqa: E402


class WhatsAppCoexistenceUiTests(unittest.TestCase):
    def test_launcher_forces_business_app_coexistence_feature(self):
        with patch.object(
            wa_ui.es,
            "launcher_html",
            return_value="before featureType: '' after",
        ), patch.dict(os.environ, {}, clear=True):
            markup = wa_ui._coexistence_launcher_html("focuschainlabs")

        self.assertIn('featureType: "whatsapp_business_app_onboarding"', markup)
        self.assertNotIn("featureType: ''", markup)

    def test_feature_type_can_be_overridden(self):
        with patch.object(
            wa_ui.es,
            "launcher_html",
            return_value="featureType: ''",
        ), patch.dict(
            os.environ,
            {"META_EMBEDDED_SIGNUP_FEATURE_TYPE": "custom_feature"},
            clear=True,
        ):
            markup = wa_ui._coexistence_launcher_html("focuschainlabs")

        self.assertIn('featureType: "custom_feature"', markup)

    def test_missing_settings_are_named_for_admin(self):
        with patch.dict(
            os.environ,
            {
                "META_APP_ID": "123",
                "META_CONFIG_ID": "",
                "WA_CONNECT_SECRET": "secret",
                "WEBHOOK_PUBLIC_URL": "",
            },
            clear=True,
        ):
            self.assertEqual(
                wa_ui._missing_embedded_signup_settings(),
                ["META_CONFIG_ID", "WEBHOOK_PUBLIC_URL"],
            )

    def test_srikant_can_operate_connection_setup(self):
        with patch.dict(os.environ, {}, clear=True):
            membership = org_config.resolve_membership("srikant@focuschainlabs.com")

        self.assertEqual(membership["organization_id"], "focuschainlabs")
        self.assertEqual(membership["role"], "admin")


if __name__ == "__main__":
    unittest.main()
