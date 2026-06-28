"""WhatsApp Embedded Signup — official Meta onboarding, tenant-safe.

This is the compliant "scan a QR to connect WhatsApp" flow. The business clicks
Connect, Meta's popup opens, they sign in / scan with their WhatsApp Business
app, and Meta hands back an authorization `code` plus the `waba_id` /
`phone_number_id`. We exchange the code for a business access token (server-side)
and store the number under the right tenant.

The security problem this module solves: the browser must tell our backend which
organization the new number belongs to — but the browser must NOT be able to
*choose* an arbitrary org (that would let one tenant attach a number to another).
So the Streamlit app (which already knows the signed-in tenant, server-side)
mints a short-lived HMAC-signed `state` binding the organization_id. The webhook
verifies that signature before persisting — the org is never read from a plain
browser field.

Required configuration (shared by the Streamlit app and the webhook service):
  META_APP_ID         — Meta app id (public; used by the JS SDK)
  META_APP_SECRET     — Meta app secret (webhook only; for the code→token exchange)
  META_CONFIG_ID      — Embedded Signup configuration id (public; used by the SDK)
  WA_CONNECT_SECRET   — random shared secret for HMAC state signing
  WEBHOOK_PUBLIC_URL  — public base URL of the webhook service (where the popup POSTs)
  META_GRAPH_VERSION  — optional, defaults to a current Graph API version
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

_GRAPH_VERSION = (os.getenv("META_GRAPH_VERSION") or "v21.0").strip()
_GRAPH = f"https://graph.facebook.com/{_GRAPH_VERSION}"
_STATE_TTL_SECONDS = 600  # signed state is good for 10 minutes


# ── configuration probes ──────────────────────────────────────────────────────
def app_id() -> str:
    return (os.getenv("META_APP_ID") or "").strip()


def config_id() -> str:
    return (os.getenv("META_CONFIG_ID") or "").strip()


def _app_secret() -> str:
    return (os.getenv("META_APP_SECRET") or "").strip()


def _connect_secret() -> str:
    return (os.getenv("WA_CONNECT_SECRET") or "").strip()


def webhook_public_url() -> str:
    return (os.getenv("WEBHOOK_PUBLIC_URL") or "").strip().rstrip("/")


def embedded_signup_configured() -> bool:
    """True when the Streamlit side can launch the popup (public bits + secret)."""
    return bool(app_id() and config_id() and _connect_secret() and webhook_public_url())


def exchange_configured() -> bool:
    """True when the webhook side can complete the code→token exchange."""
    return bool(app_id() and _app_secret() and _connect_secret())


# ── HMAC-signed tenant state (anti-spoofing) ──────────────────────────────────
def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _sign(raw: str) -> str:
    return hmac.new(_connect_secret().encode(), raw.encode(), hashlib.sha256).hexdigest()


def make_state(organization_id: str, ttl: int = _STATE_TTL_SECONDS) -> str:
    """Mint a signed `state` that binds this connect attempt to one tenant."""
    if not _connect_secret():
        raise RuntimeError("WA_CONNECT_SECRET is not set")
    payload = {"org": organization_id, "exp": int(time.time()) + int(ttl)}
    raw = _b64u(json.dumps(payload, separators=(",", ":")).encode())
    return f"{raw}.{_sign(raw)}"


def verify_state(state: str) -> str | None:
    """Return the bound organization_id if the signed state is valid and unexpired,
    else None. Uses a constant-time compare so a forged signature can't be
    brute-forced by timing."""
    if not state or not _connect_secret() or state.count(".") != 1:
        return None
    raw, sig = state.split(".", 1)
    if not hmac.compare_digest(sig, _sign(raw)):
        return None
    try:
        payload = json.loads(_b64u_decode(raw))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or int(payload.get("exp", 0)) < int(time.time()):
        return None
    org = str(payload.get("org") or "").strip()
    return org or None


# ── Meta Graph calls (webhook side) ───────────────────────────────────────────
def exchange_code_for_token(code: str) -> str:
    """Trade the Embedded Signup authorization code for a business access token."""
    import requests

    resp = requests.get(
        f"{_GRAPH}/oauth/access_token",
        params={
            "client_id": app_id(),
            "client_secret": _app_secret(),
            "code": code,
        },
        timeout=30,
    )
    resp.raise_for_status()
    token = (resp.json() or {}).get("access_token") or ""
    if not token:
        raise RuntimeError("Meta did not return an access_token for the code")
    return token


def fetch_phone_numbers(waba_id: str, access_token: str) -> list[dict[str, Any]]:
    """Authoritative phone numbers for a WABA — so we trust Meta, not the browser,
    for phone_number_id / display name. Best-effort: returns [] on any error."""
    import requests

    try:
        resp = requests.get(
            f"{_GRAPH}/{waba_id}/phone_numbers",
            params={"access_token": access_token},
            timeout=30,
        )
        resp.raise_for_status()
        return list((resp.json() or {}).get("data") or [])
    except Exception:  # noqa: BLE001 - never crash the connect flow on this
        return []


def complete_connection(
    *,
    organization_id: str,
    code: str,
    waba_id: str,
    phone_number_id: str = "",
) -> dict[str, Any]:
    """Exchange the code, resolve the number from Meta, and persist it under the
    tenant. Returns the stored account summary. Raises on hard failures."""
    from utils import crm_store_postgres as pg

    token = exchange_code_for_token(code)

    display_name = ""
    phone_number = ""
    numbers = fetch_phone_numbers(waba_id, token) if waba_id else []
    if numbers:
        # Prefer the browser-named id if it's in the list; else take the first.
        chosen = next(
            (n for n in numbers if str(n.get("id")) == str(phone_number_id)), numbers[0]
        )
        phone_number_id = str(chosen.get("id") or phone_number_id)
        display_name = str(chosen.get("verified_name") or "")
        phone_number = str(chosen.get("display_phone_number") or "")

    if not phone_number_id:
        raise RuntimeError("No phone_number_id resolved from Embedded Signup")

    pg.upsert_whatsapp_account(
        {
            "phone_number_id": phone_number_id,
            "waba_id": waba_id,
            "access_token": token,
            "display_name": display_name,
            "phone_number": phone_number,
        },
        organization_id,
    )
    return {
        "phone_number_id": phone_number_id,
        "waba_id": waba_id,
        "display_name": display_name,
        "phone_number": phone_number,
        "organization_id": organization_id,
    }


# ── Front-end launcher (Streamlit side) ───────────────────────────────────────
def launcher_html(organization_id: str, *, height: int = 220) -> str:
    """The Facebook-SDK Embedded Signup button, bound to this tenant via signed
    state. Rendered with st.components.v1.html. On success it POSTs the code +
    signed state to the webhook's /connect/whatsapp endpoint."""
    state = make_state(organization_id)
    post_url = f"{webhook_public_url()}/connect/whatsapp"
    return f"""
<div style="font-family:'Bricolage Grotesque',-apple-system,sans-serif;">
  <button id="wa-connect" style="background:#2E8B4D;color:#fff;border:none;
    border-radius:8px;padding:12px 20px;font-size:15px;font-weight:600;
    cursor:pointer;box-shadow:0 2px 8px rgba(46,139,77,.28);">
    Connect WhatsApp
  </button>
  <div id="wa-status" style="margin-top:12px;font-size:13px;color:#3C5158;"></div>
</div>
<script>
  var SIGNUP = {{
    appId: {json.dumps(app_id())},
    configId: {json.dumps(config_id())},
    state: {json.dumps(state)},
    postUrl: {json.dumps(post_url)},
    graphVersion: {json.dumps(_GRAPH_VERSION)}
  }};
  var WA = {{}};
  window.addEventListener('message', function(e) {{
    if (typeof e.origin !== 'string' || e.origin.indexOf('facebook.com') === -1) return;
    try {{
      var d = JSON.parse(e.data);
      if (d.type === 'WA_EMBEDDED_SIGNUP' && d.event === 'FINISH') {{ WA = d.data || {{}}; }}
    }} catch (err) {{}}
  }});
  window.fbAsyncInit = function() {{
    FB.init({{appId: SIGNUP.appId, autoLogAppEvents: true, xfbml: true, version: SIGNUP.graphVersion}});
  }};
  (function(d, s, id) {{
    if (d.getElementById(id)) return;
    var js = d.createElement(s); js.id = id;
    js.src = "https://connect.facebook.net/en_US/sdk.js";
    d.getElementsByTagName('head')[0].appendChild(js);
  }}(document, 'script', 'facebook-jssdk'));
  document.getElementById('wa-connect').onclick = function() {{
    var statusEl = document.getElementById('wa-status');
    if (typeof FB === 'undefined') {{ statusEl.innerText = 'Loading Meta SDK… try again in a moment.'; return; }}
    FB.login(function(resp) {{
      if (!resp.authResponse || !resp.authResponse.code) {{ statusEl.innerText = 'Sign-up cancelled.'; return; }}
      statusEl.innerText = 'Finishing connection…';
      fetch(SIGNUP.postUrl, {{
        method: 'POST', headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{
          code: resp.authResponse.code, state: SIGNUP.state,
          waba_id: WA.waba_id || '', phone_number_id: WA.phone_number_id || ''
        }})
      }}).then(function(r) {{ return r.json(); }})
        .then(function(j) {{
          statusEl.innerText = j && j.ok
            ? '✓ Connected ' + (j.phone_number || j.phone_number_id || '') + ' — reload to see it.'
            : 'Could not connect: ' + ((j && j.error) || 'unknown error');
        }}).catch(function() {{ statusEl.innerText = 'Network error completing connection.'; }});
    }}, {{config_id: SIGNUP.configId, response_type: 'code', override_default_response_type: true,
         extras: {{setup: {{}}, featureType: '', sessionInfoVersion: '3'}}}});
  }};
</script>
"""
