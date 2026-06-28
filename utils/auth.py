"""Authentication + tenant resolution for the Streamlit app.

Wraps Streamlit's native OpenID Connect login (``st.login`` / ``st.user``,
available 1.42+) and turns a signed-in Google identity into a tenant:

    sign in with Google  →  st.user.email  →  org_config.resolve_org_for_email
                         →  organization_id stored in session  →  all CRM queries scoped

Design choices:
  • Tenant is derived from the *verified* email domain, never from anything the
    user can type. A domain we don't recognise is denied, so only known company
    accounts get in.
  • If OIDC isn't configured (local dev, CI, unit tests) auth is disabled and the
    app runs against a single dev tenant — so contributors don't need a Google
    client to boot the app. Set AUTH_DISABLED=true to force this off explicitly;
    set DEV_ORG_ID to choose which tenant dev mode lands in.
  • The resolved org id is written to ``st.session_state['crm_org_id']`` — the
    same key utils/tenancy already reads — so the rest of the app needs no
    knowledge of how the tenant was chosen.
"""

from __future__ import annotations

import os
import html

import streamlit as st

from utils import org_config

_SESSION_ORG_KEY = "crm_org_id"   # shared with utils/tenancy.active_org()
_SESSION_EMAIL_KEY = "auth_email"
_SESSION_NAME_KEY = "auth_name"


# ── Capability / configuration probes ─────────────────────────────────────────
def login_supported() -> bool:
    """True if this Streamlit build exposes native OIDC (st.login)."""
    return hasattr(st, "login")


def _auth_secrets_present() -> bool:
    try:
        return "auth" in st.secrets
    except Exception:
        return False


def auth_enabled() -> bool:
    """Whether to actually gate the app behind Google sign-in.

    Disabled when explicitly turned off, when the Streamlit build is too old, or
    when no [auth] secrets exist (local dev / CI) — in those cases the app runs
    in single-tenant dev mode instead of showing a broken login button.
    """
    if (os.getenv("AUTH_DISABLED") or "").strip().lower() in ("1", "true", "yes"):
        return False
    return login_supported() and _auth_secrets_present()


def _user():
    return getattr(st, "user", None) or getattr(st, "experimental_user", None)


def is_logged_in() -> bool:
    user = _user()
    if user is None:
        return False
    try:
        return bool(getattr(user, "is_logged_in", False))
    except Exception:
        return False


def current_email() -> str:
    user = _user()
    if user is None:
        return ""
    try:
        return (getattr(user, "email", "") or "").strip()
    except Exception:
        return ""


def current_name() -> str:
    user = _user()
    if user is None:
        return ""
    try:
        return (getattr(user, "name", "") or "").strip()
    except Exception:
        return ""


# ── Active tenant accessors (used across the UI) ──────────────────────────────
def active_org_id() -> str:
    """Organization id for the current session.

    In dev mode (auth disabled) this is DEV_ORG_ID or the default tenant; under
    real auth it's whatever require_auth() resolved and stored.
    """
    stored = (st.session_state.get(_SESSION_ORG_KEY) or "").strip()
    if stored:
        return stored
    if not auth_enabled():
        dev = (os.getenv("DEV_ORG_ID") or "").strip()
        if dev:
            return dev
        orgs = org_config.list_orgs()
        return orgs[0]["id"] if orgs else org_config.DEFAULT_ORG_ID
    return org_config.DEFAULT_ORG_ID


def active_brand() -> dict:
    """Branding dict (name, short_name, tagline, eyebrow) for the active org."""
    return org_config.org_branding(active_org_id())


