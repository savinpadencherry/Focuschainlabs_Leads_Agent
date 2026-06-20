"""
GitHub-backed CRM persistence.

Streamlit Cloud's filesystem is ephemeral — CRM data is stored in the repo at
data/crm/contacts.json and synced via the GitHub Contents API when GITHUB_TOKEN
is configured. Local dev falls back to direct file read/write.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

import requests

from utils.crm_models import empty_crm_db, utc_now_iso


CRM_PATH = os.getenv("CRM_DATA_PATH", "data/crm/contacts.json")
GITHUB_API = "https://api.github.com"


def _github_token() -> str:
    return (os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_PAT") or "").strip()


def _github_repo() -> str:
    return (os.getenv("GITHUB_REPO") or "savinpadencherry/Focuschainlabs_Leads_Agent").strip()


def _github_branch() -> str:
    return (os.getenv("GITHUB_BRANCH") or "main").strip()


def github_configured() -> bool:
    return bool(_github_token() and _github_repo())


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_github_token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _normalize_db(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return empty_crm_db()
    contacts = raw.get("contacts")
    if not isinstance(contacts, list):
        raw["contacts"] = []
    custom_statuses = raw.get("custom_statuses")
    if not isinstance(custom_statuses, list):
        raw["custom_statuses"] = []
    raw.setdefault("version", 1)
    raw.setdefault("updated_at", utc_now_iso())
    return raw


def _load_local() -> tuple[dict[str, Any], dict[str, Any]]:
    path = CRM_PATH
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = _normalize_db(json.load(f))
            return data, {"source": "local", "sha": None, "path": path}
        except Exception as exc:
            return empty_crm_db(), {"source": "local", "sha": None, "path": path, "error": str(exc)}
    return empty_crm_db(), {"source": "local", "sha": None, "path": path}


def _save_local(data: dict[str, Any]) -> dict[str, Any]:
    path = CRM_PATH
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    payload = _normalize_db(data)
    payload["updated_at"] = utc_now_iso()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return {"source": "local", "sha": None, "path": path, "committed": False}


def _github_contents_url() -> str:
    repo = _github_repo()
    path = CRM_PATH.lstrip("/")
    return f"{GITHUB_API}/repos/{repo}/contents/{path}"


def _org_database_url(org: dict[str, Any] | None) -> str:
    if not org:
        return ""
    env_name = org.get("database_url_env") or "DATABASE_URL"
    return (os.getenv(env_name) or "").strip()


def _load_postgres(org: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    from utils import crm_store_pg as pg

    db_url = _org_database_url(org)
    label = org.get("label", org.get("id", "tenant"))
    if not db_url:
        env_name = org.get("database_url_env") or "DATABASE_URL"
        return empty_crm_db(), {
            "source": "postgres", "org": org.get("id"), "label": label,
            "error": f"{env_name} is not set for {label} — add its connection string to secrets.",
        }
    try:
        pg.init_schema(database_url=db_url)
        contacts = pg.load_all_contacts(database_url=db_url)
        data = _normalize_db({"contacts": contacts, "custom_statuses": []})
        return data, {
            "source": "postgres", "sha": None, "org": org.get("id"),
            "label": label, "count": len(contacts),
        }
    except Exception as exc:  # noqa: BLE001 - never crash the page on a DB hiccup
        return empty_crm_db(), {
            "source": "postgres", "org": org.get("id"), "label": label,
            "error": f"Postgres read failed for {label}: {exc}",
        }


def _save_postgres(data: dict[str, Any], org: dict[str, Any]) -> dict[str, Any]:
    from utils import crm_store_pg as pg

    db_url = _org_database_url(org)
    label = org.get("label", org.get("id", "tenant"))
    if not db_url:
        env_name = org.get("database_url_env") or "DATABASE_URL"
        return {
            "source": "postgres", "committed": False,
            "error": f"{env_name} is not set for {label} — add its connection string to secrets.",
        }
    payload = _normalize_db(data)
    payload["updated_at"] = utc_now_iso()
    try:
        pg.init_schema(database_url=db_url)
        n = pg.replace_all_contacts(payload.get("contacts") or [], database_url=db_url)
        return {
            "source": "postgres", "sha": None, "committed": True,
            "org": org.get("id"), "label": label, "count": n,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "source": "postgres", "committed": False,
            "error": f"Postgres write failed for {label}: {exc}",
        }


def _read_seed_contacts() -> list[dict[str, Any]]:
    """Existing leads to migrate into Supabase on first connect.

    Reads the repo-committed JSON (data/crm/contacts.json) that the GitHub
    backend has been using — the source of truth before the cut-over.
    """
    data, _ = _load_local()
    return [c for c in (data.get("contacts") or []) if isinstance(c, dict)]


def _load_supabase() -> tuple[dict[str, Any], dict[str, Any]]:
    from utils import crm_store_supabase as sb

    try:
        contacts = sb.load_all_contacts()
        migrated = 0
        # One-time migration: an empty table on first connect gets seeded from
        # the existing repo JSON. Upsert-by-id makes this safe to retry.
        if not contacts:
            seed = _read_seed_contacts()
            if seed:
                migrated = sb.bulk_upsert(seed)
                contacts = sb.load_all_contacts()
        data = _normalize_db({"contacts": contacts, "custom_statuses": []})
        return data, {
            "source": "supabase", "sha": None, "count": len(contacts),
            "migrated": migrated,
        }
    except Exception as exc:  # noqa: BLE001 - never crash the page on a DB hiccup
        return empty_crm_db(), {
            "source": "supabase", "sha": None,
            "error": (
                f"Supabase read failed: {exc}. Confirm SUPABASE_URL / SUPABASE_KEY "
                "are set and the shared `contacts` table exists (provisioned by the "
                "mobile app's supabase/schema.sql)."
            ),
        }


def _save_supabase(data: dict[str, Any]) -> dict[str, Any]:
    from utils import crm_store_supabase as sb

    payload = _normalize_db(data)
    payload["updated_at"] = utc_now_iso()
    try:
        n = sb.replace_all_contacts(payload.get("contacts") or [])
        return {"source": "supabase", "sha": None, "committed": True, "count": n}
    except Exception as exc:  # noqa: BLE001
        return {
            "source": "supabase", "committed": False,
            "error": (
                f"Supabase write failed: {exc}. Confirm SUPABASE_KEY can write to "
                "the shared `contacts` table (service-role key, or anon key under "
                "the UAT RLS policies)."
            ),
        }


def load_crm(
    *, force_remote: bool = False, org: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Load CRM database for the active org.

    Backend is chosen per-org:
      • org["backend"] == "postgres" — that tenant's own Postgres database
      • otherwise — GitHub-JSON (priority: GitHub API → local file → empty)
    """
    if org and org.get("backend") == "postgres":
        return _load_postgres(org)

    from utils import crm_store_supabase as sb
    if sb.supabase_configured():
        return _load_supabase()

    if github_configured() or force_remote:
        token = _github_token()
        if token:
            try:
                resp = requests.get(
                    _github_contents_url(),
                    headers=_headers(),
                    params={"ref": _github_branch()},
                    timeout=20,
                )
                if resp.status_code == 200:
                    body = resp.json()
                    content_b64 = body.get("content", "")
                    decoded = base64.b64decode(content_b64).decode("utf-8")
                    data = _normalize_db(json.loads(decoded))
                    return data, {
                        "source": "github",
                        "sha": body.get("sha"),
                        "path": CRM_PATH,
                        "branch": _github_branch(),
                        "repo": _github_repo(),
                    }
                if resp.status_code == 404:
                    return empty_crm_db(), {
                        "source": "github",
                        "sha": None,
                        "path": CRM_PATH,
                        "branch": _github_branch(),
                        "repo": _github_repo(),
                        "note": "CRM file not in repo yet — will be created on first save",
                    }
                return empty_crm_db(), {
                    "source": "github",
                    "sha": None,
                    "path": CRM_PATH,
                    "error": f"GitHub read failed ({resp.status_code}): {resp.text[:200]}",
                }
            except Exception as exc:
                if force_remote:
                    return empty_crm_db(), {"source": "github", "sha": None, "error": str(exc)}
                # Fall through to local on transient errors

    return _load_local()


