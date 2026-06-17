"""
GitHub-backed product feedback persistence.

Feedback from the CRM floater is stored at data/crm/feedback.json and synced
via the GitHub Contents API when GITHUB_TOKEN is configured (same pattern as
CRM contacts).
"""

from __future__ import annotations

import base64
import json
import os
import uuid
from typing import Any

import requests

from utils.crm_models import utc_now_iso

FEEDBACK_PATH = os.getenv("FEEDBACK_DATA_PATH", "data/crm/feedback.json")
GITHUB_API = "https://api.github.com"

FEEDBACK_CATEGORIES = ["bug", "idea", "praise", "other"]
CATEGORY_LABELS = {
    "bug": "Bug / issue",
    "idea": "Idea / improvement",
    "praise": "What's working",
    "other": "Other",
}


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


def empty_feedback_db() -> dict[str, Any]:
    return {"version": 1, "updated_at": utc_now_iso(), "entries": []}


def _normalize_db(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return empty_feedback_db()
    entries = raw.get("entries")
    if not isinstance(entries, list):
        raw["entries"] = []
    raw.setdefault("version", 1)
    raw.setdefault("updated_at", utc_now_iso())
    return raw


def _github_contents_url() -> str:
    repo = _github_repo()
    path = FEEDBACK_PATH.lstrip("/")
    return f"{GITHUB_API}/repos/{repo}/contents/{path}"


def _load_local() -> tuple[dict[str, Any], dict[str, Any]]:
    path = FEEDBACK_PATH
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = _normalize_db(json.load(f))
            return data, {"source": "local", "sha": None, "path": path}
        except Exception as exc:
            return empty_feedback_db(), {"source": "local", "sha": None, "path": path, "error": str(exc)}
    return empty_feedback_db(), {"source": "local", "sha": None, "path": path}


def _save_local(data: dict[str, Any]) -> dict[str, Any]:
    path = FEEDBACK_PATH
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    payload = _normalize_db(data)
    payload["updated_at"] = utc_now_iso()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return {"source": "local", "sha": None, "path": path, "committed": False}


def load_feedback(*, force_remote: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
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
                    decoded = base64.b64decode(body.get("content", "")).decode("utf-8")
                    data = _normalize_db(json.loads(decoded))
                    return data, {
                        "source": "github",
                        "sha": body.get("sha"),
                        "path": FEEDBACK_PATH,
                        "branch": _github_branch(),
                        "repo": _github_repo(),
                    }
                if resp.status_code == 404:
                    return empty_feedback_db(), {
                        "source": "github",
                        "sha": None,
                        "path": FEEDBACK_PATH,
                        "branch": _github_branch(),
                        "repo": _github_repo(),
                        "note": "Feedback file not in repo yet — will be created on first save",
                    }
                return empty_feedback_db(), {
                    "source": "github",
                    "sha": None,
                    "path": FEEDBACK_PATH,
                    "error": f"GitHub read failed ({resp.status_code}): {resp.text[:200]}",
                }
            except Exception as exc:
                if force_remote:
                    return empty_feedback_db(), {"source": "github", "sha": None, "error": str(exc)}

    return _load_local()


def save_feedback(
    data: dict[str, Any],
    *,
    sha: str | None = None,
    message: str = "Add product feedback",
) -> dict[str, Any]:
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
                "error": f"Couldn't reach GitHub (network issue). {'Saved locally.' if saved_locally else ''}".strip(),
            }

        if resp.status_code in (200, 201):
            result = resp.json()
            new_sha = (result.get("content") or {}).get("sha")
            try:
                _save_local(payload)
            except Exception:
                pass
            return {
                "source": "github",
                "sha": new_sha,
                "path": FEEDBACK_PATH,
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
                "error": "Someone else updated feedback — refresh and try again.",
            }

        try:
            _save_local(payload)
            saved_locally = True
        except Exception:
            saved_locally = False

        friendly = f"GitHub write failed ({resp.status_code}): {resp.text[:200]}"
        if saved_locally:
            friendly += " (Saved locally for this session.)"

        return {
            "source": "github",
            "sha": sha,
            "committed": False,
            "saved_locally": saved_locally,
            "error": friendly,
        }

    return _save_local(payload)


def normalize_entry(raw: dict[str, Any]) -> dict[str, Any]:
    category = (raw.get("category") or "other").strip().lower()
    if category not in FEEDBACK_CATEGORIES:
        category = "other"
    page = (raw.get("page") or "app").strip() or "app"
    page_label = (raw.get("page_label") or "").strip()
    return {
        "id": str(raw.get("id") or uuid.uuid4()),
        "created_at": raw.get("created_at") or utc_now_iso(),
        "message": (raw.get("message") or "").strip(),
        "category": category,
        "page": page,
        "page_label": page_label,
        "submitted_by": (raw.get("submitted_by") or "").strip(),
    }


def append_feedback(
    db: dict[str, Any],
    *,
    message: str,
    category: str = "other",
    page: str = "app",
    page_label: str = "",
    submitted_by: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    entry = normalize_entry({
        "message": message,
        "category": category,
        "page": page,
        "page_label": page_label,
        "submitted_by": submitted_by,
    })
    if not entry["message"]:
        return db, {"ok": False, "error": "Message is required."}

    entries = list(db.get("entries") or [])
    entries.append(entry)
    db["entries"] = entries
    db["updated_at"] = utc_now_iso()
    return db, {"ok": True, "entry": entry}