# ── The gate ──────────────────────────────────────────────────────────────────
def require_auth() -> None:
    """Block the app until a known-domain user is signed in.

    Call once near the top of the app, before any view renders. Renders the
    login or access-denied screen and st.stop()s when the user isn't allowed
    through; otherwise stores the resolved tenant in session and returns.
    """
    if not auth_enabled():
        # Dev / CI: no gate. Pin the session to the dev tenant so org-scoped
        # queries behave exactly as they will in production.
        st.session_state.setdefault(_SESSION_ORG_KEY, active_org_id())
        return

    if not is_logged_in():
        _render_login_screen()
        st.stop()

    email = current_email()
    org_id = org_config.resolve_org_for_email(email)
    if not org_id:
        _render_denied_screen(email)
        st.stop()

    # Fail closed: multi-tenant isolation only holds on the shared Cloud SQL
    # backend (every row carries organization_id). If auth is on but Cloud SQL
    # isn't configured, load_crm would fall through to the GitHub-JSON / Supabase
    # backends, which have no per-tenant scoping — every org would read and write
    # the same store. Refuse rather than silently leak across tenants.
    if not _multitenant_backend_ready():
        _render_backend_error_screen()
        st.stop()

    st.session_state[_SESSION_ORG_KEY] = org_id
    st.session_state[_SESSION_EMAIL_KEY] = email
    st.session_state[_SESSION_NAME_KEY] = current_name()


def _multitenant_backend_ready() -> bool:
    """True when the org-scoped Cloud SQL backend is configured."""
    try:
        from utils import crm_store_postgres as pg

        return pg.postgres_configured()
    except Exception:
        return False


def logout() -> None:
    for k in (_SESSION_ORG_KEY, _SESSION_EMAIL_KEY, _SESSION_NAME_KEY,
              "crm_db", "crm_meta", "crm_sha", "crm_page", "crm_loaded_org"):
        st.session_state.pop(k, None)
    try:
        st.logout()
    except Exception:
        st.rerun()


# ── Screens ───────────────────────────────────────────────────────────────────
_LOGIN_CSS = """
<style>
.auth-wrap{max-width:420px;margin:8vh auto 0;text-align:center;
  animation:fadeUp .7s cubic-bezier(.16,1,.3,1) both;}
.auth-mark{width:54px;height:54px;border-radius:16px;margin:0 auto 22px;
  background:linear-gradient(135deg,#2E8B4D,#37A85C);
  box-shadow:0 12px 30px rgba(46,139,77,.28);display:flex;align-items:center;
  justify-content:center;}
.auth-mark::after{content:"";width:20px;height:20px;border-radius:50%;
  background:#F4F0E7;}
.auth-eyebrow{font-family:'JetBrains Mono',monospace;font-size:10px;font-weight:700;
  letter-spacing:.34em;text-transform:uppercase;color:#2E8B4D;margin-bottom:14px;}
.auth-title{font-family:'Bricolage Grotesque',sans-serif;font-size:34px;font-weight:800;
  letter-spacing:-.03em;line-height:1.04;color:#0F2A33;margin:0 0 10px;}
.auth-title .accent{color:#2E8B4D;}
.auth-sub{font-family:'JetBrains Mono',monospace;font-size:12px;color:#6B7F85;
  letter-spacing:.03em;line-height:1.7;margin:0 auto 26px;max-width:340px;}
.auth-card{background:#FDFCF9;border:1.5px solid rgba(15,42,51,.09);border-radius:18px;
  padding:30px 26px;box-shadow:0 14px 34px rgba(15,42,51,.10);}
.auth-hint{font-family:'JetBrains Mono',monospace;font-size:10.5px;color:#6B7F85;
  letter-spacing:.04em;margin-top:18px;line-height:1.6;}
.auth-hint code{background:rgba(46,139,77,.10);color:#2E8B4D;border-radius:5px;
  padding:1px 6px;font-size:10px;}
</style>
"""


