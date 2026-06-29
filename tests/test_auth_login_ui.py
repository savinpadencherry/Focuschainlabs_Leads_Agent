"""Small regression checks for the production Google sign-in screen."""

from pathlib import Path
import unittest


AUTH_SOURCE = Path("utils/auth.py").read_text(encoding="utf-8")


class AuthLoginUiTests(unittest.TestCase):
    def test_login_uses_real_keyed_streamlit_container(self):
        self.assertIn('st.container(key="auth_login_card")', AUTH_SOURCE)

    def test_old_split_html_card_wrapper_is_gone(self):
        self.assertNotIn("st.markdown('<div class=\"auth-card\">'", AUTH_SOURCE)

    def test_motion_respects_reduced_motion_preference(self):
        self.assertIn("@media(prefers-reduced-motion:reduce)", AUTH_SOURCE)

    def test_login_screen_keeps_security_context_visible(self):
        self.assertIn("Invite only", AUTH_SOURCE)
        self.assertIn("Google protected", AUTH_SOURCE)
        self.assertIn("Tenant isolated", AUTH_SOURCE)


if __name__ == "__main__":
    unittest.main()
