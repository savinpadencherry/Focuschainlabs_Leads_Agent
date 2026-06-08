"""Test GitHub CRM persistence only."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


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

from utils.crm_store import github_configured, load_crm, save_crm
from utils.crm_models import display_name, normalize_contact, new_contact_id

db, meta = load_crm(force_remote=True)
print("github configured:", github_configured())
print("load:", meta.get("source"), "contacts:", len(db.get("contacts") or []))
if meta.get("error"):
    print("load error:", meta.get("error"))
    sys.exit(1)

c = normalize_contact({
    "id": new_contact_id(),
    "name": "GitHub Smoke Test",
    "phone": "9000000001",
    "company": "Test Co",
    "tags": ["test-script"],
    "notes": "Safe to delete — automated github smoke test",
})
db.setdefault("contacts", []).append(c)
r = save_crm(db, sha=meta.get("sha"), message="test: github CRM smoke")
print("save committed:", r.get("committed"))
if r.get("error"):
    print("save error:", r.get("error"))
    sys.exit(1)
print("OK saved:", display_name(c))
