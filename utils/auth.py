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
_SESSION_ROLE_KEY = "auth_role"


# ── Capability / configuration probes ─────────────────────────────────────────
def login_supported() -> bool:
    """True if this Streamlit build exposes native OIDC (st.login)."""
    return hasattr(st, "login")


def _auth_secrets_present() -> bool:
    try:
        return "auth" in st.secrets
    except Exception:
        return False


def auth_required() -> bool:
    """Production fail-closed switch. When AUTH_REQUIRED is set, the app must
    NEVER run unauthenticated — even if [auth] is missing it refuses to serve
    rather than dropping into single-tenant dev mode."""
    return (os.getenv("AUTH_REQUIRED") or "").strip().lower() in ("1", "true", "yes")


def _properly_configured() -> bool:
    return login_supported() and _auth_secrets_present()


def auth_enabled() -> bool:
    """Whether to gate the app behind Google sign-in.

    Always on when AUTH_REQUIRED is set. Otherwise on when [auth] is configured;
    off (single-tenant dev mode) for local dev / CI, or when AUTH_DISABLED is set.
    """
    if auth_required():
        return True
    if (os.getenv("AUTH_DISABLED") or "").strip().lower() in ("1", "true", "yes"):
        return False
    return _properly_configured()


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


def active_role() -> str:
    """The signed-in user's role. Dev mode (auth off) is treated as admin so a
    contributor can exercise every feature locally; under auth, missing = member."""
    stored = (st.session_state.get(_SESSION_ROLE_KEY) or "").strip()
    if stored:
        return stored
    return org_config.ROLE_ADMIN if not auth_enabled() else org_config.ROLE_MEMBER


def is_admin() -> bool:
    return active_role() == org_config.ROLE_ADMIN


# ── The gate ──────────────────────────────────────────────────────────────────
def require_auth() -> None:
    """Block the app until an invited user is signed in.

    Call once near the top of the app, before any view renders. Renders the
    login / access-denied / config screens and st.stop()s when the user isn't
    allowed through; otherwise stores the resolved tenant + role in session.
    """
    if not auth_enabled():
        # Dev / CI: no gate. Pin the session to the dev tenant so org-scoped
        # queries behave exactly as they will in production.
        st.session_state.setdefault(_SESSION_ORG_KEY, active_org_id())
        return

    # AUTH_REQUIRED is set but sign-in isn't actually configured — fail closed
    # rather than letting anyone in or crashing on a broken login button.
    if not _properly_configured():
        _render_config_required_screen()
        st.stop()

    if not is_logged_in():
        _render_login_screen()
        st.stop()

    # Invite-only: access is granted per-email, never by domain alone.
    email = current_email()
    membership = org_config.resolve_membership(email)
    if not membership:
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

    st.session_state[_SESSION_ORG_KEY] = membership["organization_id"]
    st.session_state[_SESSION_ROLE_KEY] = membership["role"]
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
    for k in (_SESSION_ORG_KEY, _SESSION_EMAIL_KEY, _SESSION_NAME_KEY, _SESSION_ROLE_KEY,
              "crm_db", "crm_meta", "crm_sha", "crm_page", "crm_loaded_org"):
        st.session_state.pop(k, None)
    try:
        st.logout()
    except Exception:
        st.rerun()


