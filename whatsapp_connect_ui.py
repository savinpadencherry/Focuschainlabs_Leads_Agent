"""WhatsApp connections panel for the CRM — connect numbers via Meta Embedded
Signup, list connected numbers, disconnect. Everything is scoped to the active
organization_id so each tenant only ever sees and manages its own numbers.
"""

from __future__ import annotations

import html
import json
import os

import streamlit as st
import streamlit.components.v1 as components

from utils import auth
from utils import wa_embedded_signup as es

_PANEL_CSS = """
<style>
.wa-conn-shell{display:flex;flex-direction:column;gap:14px;}
.wa-conn-hero{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;
  padding:16px 18px;border:1px solid rgba(15,42,51,.10);border-radius:16px;
  background:linear-gradient(145deg,#FDFCF9 0%,rgba(238,249,241,.88) 100%);
  box-shadow:0 10px 30px rgba(15,42,51,.06);}
.wa-conn-hero-copy{min-width:0;}
.wa-conn-eyebrow{font-family:'JetBrains Mono',monospace;font-size:9.5px;font-weight:800;
  letter-spacing:.16em;text-transform:uppercase;color:#2E8B4D;margin-bottom:5px;}
.wa-conn-title{font-family:'Bricolage Grotesque',sans-serif;font-size:19px;font-weight:800;
  color:#0F2A33;line-height:1.15;}
.wa-conn-sub{font-size:12.5px;color:#5D7278;line-height:1.55;margin-top:5px;max-width:650px;}
.wa-conn-badge{display:inline-flex;align-items:center;gap:7px;flex:none;padding:7px 10px;
  border-radius:999px;font-family:'JetBrains Mono',monospace;font-size:9.5px;font-weight:800;
  letter-spacing:.06em;text-transform:uppercase;border:1px solid rgba(15,42,51,.10);
  background:#fff;color:#6B7F85;white-space:nowrap;}
.wa-conn-badge.ready{color:#207642;background:rgba(46,139,77,.09);border-color:rgba(46,139,77,.22);}
.wa-conn-badge.waiting{color:#936116;background:rgba(183,121,31,.09);border-color:rgba(183,121,31,.22);}
.wa-conn-row{display:flex;align-items:center;justify-content:space-between;
  background:#FDFCF9;border:1.5px solid rgba(15,42,51,.09);border-radius:12px;
  padding:12px 16px;margin-bottom:8px;box-shadow:0 4px 14px rgba(15,42,51,.035);}
.wa-conn-name{font-family:'Bricolage Grotesque',sans-serif;font-weight:700;
  font-size:14px;color:#0F2A33;}
.wa-conn-meta{font-family:'JetBrains Mono',monospace;font-size:10.5px;
  color:#6B7F85;letter-spacing:.03em;margin-top:2px;overflow-wrap:anywhere;}
.wa-conn-dot{display:inline-block;width:7px;height:7px;border-radius:50%;
  background:#2E8B4D;margin-right:6px;box-shadow:0 0 0 3px rgba(46,139,77,.14);}
.wa-conn-hint{font-family:'JetBrains Mono',monospace;font-size:10.5px;
  color:#6B7F85;letter-spacing:.03em;line-height:1.6;}
.wa-conn-hint code{background:rgba(46,139,77,.10);color:#2E8B4D;border-radius:5px;
  padding:1px 6px;font-size:10px;}
.wa-conn-empty,.wa-conn-locked,.wa-conn-config{padding:14px 16px;border-radius:12px;
  font-size:12.5px;line-height:1.55;}
.wa-conn-empty{border:1px dashed rgba(15,42,51,.20);background:rgba(255,255,255,.48);color:#5D7278;}
.wa-conn-locked{border:1px solid rgba(183,121,31,.22);background:rgba(183,121,31,.08);color:#60491f;}
.wa-conn-config{border:1px solid rgba(169,61,61,.20);background:rgba(169,61,61,.07);color:#6f3030;}
.wa-conn-config code{background:#EDF7EF!important;color:#226B3D!important;border:1px solid rgba(46,139,77,.18);
  border-radius:6px;padding:2px 6px;box-shadow:none!important;}
.wa-config-list{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0 8px;}
.wa-config-chip{display:inline-flex;align-items:center;padding:5px 8px;border-radius:8px;
  background:#EDF7EF;color:#226B3D;border:1px solid rgba(46,139,77,.18);
  font-family:'JetBrains Mono',monospace;font-size:10px;font-weight:750;letter-spacing:.035em;}
.wa-conn-section-title{font-family:'Bricolage Grotesque',sans-serif;font-size:14px;
  font-weight:800;color:#0F2A33;margin:2px 0 7px;}

/* Trigger buttons: force the light CRM palette even when the OS/browser uses dark mode. */
[data-testid="stPopover"] button,
[data-testid="stPopoverButton"] button{
  background:#FDFCF9!important;color:#0F2A33!important;
  -webkit-text-fill-color:#0F2A33!important;border:1.5px solid rgba(15,42,51,.16)!important;
  box-shadow:0 2px 8px rgba(15,42,51,.05)!important;}
[data-testid="stPopover"] button p,
[data-testid="stPopover"] button span,
[data-testid="stPopoverButton"] button p,
[data-testid="stPopoverButton"] button span{color:inherit!important;-webkit-text-fill-color:inherit!important;}
[data-testid="stPopover"] button svg,
[data-testid="stPopoverButton"] button svg{fill:#0F2A33!important;color:#0F2A33!important;}
[data-testid="stPopover"] button:hover,
[data-testid="stPopoverButton"] button:hover{background:#EFEADE!important;border-color:rgba(15,42,51,.24)!important;}
[data-testid="stPopover"] button:disabled,
[data-testid="stPopoverButton"] button:disabled{background:#F1EDE4!important;color:#7A898D!important;
  -webkit-text-fill-color:#7A898D!important;opacity:.72!important;}
[data-testid="stPopover"] button[data-testid="stBaseButton-primary"]{
  background:#2E8B4D!important;color:#fff!important;-webkit-text-fill-color:#fff!important;
  border-color:#2E8B4D!important;}
[data-testid="stPopover"] button[data-testid="stBaseButton-primary"] *{color:#fff!important;-webkit-text-fill-color:#fff!important;}

/* Expanded compose/delete popovers are body-level portals. */
[data-testid="stPopoverBody"],
[data-testid="stPopoverBody"]>div,
[data-baseweb="popover"] [data-testid="stPopoverBody"]{
  background:linear-gradient(180deg,#FDFCF9 0%,#F5F1E8 100%)!important;
  color:#0F2A33!important;border:1px solid rgba(15,42,51,.14)!important;
  border-radius:16px!important;box-shadow:0 18px 42px rgba(15,42,51,.16)!important;}
[data-testid="stPopoverBody"] [data-testid="stVerticalBlock"],
[data-testid="stPopoverBody"] [data-testid="stElementContainer"],
[data-testid="stPopoverBody"] [data-testid="stMarkdownContainer"]{
  background:transparent!important;color:#0F2A33!important;}
[data-testid="stPopoverBody"] p,
[data-testid="stPopoverBody"] label,
[data-testid="stPopoverBody"] small,
[data-testid="stPopoverBody"] [data-testid="stCaptionContainer"]{
  color:#0F2A33!important;-webkit-text-fill-color:#0F2A33!important;}
[data-baseweb="popover"] [data-popper-arrow]::before,
[data-baseweb="popover"] [data-popper-arrow]::after{
  background:#FDFCF9!important;border-color:rgba(15,42,51,.14)!important;}

/* The remaining black strip in the screenshots is the button help tooltip, not
   a permanent layout block. BaseWeb gives it a dark surface in dark mode. */
[data-baseweb="tooltip"],
[data-baseweb="tooltip"]>div,
[data-testid="stTooltipContent"],
[role="tooltip"]{
  background:#FDFCF9!important;color:#0F2A33!important;
  -webkit-text-fill-color:#0F2A33!important;border:1px solid rgba(15,42,51,.16)!important;
  border-radius:10px!important;box-shadow:0 10px 26px rgba(15,42,51,.15)!important;}
[data-baseweb="tooltip"] *,
[data-testid="stTooltipContent"] *,
[role="tooltip"] *{color:#0F2A33!important;-webkit-text-fill-color:#0F2A33!important;}
[data-baseweb="tooltip"] [data-popper-arrow]::before,
[role="tooltip"] [data-popper-arrow]::before{background:#FDFCF9!important;}

/* Toast markup differs between Streamlit releases. */
[data-testid="stToastContainer"]>div,
[data-testid="stToastContainer"] [role="alert"],
[data-testid="stToast"],
[data-testid="stToast"]>div,
[data-baseweb="toast"],
[data-baseweb="notification"]{
  background:#FDFCF9!important;color:#0F2A33!important;
  border:1px solid rgba(15,42,51,.14)!important;border-radius:12px!important;
  box-shadow:0 14px 34px rgba(15,42,51,.16)!important;}
[data-testid="stToastContainer"] *,
[data-testid="stToast"] *,
[data-baseweb="toast"] *,
[data-baseweb="notification"] *{color:#0F2A33!important;-webkit-text-fill-color:#0F2A33!important;}
[data-testid="stToastContainer"] svg,
[data-testid="stToast"] svg,
[data-baseweb="toast"] svg,
[data-baseweb="notification"] svg{fill:#0F2A33!important;color:#0F2A33!important;}

/* Password reveal control and input end-adornments were the other black square. */
[data-testid="stTextInput"] [data-baseweb="input"],
[data-testid="stTextInput"] [data-baseweb="input"]>div,
[data-testid="stTextInput"] [data-baseweb="base-input"]{
  background:#fff!important;color:#0F2A33!important;}
[data-testid="stTextInput"] button,
[data-testid="stTextInput"] [role="button"],
button[aria-label*="password" i],
button[title*="password" i]{
  background:#FDFCF9!important;color:#0F2A33!important;
  -webkit-text-fill-color:#0F2A33!important;border-color:rgba(15,42,51,.14)!important;
  box-shadow:none!important;}
[data-testid="stTextInput"] button svg,
[data-testid="stTextInput"] [role="button"] svg,
button[aria-label*="password" i] svg,
button[title*="password" i] svg{fill:#0F2A33!important;color:#0F2A33!important;}

@media(max-width:720px){
  .wa-conn-hero{flex-direction:column;padding:14px;}
  .wa-conn-badge{align-self:flex-start;}
  .wa-conn-row{padding:11px 12px;}
  [data-testid="stPopoverBody"]{max-width:calc(100vw - 24px)!important;max-height:70vh!important;overflow:auto!important;}
}
</style>
"""

