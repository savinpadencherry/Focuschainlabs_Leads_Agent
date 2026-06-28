"""Canonical organization (tenant) registry for the shared multi-tenant app.

Cloud SQL holds one row per tenant in the `organizations` table; *this* module is
the application-side registry that the login screen and UI read from. It answers
three questions without touching the database:

  1. Which tenants exist?              → list_orgs()
  2. Which tenant does this user belong to, by email domain?  → resolve_org_for_email()
  3. How should this tenant be branded? → org_branding()

Why a config module rather than a DB lookup for domains/branding: these are
deploy-time facts (which companies use the app, their email domains, their
display names) the login path needs *before* any query, and they change rarely.
Keeping them in one small, env-overridable place keeps sign-in fast and lets the
same code render either brand.

Production override — set the ORG_CONFIG secret to a JSON list to replace the
built-in defaults wholesale:

    ORG_CONFIG = '''[
      {"id":"focuschainlabs","name":"FocusChain Labs","short_name":"FocusChain",
       "email_domains":["focuschainlabs.com"],
       "tagline":"prompt.intake() -> signals.scan -> outreach.deploy",
       "eyebrow":"FOCUSCHAIN LABS · LEAD AGENT"},
      {"id":"sn_realtors","name":"SN Realtors","short_name":"SN Realtors",
       "email_domains":["snrealtors.in"],
       "tagline":"premium homes -> matched buyers -> closed deals",
       "eyebrow":"SN REALTORS · LEAD DESK"}
    ]'''

Or, to only tweak domain routing without restating everything, set
ORG_EMAIL_DOMAINS to a JSON object mapping domain -> org id; it wins over the
per-org email_domains list:

    ORG_EMAIL_DOMAINS = '{"focuschainlabs.com":"focuschainlabs","sn.co.in":"sn_realtors"}'
"""

from __future__ import annotations

import json
import os
from typing import Any

# Tenant used for pre-multi-tenant data and as the safety fallback. Mirrors
# crm_store_postgres.DEFAULT_ORG_ID (kept as a literal here to avoid importing
# psycopg2 just to read a constant on the login path).
DEFAULT_ORG_ID = "default"

# Built-in defaults so the app works out-of-the-box for the two launch tenants.
# NOTE: the email_domains below are best-guesses — confirm the real Google
# Workspace domains and override via ORG_CONFIG / ORG_EMAIL_DOMAINS in secrets.
_BUILTIN_ORGS: list[dict[str, Any]] = [
    {
        "id": "focuschainlabs",
        "name": "FocusChain Labs",
        "short_name": "FocusChain",
        "email_domains": ["focuschainlabs.com"],
        "tagline": "prompt.intake()  →  signals.scan  →  outreach.deploy",
        "eyebrow": "FOCUSCHAIN LABS · LEAD AGENT",
    },
    {
        "id": "sn_realtors",
        "name": "SN Realtors",
        "short_name": "SN Realtors",
        "email_domains": ["snrealtors.in", "snrealtors.com"],
        "tagline": "premium homes  →  matched buyers  →  closed deals",
        "eyebrow": "SN REALTORS · LEAD DESK",
    },
]

# Branding shown when no org resolves (e.g. auth disabled in local dev). Neutral
# so an unconfigured deployment still looks intentional rather than broken.
_DEFAULT_BRANDING: dict[str, Any] = {
    "id": DEFAULT_ORG_ID,
    "name": "FocusChain Labs",
    "short_name": "FocusChain",
    "email_domains": [],
    "tagline": "prompt.intake()  →  signals.scan  →  outreach.deploy",
    "eyebrow": "FOCUSCHAIN LABS · LEAD AGENT",
}


def _normalize_org(raw: Any) -> dict[str, Any] | None:
    """Coerce one registry entry into a complete, lower-cased-domain org dict."""
    if not isinstance(raw, dict):
        return None
    org_id = str(raw.get("id") or "").strip()
    name = str(raw.get("name") or "").strip()
    if not org_id or not name:
        return None
    domains = raw.get("email_domains") or []
    if isinstance(domains, str):
        domains = [domains]
    clean_domains = [
        d.strip().lower().lstrip("@") for d in domains if isinstance(d, str) and d.strip()
    ]
    short = str(raw.get("short_name") or name).strip()
    return {
        "id": org_id,
        "name": name,
        "short_name": short,
        "email_domains": clean_domains,
        "tagline": str(raw.get("tagline") or _DEFAULT_BRANDING["tagline"]),
        "eyebrow": str(raw.get("eyebrow") or f"{name.upper()} · LEAD AGENT"),
    }


def list_orgs() -> list[dict[str, Any]]:
    """All configured tenants. ORG_CONFIG (JSON list) overrides the built-ins."""
    raw = (os.getenv("ORG_CONFIG") or "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                orgs = [o for o in (_normalize_org(x) for x in parsed) if o]
                if orgs:
                    return orgs
        except (json.JSONDecodeError, TypeError):
            pass
    return [_normalize_org(o) for o in _BUILTIN_ORGS]  # type: ignore[misc]


def get_org(org_id: str) -> dict[str, Any] | None:
    """The org dict for an id, or None if unknown."""
    oid = (org_id or "").strip()
    for org in list_orgs():
        if org["id"] == oid:
            return org
    return None


def _extra_domain_map() -> dict[str, str]:
    """Optional ORG_EMAIL_DOMAINS override: {domain: org_id}, lower-cased."""
    raw = (os.getenv("ORG_EMAIL_DOMAINS") or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    out: dict[str, str] = {}
    for domain, org_id in parsed.items():
        if isinstance(domain, str) and isinstance(org_id, str) and domain and org_id:
            out[domain.strip().lower().lstrip("@")] = org_id.strip()
    return out


def domain_of(email: str) -> str:
    """The lower-cased domain part of an email, or '' if malformed."""
    email = (email or "").strip().lower()
    if email.count("@") != 1:
        return ""
    return email.split("@", 1)[1]


def resolve_org_for_email(email: str) -> str | None:
    """Which tenant a signed-in user belongs to, by email domain.

    Returns the org id, or None if the domain isn't mapped to any tenant — the
    caller (auth) treats None as "access denied" so only known company domains
    get in. Resolution order: the ORG_EMAIL_DOMAINS override map first, then each
    org's own email_domains list.
    """
    domain = domain_of(email)
    if not domain:
        return None
    extra = _extra_domain_map()
    if domain in extra:
        return extra[domain]
    for org in list_orgs():
        if domain in org["email_domains"]:
            return org["id"]
    return None


def org_branding(org_id: str | None) -> dict[str, Any]:
    """Display fields (name, short_name, tagline, eyebrow) for an org.

    Always returns a complete dict — falls back to neutral default branding for
    an unknown/None org so the UI never has to None-check.
    """
    if org_id:
        org = get_org(org_id)
        if org:
            return org
    return dict(_DEFAULT_BRANDING)


def all_allowed_domains() -> list[str]:
    """Every domain that can sign in — for the 'use your company email' hint."""
    domains: list[str] = list(_extra_domain_map().keys())
    for org in list_orgs():
        for d in org["email_domains"]:
            if d not in domains:
                domains.append(d)
    return domains
