import io
import json
import unittest
from contextlib import redirect_stdout

from utils import obs


class ObsTests(unittest.TestCase):
    def _emit(self, *args, **kwargs) -> dict:
        buf = io.StringIO()
        with redirect_stdout(buf):
            obs.log_event(*args, **kwargs)
        line = buf.getvalue().strip()
        return json.loads(line) if line else {}

    def test_emits_single_json_line_with_event(self):
        payload = self._emit("inbound_message", organization_id="sn_realtors", action="created")
        self.assertEqual(payload["event"], "inbound_message")
        self.assertEqual(payload["organization_id"], "sn_realtors")
        self.assertEqual(payload["action"], "created")
        self.assertEqual(payload["severity"], "INFO")

    def test_omits_none_fields_and_blank_org(self):
        payload = self._emit("daily_batch", organization_id=None, llm_calls=5, extra=None)
        self.assertNotIn("organization_id", payload)
        self.assertNotIn("extra", payload)
        self.assertEqual(payload["llm_calls"], 5)

    def test_custom_severity(self):
        payload = self._emit("oops", severity="ERROR")
        self.assertEqual(payload["severity"], "ERROR")

    def test_never_raises_on_unserializable(self):
        # default=str keeps it from blowing up on odd objects
        payload = self._emit("ev", organization_id="x", obj=object())
        self.assertEqual(payload["event"], "ev")


if __name__ == "__main__":
    unittest.main()