_SENDER_SESSION_KEY = "wa_sender_phone_number_id"
_COEXISTENCE_FEATURE_TYPE = "whatsapp_business_app_onboarding"

# These are the five launch users who must be able to manage WhatsApp Business
# app coexistence even when the production ORG_MEMBERS secret still labels one
# of them as a normal member. This override is deliberately scoped to WhatsApp
# connection management; it does not grant unrelated organisation-admin powers.
_WHATSAPP_CONNECTION_ADMINS = frozenset({
    "savin@focuschainlabs.com",
    "bhaskar@focuschainlabs.com",
    "srikant@focuschainlabs.com",
    "surajmetgud@gmail.com",
    "suhassalgatti71@gmail.com",
})


def _can_manage_whatsapp_connections() -> bool:
    return auth.is_admin() or auth.current_email().strip().lower() in _WHATSAPP_CONNECTION_ADMINS


def _account_label(account: dict) -> str:
    name = account.get("display_name") or account.get("agent_name") or "WhatsApp number"
    number = account.get("phone_number") or account.get("phone_number_id") or ""
    return f"{name} · {number}"


def _missing_embedded_signup_settings() -> list[str]:
    required = {
        "META_APP_ID": os.getenv("META_APP_ID"),
        "META_CONFIG_ID": os.getenv("META_CONFIG_ID"),
        "WA_CONNECT_SECRET": os.getenv("WA_CONNECT_SECRET"),
        "WEBHOOK_PUBLIC_URL": os.getenv("WEBHOOK_PUBLIC_URL"),
    }
    return [name for name, value in required.items() if not str(value or "").strip()]