def save_crm(
    data: dict[str, Any],
    *,
    sha: str | None = None,
    message: str = "Update CRM contacts",
    org: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Persist CRM database for the active org.

    Backend is chosen per-org:
      • org["backend"] == "postgres" — write to that tenant's Postgres database
      • otherwise — commit to GitHub (Contents API) so data survives reboots,
        with a local-file fallback when the write fails.
    """
    if org and org.get("backend") == "postgres":
        return _save_postgres(data, org)

    from utils import crm_store_supabase as sb
    if sb.supabase_configured():
        return _save_supabase(data)

    payload = _normalize_db(data)
    payload["updated_at"] = utc_now_iso()
    encoded = base64.b64encode(
        json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")

    if github_configured():
        body: dict[str, Any] = {
            "message": message,
            "content": encoded,
            "branch": _github_branch(),
        }
        if sha:
            body["sha"] = sha

        try:
            resp = requests.put(
                _github_contents_url(),
                headers=_headers(),
                json=body,
                timeout=30,
            )
        except requests.RequestException as exc:
            # Network/timeout — never crash; keep data locally for this session.
            try:
                _save_local(payload)
                saved_locally = True
            except Exception:
                saved_locally = False
            return {
                "source": "github",
                "sha": sha,
                "committed": False,
                "saved_locally": saved_locally,
                "error": (
                    "Couldn't reach GitHub (network issue). "
                    + ("Saved locally for this session." if saved_locally else "")
                ).strip(),
            }

        if resp.status_code in (200, 201):
            result = resp.json()
            new_sha = (result.get("content") or {}).get("sha")
            # Mirror to local file when running in dev
            try:
                _save_local(payload)
            except Exception:
                pass
            return {
                "source": "github",
                "sha": new_sha,
                "path": CRM_PATH,
                "committed": True,
                "repo": _github_repo(),
                "branch": _github_branch(),
            }

        if resp.status_code == 409:
            return {
                "source": "github",
                "sha": sha,
                "committed": False,
                "conflict": True,
                "error": "Someone else updated CRM — refresh and try again.",
            }

        # Write failed — keep the data safe locally so the user loses nothing,
        # and surface an actionable message rather than a raw API dump.
        try:
            _save_local(payload)
            saved_locally = True
        except Exception:
            saved_locally = False

        if resp.status_code in (401, 403):
            friendly = (
                "GitHub rejected the write — your token can't save to this repo. "
                "Give it 'Contents: Read and write' permission (fine-grained PAT) "
                "or the 'repo' scope (classic token), then update GITHUB_TOKEN in "
                "Streamlit secrets."
            )
        elif resp.status_code == 404:
            friendly = (
                "GitHub couldn't find the repo or path. Check GITHUB_REPO, "
                "GITHUB_BRANCH and CRM_DATA_PATH in your secrets."
            )
        else:
            friendly = f"GitHub write failed ({resp.status_code}): {resp.text[:200]}"

        if saved_locally:
            friendly += " (Saved locally for this session.)"

        return {
            "source": "github",
            "sha": sha,
            "committed": False,
            "saved_locally": saved_locally,
            "status_code": resp.status_code,
            "error": friendly,
        }

    return _save_local(payload)


def import_leads_to_crm(
    db: dict[str, Any],
    leads: list[dict[str, Any]],
    *,
    agent_run_id: str = "",
) -> tuple[dict[str, Any], dict[str, int]]:
    """Merge agent leads into CRM, deduping by fingerprint."""
    from utils.crm_models import contact_fingerprint, lead_to_contact, merge_contacts

    contacts = list(db.get("contacts") or [])
    index = {contact_fingerprint(c): i for i, c in enumerate(contacts)}

    stats = {"added": 0, "updated": 0, "skipped": 0}
    for lead in leads:
        incoming = lead_to_contact(lead, agent_run_id=agent_run_id)
        fp = contact_fingerprint(incoming)
        if not incoming.get("company") and not incoming.get("name") and not incoming.get("email"):
            stats["skipped"] += 1
            continue
        if fp in index:
            idx = index[fp]
            contacts[idx] = merge_contacts(contacts[idx], incoming)
            stats["updated"] += 1
        else:
            contacts.append(incoming)
            index[fp] = len(contacts) - 1
            stats["added"] += 1

    db["contacts"] = contacts
    db["updated_at"] = utc_now_iso()
    return db, stats
