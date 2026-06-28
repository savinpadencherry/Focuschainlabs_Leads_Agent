import os
import tempfile
import unittest

from utils import intel_store


class IntelStoreTenancyTests(unittest.TestCase):
    """Briefings must be isolated per organization_id (no cross-tenant leak)."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig_base = intel_store._BASE_DIR
        intel_store._BASE_DIR = os.path.join(self._tmp, "intel")

    def tearDown(self):
        intel_store._BASE_DIR = self._orig_base

    def test_default_org_uses_legacy_path(self):
        self.assertTrue(intel_store._path("default").endswith("/briefings.json"))

    def test_distinct_orgs_get_distinct_files(self):
        self.assertNotEqual(
            intel_store._path("focuschainlabs"), intel_store._path("sn_realtors")
        )

    def test_briefings_do_not_leak_across_orgs(self):
        intel_store.upsert_briefings(
            [{"id": "a", "company": "Acme", "ran_at": "2026-01-01"}], "focuschainlabs"
        )
        intel_store.upsert_briefings(
            [{"id": "b", "company": "Beta", "ran_at": "2026-01-02"}], "sn_realtors"
        )
        foc = {b["id"] for b in intel_store.load_briefings("focuschainlabs")}
        snr = {b["id"] for b in intel_store.load_briefings("sn_realtors")}
        self.assertEqual(foc, {"a"})
        self.assertEqual(snr, {"b"})

    def test_mark_pushed_is_org_scoped(self):
        intel_store.upsert_briefings(
            [{"id": "x", "company": "Acme", "ran_at": "2026-01-01"}], "focuschainlabs"
        )
        intel_store.mark_pushed("x", "focuschainlabs")
        self.assertTrue(intel_store.load_briefings("focuschainlabs")[0]["pushed_to_crm"])
        # other org unaffected / empty
        self.assertEqual(intel_store.load_briefings("sn_realtors"), [])

    def test_path_sanitizes_org_id(self):
        # A hostile org id can't escape the intel dir.
        p = intel_store._path("../../etc/passwd")
        self.assertNotIn("..", p)


if __name__ == "__main__":
    unittest.main()
