"""Quick local smoke test for CRM AI intake + GitHub persistence."""
from __future__ import annotations

import json
import os
import sys

def _load_secrets() -> None:
    secrets_path = os.path.join(os.path.dirname(__file__), "..", ".streamlit", "secrets.toml")
    if not os.path.exists(secrets_path):
        return
    with open(secrets_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


_load_secrets()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.crm_intake_agent import parse_contact
from utils.crm_store import github_configured, load_crm, save_crm
from utils.crm_models import display_name, lead_to_contact, normalize_contact, new_contact_id


SAMPLE = (
    "Add Priya Nair, founder of Zenith Interiors, phone 9876543210, "
    "met at Mumbai expo, wants a demo next week for SN Realtors"
)


def main() -> int:
    print("=== CRM AI intake local test ===\n")

    if not os.getenv("GEMINI_API_KEY"):
        print("FAIL: GEMINI_API_KEY not loaded")
        return 1
    print(f"Gemini model: {os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')}")
    print(f"GitHub configured: {github_configured()}")

    print("\n1) parse_contact (Gemini)...")
    try:
        res = parse_contact(text=SAMPLE)
    except Exception as exc:
        print(f"FAIL parse_contact: {exc}")
        return 1

    fields = res.get("fields") or {}
    print(f"   ok={res.get('ok')} summary={res.get('summary', '')[:80]}")
    print(f"   name={fields.get('name')} company={fields.get('company')} phone={fields.get('phone')}")
    print(f"   email={fields.get('email')} client={fields.get('client')}")
    if res.get("missing"):
        print(f"   missing={res.get('missing')}")

    if not (fields.get("name") or fields.get("company")):
        print("FAIL: AI did not extract name/company")
        return 1
    if not (fields.get("phone") or fields.get("email")):
        print("FAIL: AI did not extract phone/email")
        return 1

    print("\n2) load_crm from GitHub...")
    db, meta = load_crm(force_remote=True)
    print(f"   source={meta.get('source')} contacts={len(db.get('contacts') or [])} sha={str(meta.get('sha', ''))[:12]}")

    print("\n3) save test contact to GitHub...")
    test_contact = normalize_contact(
        {
            **fields,
            "id": new_contact_id(),
            "source": "other",
            "tags": ["ai-intake", "test-script"],
            "notes": (fields.get("notes") or "") + " [local test — safe to delete]",
        }
    )
    db.setdefault("contacts", []).append(test_contact)
    result = save_crm(db, sha=meta.get("sha"), message="test: AI intake smoke test")
    if result.get("error"):
        print(f"FAIL save: {result.get('error')}")
        return 1
    print(f"   committed={result.get('committed')} source={result.get('source')}")
    print(f"   saved as: {display_name(test_contact)}")

    print("\nPASS — AI intake + GitHub save work locally.")
    print("Open http://localhost:8501 → CRM → Add with AI and run the same text in the UI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