# ── Screens ───────────────────────────────────────────────────────────────────
_LOGIN_CSS = """
<style>
/* Keep the authentication view focused and remove the normal app chrome. */
[data-testid="stSidebar"], [data-testid="collapsedControl"]{display:none!important;}
[data-testid="stHeader"]{background:transparent!important;}
[data-testid="stAppViewContainer"]{
  background:
    radial-gradient(circle at 18% 14%, rgba(46,139,77,.14), transparent 28%),
    radial-gradient(circle at 84% 18%, rgba(242,190,92,.12), transparent 24%),
    linear-gradient(145deg,#F9F6EE 0%,#F4F0E7 52%,#EFE9DC 100%)!important;
  min-height:100vh;
}
[data-testid="stMainBlockContainer"]{padding-top:clamp(34px,7vh,82px)!important;
  padding-bottom:48px!important;max-width:920px!important;}

.auth-wrap{position:relative;max-width:520px;margin:0 auto;text-align:center;
  animation:authFadeUp .75s cubic-bezier(.16,1,.3,1) both;}
.auth-wrap::before,.auth-wrap::after{content:"";position:absolute;border-radius:999px;
  filter:blur(2px);pointer-events:none;z-index:-1;}
.auth-wrap::before{width:210px;height:210px;left:-155px;top:20px;
  background:radial-gradient(circle,rgba(46,139,77,.13),rgba(46,139,77,0) 68%);
  animation:authDrift 7s ease-in-out infinite alternate;}
.auth-wrap::after{width:170px;height:170px;right:-130px;top:100px;
  background:radial-gradient(circle,rgba(183,121,31,.10),rgba(183,121,31,0) 68%);
  animation:authDrift 8.5s ease-in-out 1s infinite alternate-reverse;}
.auth-mark{position:relative;width:62px;height:62px;border-radius:19px;margin:0 auto 24px;
  background:linear-gradient(145deg,#228445,#36B765);display:grid;place-items:center;
  box-shadow:0 18px 42px rgba(46,139,77,.25),inset 0 1px 0 rgba(255,255,255,.35);
  animation:authMarkIn .8s cubic-bezier(.16,1,.3,1) .08s both;}
.auth-mark::before{content:"";position:absolute;inset:-8px;border-radius:25px;
  border:1px solid rgba(46,139,77,.18);animation:authPulse 3s ease-out infinite;}
.auth-mark::after{content:"";width:20px;height:20px;border-radius:50%;
  background:#F7F4EC;box-shadow:0 0 0 6px rgba(255,255,255,.10);}
.auth-eyebrow{font-family:'JetBrains Mono',monospace!important;font-size:10px;font-weight:700;
  letter-spacing:.34em;text-transform:uppercase;color:#2E8B4D;margin-bottom:15px;
  animation:authFadeUp .65s ease .12s both;}
.auth-title{font-family:'Bricolage Grotesque',sans-serif!important;
  font-size:clamp(38px,6vw,56px);font-weight:800;letter-spacing:-.045em;
  line-height:.98;color:#0F2A33;margin:0 0 16px;animation:authFadeUp .68s ease .18s both;}
.auth-title .accent{background:linear-gradient(110deg,#1F7D40,#35B663);
  -webkit-background-clip:text;background-clip:text;color:transparent;}
.auth-sub{font-family:'JetBrains Mono',monospace!important;font-size:12px;color:#60757B;
  letter-spacing:.025em;line-height:1.75;margin:0 auto 20px;max-width:430px;
  animation:authFadeUp .68s ease .24s both;}
.auth-trust-row{display:flex;justify-content:center;flex-wrap:wrap;gap:8px;margin:0 auto 8px;
  animation:authFadeUp .7s ease .3s both;}
.auth-pill{display:inline-flex;align-items:center;gap:7px;padding:7px 10px;border-radius:999px;
  border:1px solid rgba(15,42,51,.09);background:rgba(253,252,249,.66);
  backdrop-filter:blur(10px);font-family:'JetBrains Mono',monospace!important;
  color:#52686E;font-size:9.5px;font-weight:600;letter-spacing:.06em;}
.auth-pill-dot{width:6px;height:6px;border-radius:50%;background:#2E8B4D;
  box-shadow:0 0 0 3px rgba(46,139,77,.11);}

/* Real Streamlit container: unlike an opening/closing HTML div split across
   markdown calls, this actually contains the button and therefore cannot render
   as the mysterious empty white rectangle seen in production. */
div[class*="st-key-auth_login_card"]{max-width:430px;margin:24px auto 0!important;
  padding:22px!important;border:1px solid rgba(15,42,51,.10)!important;
  border-radius:22px!important;background:rgba(253,252,249,.78)!important;
  box-shadow:0 24px 70px rgba(15,42,51,.12),inset 0 1px 0 rgba(255,255,255,.85)!important;
  backdrop-filter:blur(18px);animation:authCardIn .78s cubic-bezier(.16,1,.3,1) .22s both;}
div[class*="st-key-auth_login_card"] [data-testid="stVerticalBlock"]{gap:12px!important;}
.auth-card-kicker{font-family:'JetBrains Mono',monospace!important;font-size:9.5px;
  font-weight:700;letter-spacing:.18em;text-transform:uppercase;color:#6B7F85;
  text-align:center;margin:0 0 2px;}
div[class*="st-key-auth_login_card"] .stButton>button{
  position:relative;min-height:54px!important;border:0!important;border-radius:14px!important;
  background:linear-gradient(110deg,#238646,#31A95A)!important;color:#fff!important;
  font-family:'Bricolage Grotesque',sans-serif!important;font-size:15px!important;
  font-weight:700!important;letter-spacing:.005em!important;
  box-shadow:0 12px 26px rgba(46,139,77,.24)!important;
  transition:transform .18s ease,box-shadow .18s ease,filter .18s ease!important;}
div[class*="st-key-auth_login_card"] .stButton>button:hover{
  transform:translateY(-2px)!important;box-shadow:0 17px 34px rgba(46,139,77,.31)!important;
  filter:saturate(1.06)!important;}
div[class*="st-key-auth_login_card"] .stButton>button:active{transform:translateY(0)!important;}
div[class*="st-key-auth_login_card"] .stButton>button::before{
  content:"G";display:inline-grid;place-items:center;width:24px;height:24px;margin-right:10px;
  border-radius:7px;background:#fff;color:#2E8B4D;font-size:13px;font-weight:800;
  box-shadow:0 2px 8px rgba(15,42,51,.12);}
.auth-card{background:rgba(253,252,249,.78);border:1px solid rgba(15,42,51,.10);
  border-radius:18px;padding:22px;box-shadow:0 18px 48px rgba(15,42,51,.10);
  backdrop-filter:blur(16px);}
.auth-hint{font-family:'JetBrains Mono',monospace!important;font-size:10px;color:#6B7F85;
  letter-spacing:.03em;text-align:center;line-height:1.6;margin:2px 4px 0;}
.auth-hint strong{color:#3C5158;font-weight:700;}
.auth-hint code{background:rgba(46,139,77,.10);color:#2E8B4D;border-radius:5px;
  padding:1px 6px;font-size:10px;}
.auth-foot{font-family:'JetBrains Mono',monospace!important;font-size:9px;color:#87979B;
  letter-spacing:.08em;text-align:center;margin-top:18px;animation:authFadeUp .7s ease .42s both;}

@keyframes authFadeUp{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
@keyframes authCardIn{from{opacity:0;transform:translateY(18px) scale(.985)}to{opacity:1;transform:none}}
@keyframes authMarkIn{from{opacity:0;transform:translateY(12px) rotate(-8deg) scale(.9)}to{opacity:1;transform:none}}
@keyframes authPulse{0%{opacity:.7;transform:scale(.88)}70%,100%{opacity:0;transform:scale(1.28)}}
@keyframes authDrift{from{transform:translate3d(0,0,0)}to{transform:translate3d(12px,14px,0)}}

@media(max-width:640px){
  [data-testid="stMainBlockContainer"]{padding:44px 20px 34px!important;}
  .auth-wrap{max-width:100%;}
  .auth-title{font-size:39px;}
  .auth-sub{font-size:11px;max-width:330px;}
  .auth-trust-row{gap:6px;}
  .auth-pill{font-size:8.7px;padding:6px 8px;}
  div[class*="st-key-auth_login_card"]{padding:18px!important;border-radius:18px!important;
    margin-top:20px!important;}
}
@media(prefers-reduced-motion:reduce){
  .auth-wrap,.auth-mark,.auth-eyebrow,.auth-title,.auth-sub,.auth-trust-row,.auth-foot,
  div[class*="st-key-auth_login_card"]{animation:none!important;}
  .auth-wrap::before,.auth-wrap::after,.auth-mark::before{animation:none!important;}
  div[class*="st-key-auth_login_card"] .stButton>button{transition:none!important;}
}
</style>
"""


