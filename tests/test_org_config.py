import json
import os
import unittest
from unittest.mock import patch

from utils import org_config


class _EnvBase(unittest.TestCase):
    def setUp(self):
        self._keys = ("ORG_CONFIG", "ORG_EMAIL_DOMAINS")
        self._backup = {k: os.environ.get(k) for k in self._keys}
        for k in self._keys:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class BuiltinOrgTests(_EnvBase):
    def test_builtins_present(self):
        ids = {o["id"] for o in org_config.list_orgs()}
        self.assertIn("focuschainlabs", ids)
        self.assertIn("sn_realtors", ids)

    def test_every_org_has_complete_branding(self):
        for o in org_config.list_orgs():
            for field in ("id", "name", "short_name", "tagline", "eyebrow", "email_domains"):
                self.assertIn(field, o)

    def test_domain_resolves_to_focuschainlabs(self):
        self.assertEqual(
            org_config.resolve_org_for_email("anyone@focuschainlabs.com"), "focuschainlabs"
        )

    def test_sn_realtors_has_no_domain(self):
        # SN Realtors users are on personal Gmail — domain resolution must not
        # grant access (membership does). focuschainlabs domain still hints.
        self.assertIsNone(org_config.resolve_org_for_email("owner@snrealtors.in"))

    def test_resolution_is_case_insensitive(self):
        self.assertEqual(
            org_config.resolve_org_for_email("SAVIN@FocusChainLabs.COM"), "focuschainlabs"
        )

    def test_unknown_domain_denied(self):
        self.assertIsNone(org_config.resolve_org_for_email("someone@gmail.com"))

    def test_malformed_email_denied(self):
        for bad in ("", "no-at-sign", "two@@at.com", None):
            self.assertIsNone(org_config.resolve_org_for_email(bad))  # type: ignore[arg-type]


class BrandingTests(_EnvBase):
    def test_known_org_branding(self):
        brand = org_config.org_branding("sn_realtors")
        self.assertEqual(brand["name"], "SN Realtors")

    def test_unknown_org_falls_back_to_default_branding(self):
        brand = org_config.org_branding("does-not-exist")
        self.assertTrue(brand["name"])
        self.assertEqual(brand["id"], org_config.DEFAULT_ORG_ID)

    def test_none_org_branding_is_complete(self):
        brand = org_config.org_branding(None)
        for field in ("name", "short_name", "tagline", "eyebrow"):
            self.assertIn(field, brand)


class EnvOverrideTests(_EnvBase):
    def test_org_config_env_replaces_builtins(self):
        os.environ["ORG_CONFIG"] = json.dumps([
            {"id": "acme", "name": "Acme Co", "email_domains": ["acme.test"]},
        ])
        ids = {o["id"] for o in org_config.list_orgs()}
        self.assertEqual(ids, {"acme"})
        self.assertEqual(org_config.resolve_org_for_email("x@acme.test"), "acme")
        # focuschain no longer configured -> denied
        self.assertIsNone(org_config.resolve_org_for_email("x@focuschainlabs.com"))

    def test_invalid_org_config_falls_back_to_builtins(self):
        os.environ["ORG_CONFIG"] = "{not valid json"
        ids = {o["id"] for o in org_config.list_orgs()}
        self.assertIn("focuschainlabs", ids)

    def test_org_config_entries_missing_id_or_name_are_dropped(self):
        os.environ["ORG_CONFIG"] = json.dumps([
            {"id": "ok", "name": "OK Co", "email_domains": ["ok.test"]},
            {"name": "No Id"},
            {"id": "no-name"},
        ])
        ids = {o["id"] for o in org_config.list_orgs()}
        self.assertEqual(ids, {"ok"})

    def test_email_domain_override_map_wins(self):
        os.environ["ORG_EMAIL_DOMAINS"] = json.dumps({"custom.io": "sn_realtors"})
        self.assertEqual(org_config.resolve_org_for_email("a@custom.io"), "sn_realtors")
        # built-in domains still resolve
        self.assertEqual(
            org_config.resolve_org_for_email("a@focuschainlabs.com"), "focuschainlabs"
        )

    def test_domains_normalized_strip_at_and_case(self):
        os.environ["ORG_CONFIG"] = json.dumps([
            {"id": "acme", "name": "Acme", "email_domains": ["@ACME.TEST"]},
        ])
        self.assertEqual(org_config.resolve_org_for_email("x@acme.test"), "acme")

    def test_all_allowed_domains_lists_configured_domains(self):
        domains = org_config.all_allowed_domains()
        self.assertIn("focuschainlabs.com", domains)


class MembershipTests(_EnvBase):
    def setUp(self):
        super().setUp()
        self._mkey = os.environ.get("ORG_MEMBERS")
        os.environ.pop("ORG_MEMBERS", None)

    def tearDown(self):
        if self._mkey is None:
            os.environ.pop("ORG_MEMBERS", None)
        else:
            os.environ["ORG_MEMBERS"] = self._mkey
        super().tearDown()

    def test_known_members_resolve_with_org_and_role(self):
        m = org_config.resolve_membership("savin@focuschainlabs.com")
        self.assertEqual(m["organization_id"], "focuschainlabs")
        self.assertEqual(m["role"], "admin")
        m2 = org_config.resolve_membership("bhaskar@focuschainlabs.com")
        self.assertEqual(m2["organization_id"], "focuschainlabs")
        self.assertEqual(m2["role"], "member")

    def test_sn_realtors_gmail_members_resolve(self):
        m = org_config.resolve_membership("surajmetgud@gmail.com")
        self.assertEqual(m["organization_id"], "sn_realtors")
        self.assertEqual(m["role"], "admin")
        self.assertEqual(
            org_config.resolve_membership("suhassalgatti71@gmail.com")["organization_id"],
            "sn_realtors",
        )

    def test_membership_is_case_insensitive(self):
        self.assertEqual(
            org_config.resolve_membership("Savin@FocusChainLabs.com")["organization_id"],
            "focuschainlabs",
        )

    def test_non_member_denied_even_with_matching_domain(self):
        # A focuschainlabs.com address NOT on the invite list gets no access —
        # domain match alone must not grant entry.
        self.assertIsNone(org_config.resolve_membership("stranger@focuschainlabs.com"))

    def test_unknown_email_denied(self):
        self.assertIsNone(org_config.resolve_membership("random@gmail.com"))
        self.assertIsNone(org_config.resolve_membership(""))

    def test_org_members_env_override(self):
        import json
        os.environ["ORG_MEMBERS"] = json.dumps([
            {"email": "new@acme.test", "org": "acme", "role": "admin"},
        ])
        self.assertEqual(
            org_config.resolve_membership("new@acme.test"),
            {"organization_id": "acme", "role": "admin", "email": "new@acme.test"},
        )
        # built-ins no longer apply once overridden
        self.assertIsNone(org_config.resolve_membership("savin@focuschainlabs.com"))

    def test_invalid_role_defaults_to_member(self):
        import json
        os.environ["ORG_MEMBERS"] = json.dumps([
            {"email": "x@acme.test", "org": "acme", "role": "superuser"},
        ])
        self.assertEqual(org_config.resolve_membership("x@acme.test")["role"], "member")


if __name__ == "__main__":
    unittest.main()