def _render_login_screen() -> None:
    """Minimalist, on-brand Google sign-in screen."""
    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)
    domains = org_config.all_allowed_domains()
    hint = ""
    if domains:
        chips = " ".join(f"<code>@{html.escape(d)}</code>" for d in domains[:4])
        hint = f"<div class='auth-hint'>Sign in with your company account &nbsp;{chips}</div>"

    st.markdown(
        f"""
        <div class="auth-wrap">
          <div class="auth-mark"></div>
          <div class="auth-eyebrow">FocusChain Labs · Secure Access</div>
          <h1 class="auth-title">Welcome <span class="accent">back</span></h1>
          <div class="auth-sub">Your leads, your conversations, your pipeline —
            one organisation at a time. Sign in to continue.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        with st.container():
            st.markdown('<div class="auth-card">', unsafe_allow_html=True)
            if st.button("Continue with Google", type="primary",
                         use_container_width=True, key="auth_google_btn"):
                _do_login()
            st.markdown((hint or "") + "</div>", unsafe_allow_html=True)


def _do_login() -> None:
    """Kick off the OIDC redirect. Tries the named 'google' provider first."""
    try:
        st.login("google")
    except Exception:
        try:
            st.login()
        except Exception as exc:  # noqa: BLE001
            st.error(
                "Sign-in isn't configured yet. Add the [auth] section to "
                f"Streamlit secrets (Google OAuth). ({exc})"
            )


def _render_denied_screen(email: str) -> None:
    """Signed in, but the email domain maps to no tenant."""
    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)
    safe_email = html.escape(email or "your account")
    domains = ", ".join(f"@{d}" for d in org_config.all_allowed_domains()) or "an approved company domain"
    st.markdown(
        f"""
        <div class="auth-wrap">
          <div class="auth-mark"></div>
          <div class="auth-eyebrow">FocusChain Labs · Access</div>
          <h1 class="auth-title">No workspace <span class="accent">for {safe_email}</span></h1>
          <div class="auth-sub">This account isn't linked to an organisation.
            Access is limited to {html.escape(domains)}. Use your company email,
            or ask an admin to add your domain.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        if st.button("Sign in with a different account", use_container_width=True,
                     key="auth_switch_btn"):
            logout()


def _render_backend_error_screen() -> None:
    """Auth is on but the org-scoped Cloud SQL backend isn't configured."""
    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)
    st.markdown(
        """
        <div class="auth-wrap">
          <div class="auth-mark"></div>
          <div class="auth-eyebrow">FocusChain Labs · Configuration</div>
          <h1 class="auth-title">Almost <span class="accent">there</span></h1>
          <div class="auth-sub">Sign-in works, but the multi-tenant database
            isn't connected yet. To keep each organisation's data isolated, the
            app needs Cloud SQL configured before it can show any leads.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        st.markdown(
            """
            <div class="auth-card" style="text-align:left;">
              <div class="auth-hint" style="margin-top:0;">
                Set <code>CLOUD_SQL_CONNECTION_NAME</code> (Cloud Run) or
                <code>DATABASE_URL</code> (local), apply
                <code>db/schema_cloudsql.sql</code>, then reload. Until then the
                app stays locked so no tenant can read another's data.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Sign out", use_container_width=True, key="auth_backend_logout_btn"):
            logout()


def render_user_chip() -> None:
    """Compact identity + sign-out control for the sidebar drawer."""
    if not auth_enabled() or not is_logged_in():
        return
    name = st.session_state.get(_SESSION_NAME_KEY) or current_name() or current_email()
    brand = active_brand()
    st.markdown(
        f"""
        <div style="font-family:'JetBrains Mono',monospace;font-size:9px;font-weight:700;
          letter-spacing:.18em;text-transform:uppercase;color:#2E8B4D;margin:2px 0 2px;">
          {html.escape(brand['short_name'])}</div>
        <div style="font-family:'Bricolage Grotesque',sans-serif;font-size:12px;
          color:#3C5158;margin-bottom:6px;white-space:nowrap;overflow:hidden;
          text-overflow:ellipsis;">{html.escape(name or '')}</div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Sign out", key="auth_logout_btn", use_container_width=True):
        logout()