def _render_login_screen() -> None:
    """Animated, on-brand Google sign-in screen without phantom containers."""
    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)
    st.markdown(
        """
        <div class="auth-wrap">
          <div class="auth-mark"></div>
          <div class="auth-eyebrow">FocusChain Labs · Secure Access</div>
          <h1 class="auth-title">Welcome <span class="accent">back</span></h1>
          <div class="auth-sub">Your leads, conversations and pipeline — securely
            separated by organisation. Sign in to enter your workspace.</div>
          <div class="auth-trust-row">
            <span class="auth-pill"><span class="auth-pill-dot"></span>Invite only</span>
            <span class="auth-pill"><span class="auth-pill-dot"></span>Google protected</span>
            <span class="auth-pill"><span class="auth-pill-dot"></span>Tenant isolated</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _, mid, _ = st.columns([1, 2.15, 1])
    with mid:
        # Use a real keyed Streamlit container so the visual card truly contains
        # the button and hint. The previous split HTML wrapper rendered as an
        # empty white rectangle because Streamlit markdown calls are separate DOMs.
        with st.container(key="auth_login_card"):
            st.markdown(
                '<div class="auth-card-kicker">Secure workspace access</div>',
                unsafe_allow_html=True,
            )
            if st.button(
                "Continue with Google",
                type="primary",
                use_container_width=True,
                key="auth_google_btn",
            ):
                _do_login()
            st.markdown(
                """
                <div class="auth-hint"><strong>Invite-only access.</strong> Use the
                Google account your organisation administrator approved.</div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown(
        '<div class="auth-foot">OIDC sign-in · encrypted session · organisation-scoped data</div>',
        unsafe_allow_html=True,
    )


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
    """Signed in, but the email isn't on any tenant's invite list."""
    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)
    safe_email = html.escape(email or "your account")
    st.markdown(
        f"""
        <div class="auth-wrap">
          <div class="auth-mark"></div>
          <div class="auth-eyebrow">FocusChain Labs · Access</div>
          <h1 class="auth-title">Not invited <span class="accent">yet</span></h1>
          <div class="auth-sub">{safe_email} isn't on an organisation's member
            list. Access is invite-only — ask your admin to add your address,
            or sign in with a different account.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        if st.button("Sign in with a different account", use_container_width=True,
                     key="auth_switch_btn"):
            logout()


def _render_config_required_screen() -> None:
    """AUTH_REQUIRED is set but the [auth] sign-in config is missing — fail closed."""
    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)
    st.markdown(
        """
        <div class="auth-wrap">
          <div class="auth-mark"></div>
          <div class="auth-eyebrow">FocusChain Labs · Locked</div>
          <h1 class="auth-title">Sign-in not <span class="accent">configured</span></h1>
          <div class="auth-sub">AUTH_REQUIRED is on but Google sign-in isn't set
            up yet, so the app is locked rather than running open. Add the [auth]
            section to the app's secrets and reload.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


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
