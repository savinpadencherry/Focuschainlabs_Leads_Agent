"""Auth gate tests. Streamlit isn't installed in CI, so we inject a minimal
fake module before importing utils.auth (the same trick the app's smoke test
uses). Covers AUTH_REQUIRED fail-closed, invite-only membership, and roles.
"""

import os
import sys
import types
import unittest


class _Stop(Exception):
    pass


_st = types.ModuleType("streamlit")
_st.session_state = {}


class _Secrets(dict):
    pass


_st.secrets = _Secrets()
_st.user = types.SimpleNamespace(is_logged_in=False, email="", name="")
_st.login = lambda *a, **k: None
_st.logout = lambda *a, **k: None
_st.stop = lambda: (_ for _ in ()).throw(_Stop())
_st.rerun = lambda *a, **k: None
_st.markdown = lambda *a, **k: None
_st.button = lambda *a, **k: False
_st.error = lambda *a, **k: None
_st.toast = lambda *a, **k: None


class _CM:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


_st.columns = lambda spec: [_CM() for _ in (spec if isinstance(spec, list) else range(spec))]
_st.container = lambda *a, **k: _CM()
sys.modules["streamlit"] = _st

from utils import auth  # noqa: E402


def _login(email: str, name: str = "User") -> None:
    _st.user = types.SimpleNamespace(is_logged_in=True, email=email, name=name)


class _Base(unittest.TestCase):
    _ENV = ("AUTH_REQUIRED", "AUTH_DISABLED", "DATABASE_URL",
            "CLOUD_SQL_CONNECTION_NAME", "DEV_ORG_ID", "ORG_MEMBERS")

    def setUp(self):
        _st.session_state.clear()
        _st.secrets.clear()
        _st.user = types.SimpleNamespace(is_logged_in=False, email="", name="")
        self._env = {k: os.environ.get(k) for k in self._ENV}
        for k in self._ENV:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class AuthRequiredTests(_Base):
    def test_auth_required_forces_enabled_even_without_secrets(self):
        os.environ["AUTH_REQUIRED"] = "true"
        self.assertTrue(auth.auth_enabled())

    def test_auth_required_but_unconfigured_fails_closed(self):
        os.environ["AUTH_REQUIRED"] = "true"
        # no [auth] secrets -> must stop on the config screen, never run open
        with self.assertRaises(_Stop):
            auth.require_auth()
        self.assertNotIn("crm_org_id", _st.session_state)

    def test_dev_mode_when_not_required_and_no_secrets(self):
        # No AUTH_REQUIRED, no secrets -> dev mode, no gate, admin role.
        auth.require_auth()
        self.assertFalse(auth.auth_enabled())
        self.assertTrue(auth.is_admin())

    def test_auth_disabled_overrides_secrets(self):
        os.environ["AUTH_DISABLED"] = "true"
        _st.secrets["auth"] = {"redirect_uri": "x"}
        self.assertFalse(auth.auth_enabled())


class MembershipGateTests(_Base):
    def _enable(self):
        _st.secrets["auth"] = {"redirect_uri": "x"}
        os.environ["DATABASE_URL"] = "postgresql://u:p@localhost/db"  # backend ready

    def test_admin_member_resolves_org_and_role(self):
        self._enable()
        _login("savin@focuschainlabs.com")
        auth.require_auth()
        self.assertEqual(_st.session_state["crm_org_id"], "focuschainlabs")
        self.assertEqual(auth.active_role(), "admin")
        self.assertTrue(auth.is_admin())

    def test_plain_member_is_not_admin(self):
        self._enable()
        _login("bhaskar@focuschainlabs.com")
        auth.require_auth()
        self.assertEqual(auth.active_role(), "member")
        self.assertFalse(auth.is_admin())

    def test_sn_realtors_gmail_member_allowed(self):
        self._enable()
        _login("surajmetgud@gmail.com")
        auth.require_auth()
        self.assertEqual(_st.session_state["crm_org_id"], "sn_realtors")

    def test_non_member_denied(self):
        self._enable()
        _login("intruder@focuschainlabs.com")  # domain matches, not invited
        with self.assertRaises(_Stop):
            auth.require_auth()
        self.assertNotIn("crm_org_id", _st.session_state)

    def test_backend_not_ready_fails_closed(self):
        _st.secrets["auth"] = {"redirect_uri": "x"}
        # DATABASE_URL intentionally unset -> Cloud SQL not configured
        _login("savin@focuschainlabs.com")
        with self.assertRaises(_Stop):
            auth.require_auth()
        self.assertNotIn("crm_org_id", _st.session_state)

    def test_not_logged_in_shows_login(self):
        self._enable()  # enabled but no user logged in
        with self.assertRaises(_Stop):
            auth.require_auth()


if __name__ == "__main__":
    unittest.main()