def _coexistence_launcher_html(organization_id: str) -> str:
    """Force Meta's WhatsApp Business app coexistence onboarding configuration."""
    markup = es.launcher_html(organization_id)
    feature = (
        os.getenv("META_EMBEDDED_SIGNUP_FEATURE_TYPE")
        or _COEXISTENCE_FEATURE_TYPE
    ).strip()
    return markup.replace("featureType: ''", f"featureType: {json.dumps(feature)}")


def _render_connection_summary(active_accounts: list[dict]) -> None:
    connected = len(active_accounts)
    if connected:
        badge_class = "ready"
        badge_text = f"{connected} connected"
        title = "WhatsApp is ready"
        subtitle = (
            "Customer messages can enter this organisation's CRM, and outbound messages "
            "can be sent from the selected business number."
        )
    else:
        badge_class = "waiting"
        badge_text = "Not connected"
        title = "Connect your WhatsApp Business number"
        subtitle = (
            "Use Meta's official coexistence setup. You keep using the WhatsApp Business "
            "mobile app while the same number is connected to this CRM."
        )

    st.markdown(
        "<div class='wa-conn-hero'>"
        "<div class='wa-conn-hero-copy'>"
        "<div class='wa-conn-eyebrow'>WhatsApp coexistence</div>"
        f"<div class='wa-conn-title'>{html.escape(title)}</div>"
        f"<div class='wa-conn-sub'>{html.escape(subtitle)}</div>"
        "</div>"
        f"<div class='wa-conn-badge {badge_class}'>{html.escape(badge_text)}</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def render_whatsapp_connections(organization_id: str) -> None:
    """Connected-numbers manager for one tenant. Safe to call on every CRM render."""
    from utils import crm_store_postgres as pg

    st.markdown(_PANEL_CSS, unsafe_allow_html=True)

    if not pg.postgres_configured():
        st.error(
            "WhatsApp connections need the shared Cloud SQL database. "
            "Set CLOUD_SQL_CONNECTION_NAME or DATABASE_URL before connecting a number."
        )
        return

    try:
        accounts = pg.load_whatsapp_accounts(organization_id)
    except Exception as exc:  # noqa: BLE001 - never crash the CRM page
        st.warning(f"Couldn't load WhatsApp numbers: {exc}")
        accounts = []

    is_admin = _can_manage_whatsapp_connections()
    active_accounts = [
        account
        for account in accounts
        if account.get("active", True)
        and (account.get("phone_number_id") or "").strip()
        and (account.get("access_token") or "").strip()
    ]

    selected_pid = str(st.session_state.get(_SENDER_SESSION_KEY) or "").strip()
    active_pids = [str(account.get("phone_number_id") or "").strip() for account in active_accounts]
    if selected_pid and selected_pid not in active_pids:
        st.session_state.pop(_SENDER_SESSION_KEY, None)
        selected_pid = ""

    if len(active_accounts) == 1:
        st.session_state[_SENDER_SESSION_KEY] = active_pids[0]
    elif len(active_accounts) > 1:
        if is_admin:
            by_pid = {str(account["phone_number_id"]): account for account in active_accounts}
            default_index = active_pids.index(selected_pid) if selected_pid in active_pids else 0
            picked = st.selectbox(
                "Sending number for broadcasts",
                active_pids,
                index=default_index,
                format_func=lambda pid: _account_label(by_pid[pid]),
                key="wa_sender_picker",
                help="Broadcasts use only this organisation's selected WhatsApp account.",
            )
            st.session_state[_SENDER_SESSION_KEY] = picked
        else:
            st.session_state.pop(_SENDER_SESSION_KEY, None)
            st.warning(
                "Multiple WhatsApp numbers are connected. An organisation admin must "
                "select the sending number before broadcasts can be sent."
            )
    else:
        st.session_state.pop(_SENDER_SESSION_KEY, None)

    _render_connection_summary(active_accounts)

    st.markdown(
        "<div class='wa-conn-hint' style='margin:2px 0 4px;'>"
        "To send a message, open a lead → <b>Activity</b> → <b>Send WhatsApp</b>, "
        "or select multiple leads for a broadcast.</div>",
        unsafe_allow_html=True,
    )

    st.markdown("<div class='wa-conn-section-title'>Connect a number</div>", unsafe_allow_html=True)
    if is_admin:
        if es.embedded_signup_configured():
            components.html(
                _coexistence_launcher_html(organization_id),
                height=258,
                scrolling=False,
            )
        else:
            missing_settings = _missing_embedded_signup_settings()
            missing_html = "".join(
                f"<span class='wa-config-chip'>{html.escape(name)}</span>"
                for name in missing_settings
            )
            st.markdown(
                "<div class='wa-conn-config'><b>Connect button is not configured yet.</b><br>"
                "The CRM Cloud Run service is missing these settings:"
                f"<div class='wa-config-list'>{missing_html}</div>"
                "The webhook service must also have <code>META_APP_SECRET</code> and the same "
                "<code>WA_CONNECT_SECRET</code>. Run <code>scripts/check_whatsapp_setup.sh</code> "
                "from Google Cloud Shell after deploying this revision."
                "</div>",
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            "<div class='wa-conn-locked'><b>Admin access required.</b><br>"
            "Connecting a business number grants CRM access to WhatsApp messages, so this "
            "action is limited to organisation admins. Ask an admin to open this panel and "
            "use the Connect WhatsApp button.</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div class='wa-conn-section-title'>Connected numbers</div>", unsafe_allow_html=True)
    if accounts:
        for account in accounts:
            label = account.get("display_name") or account.get("agent_name") or "WhatsApp number"
            number = account.get("phone_number") or account.get("phone_number_id") or ""
            row, btn = st.columns([5, 1])
            with row:
                st.markdown(
                    "<div class='wa-conn-row'><div>"
                    "<div class='wa-conn-name'><span class='wa-conn-dot'></span>"
                    f"{html.escape(str(label))}</div>"
                    f"<div class='wa-conn-meta'>{html.escape(str(number))} · "
                    f"id {html.escape(str(account.get('phone_number_id') or ''))}</div>"
                    "</div></div>",
                    unsafe_allow_html=True,
                )
            with btn:
                if is_admin and st.button(
                    "Disconnect",
                    key=f"wa_disc_{account.get('id')}",
                    help="Remove this number from this organisation's CRM.",
                ):
                    try:
                        pg.delete_whatsapp_account(account.get("id") or "", organization_id)
                        if str(account.get("phone_number_id") or "") == str(
                            st.session_state.get(_SENDER_SESSION_KEY) or ""
                        ):
                            st.session_state.pop(_SENDER_SESSION_KEY, None)
                        st.toast("WhatsApp number disconnected.")
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Disconnect failed: {exc}")
                    st.rerun()
    else:
        st.markdown(
            "<div class='wa-conn-empty'>No number has been registered for this organisation yet. "
            "An admin should use the coexistence button above, complete Meta's setup, and scan "
            "the QR code with the WhatsApp Business mobile app when Meta asks.</div>",
            unsafe_allow_html=True,
        )

    if not is_admin:
        return

    with st.expander("Advanced: add an existing Cloud API number manually"):
        st.caption(
            "Use this only for a number already set up in Meta Business Manager. "
            "For WhatsApp Business app coexistence, use the green Connect button above."
        )
        with st.form("wa_manual_add", clear_on_submit=True):
            pid = st.text_input("Phone number ID")
            waba = st.text_input("WhatsApp Business Account (WABA) ID")
            token = st.text_input("Access token", type="password")
            name = st.text_input("Display name (optional)")
            phone = st.text_input("Phone number (optional, e.g. +91…)")
            if st.form_submit_button("Save number", type="primary"):
                if not pid.strip() or not token.strip():
                    st.error("Phone number ID and access token are required.")
                else:
                    try:
                        pg.upsert_whatsapp_account(
                            {
                                "phone_number_id": pid.strip(),
                                "waba_id": waba.strip(),
                                "access_token": token.strip(),
                                "display_name": name.strip(),
                                "phone_number": phone.strip(),
                            },
                            organization_id,
                        )
                        st.session_state[_SENDER_SESSION_KEY] = pid.strip()
                        st.success("WhatsApp number saved.")
                        st.rerun()
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Couldn't save: {exc}")
