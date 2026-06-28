"""Multi-tenant org switcher — pick which client's CRM you're working in.

Each "org" is a client (FocusChain Labs, SN Realtors, ...). An org can run on
either backend:
  • "github"   — JSON file in a GitHub repo (current default; zero extra setup)
  • "postgres" — its own Postgres database (for scale, e.g. SN Realtors' 10k records)

Configure orgs via the CRM_ORGS secret as a JSON array, e.g.:

    CRM_ORGS = '''[
      {"id": "focuschainlabs", "label": "FocusChain Labs", "backend": "github"},
      {"id": "sn_realtors",    "label": "SN Realtors",
       "backend": "postgres",  "database_url_env": "SN_REALTORS_DATABASE_URL"}
    ]'''
    SN_REALTORS_DATABASE_URL = "postgresql://user:pass@host/sn_realtors_db?sslmode=require"

If CRM_ORGS isn't set, the app behaves exactly as a single-tenant app (today's
default) — nothing changes for existing deployments.
"""

from __future__ import annotations

import json
import os
from typing import Any

import streamlit as st

_DEFAULT_ORG = {"id": "default", "label": "FocusChain Labs", "backend": "github"}


def list_orgs() -> list[dict[str, Any]]:
    raw = os.getenv("CRM_ORGS", "").strip()
    if not raw:
        return [_DEFAULT_ORG]
    try:
        parsed = json.loads(raw)
        orgs = [o for o in parsed if isinstance(o, dict) and o.get("id") and o.get("label")]
        return orgs or [_DEFAULT_ORG]
    except (json.JSONDecodeError, TypeError):
        return [_DEFAULT_ORG]


def active_org() -> dict[str, Any]:
    orgs = list_orgs()
    org_id = st.session_state.get("crm_org_id")
    for o in orgs:
        if o["id"] == org_id:
            return o
    if org_id:
        # The authenticated user's tenant may not appear in CRM_ORGS — the shared
        # multi-tenant model derives tenants from utils/org_config, not CRM_ORGS.
        # Honour that id on the shared Cloud SQL backend rather than snapping the
        # session back to the first configured org.
        from utils import org_config

        brand = org_config.org_branding(org_id)
        return {"id": org_id, "label": brand["name"], "backend": "github"}
    st.session_state["crm_org_id"] = orgs[0]["id"]
    return orgs[0]


def org_database_url(org: dict[str, Any]) -> str:
    """Resolve the Postgres connection string for a postgres-backend org."""
    env_name = org.get("database_url_env") or "DATABASE_URL"
    return (os.getenv(env_name) or "").strip()


def render_org_switcher() -> None:
    """Render the org picker. No-op (silent) when only one org is configured."""
    orgs = list_orgs()
    if len(orgs) <= 1:
        return

    org = active_org()
    labels = [o["label"] for o in orgs]
    ids = [o["id"] for o in orgs]
    current_idx = ids.index(org["id"]) if org["id"] in ids else 0

    st.markdown(
        """
        <style>
        .org-pill{font-family:'JetBrains Mono',monospace;font-size:11px;letter-spacing:.06em;
          text-transform:uppercase;color:#2E8B4D;margin-bottom:2px;}
        </style>
        <div class="org-pill">Working in</div>
        """,
        unsafe_allow_html=True,
    )
    picked = st.selectbox(
        "Organisation", labels, index=current_idx,
        label_visibility="collapsed", key="org_switcher_select",
    )
    picked_id = ids[labels.index(picked)]
    if picked_id != org["id"]:
        st.session_state["crm_org_id"] = picked_id
        # Switching tenants must drop the previously loaded CRM/cache.
        for k in ("crm_db", "crm_meta", "crm_sha", "crm_page"):
            st.session_state.pop(k, None)
        st.rerun()


def backend_badge_html(org: dict[str, Any]) -> str:
    backend = org.get("backend", "github")
    label = "Postgres" if backend == "postgres" else "GitHub"
    color = "#0D6E8C" if backend == "postgres" else "#2E8B4D"
    return (
        f'<span style="font-family:JetBrains Mono,monospace;font-size:10.5px;'
        f'letter-spacing:.05em;text-transform:uppercase;color:{color};'
        f'background:{color}1a;border:1px solid {color}40;border-radius:999px;'
        f'padding:3px 10px;">{org["label"]} · {label}</span>'
    )
