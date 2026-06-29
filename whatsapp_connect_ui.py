"""WhatsApp connections panel for the CRM — connect numbers via Meta Embedded
Signup, list connected numbers, disconnect. Everything is scoped to the active
organization_id so each tenant only ever sees and manages its own numbers.
"""

from __future__ import annotations

import html

import streamlit as st
import streamlit.components.v1 as components

from utils import auth
from utils import wa_embedded_signup as es

_PANEL_CSS = """
<style>
.wa-conn-row{display:flex;align-items:center;justify-content:space-between;
  background:#FDFCF9;border:1.5px solid rgba(15,42,51,.09);border-radius:12px;
  padding:12px 16px;margin-bottom:8px;}
.wa-conn-name{font-family:'Bricolage Grotesque',sans-serif;font-weight:700;
  font-size:14px;color:#0F2A33;}
.wa-conn-meta{font-family:'JetBrains Mono',monospace;font-size:10.5px;
  color:#6B7F85;letter-spacing:.03em;margin-top:2px;}
.wa-conn-dot{display:inline-block;width:7px;height:7px;border-radius:50%;
  background:#2E8B4D;margin-right:6px;box-shadow:0 0 0 3px rgba(46,139,77,.14);}
.wa-conn-hint{font-family:'JetBrains Mono',monospace;font-size:10.5px;
  color:#6B7F85;letter-spacing:.03em;line-height:1.6;}
.wa-conn-hint code{background:rgba(46,139,77,.10);color:#2E8B4D;border-radius:5px;
  padding:1px 6px;font-size:10px;}
</style>
"""

_SENDER_SESSION_KEY = "wa_sender_phone_number_id"


def _account_label(account: dict) -> str:
    name = account.get("display_name") or account.get("agent_name") or "WhatsApp number"
    number = account.get("phone_number") or account.get("phone_number_id") or ""
    return f"{name} · {number}"


def render_whatsapp_connections(organization_id: str) -> None:
    """Connected-numbers manager for one tenant. Safe to call on every CRM render."""
    from utils import crm_store_postgres as pg

    st.markdown(_PANEL_CSS, unsafe_allow_html=True)

    if not pg.postgres_configured():
        st.info(
            "Connect Cloud SQL to manage WhatsApp numbers "
            "(set CLOUD_SQL_CONNECTION_NAME or DATABASE_URL)."
        )
        return

    try:
        accounts = pg.load_whatsapp_accounts(organization_id)
    except Exception as exc:  # noqa: BLE001 - never crash the CRM page
        st.warning(f"Couldn't load WhatsApp numbers: {exc}")
        accounts = []

    is_admin = auth.is_admin()
    active_accounts = [
        a for a in accounts
        if a.get("active", True)
        and (a.get("phone_number_id") or "").strip()
        and (a.get("access_token") or "").strip()
    ]

    # Tenant-safe outbound selection. A single active number is automatic. When
    # several exist, an admin must choose the sender for this session before the
    # broadcast controls become enabled. The WhatsApp helper reads this same key.
    selected_pid = str(st.session_state.get(_SENDER_SESSION_KEY) or "").strip()
    active_pids = [str(a.get("phone_number_id") or "").strip() for a in active_accounts]
    if selected_pid and selected_pid not in active_pids:
        st.session_state.pop(_SENDER_SESSION_KEY, None)
        selected_pid = ""

    if len(active_accounts) == 1:
        st.session_state[_SENDER_SESSION_KEY] = active_pids[0]
    elif len(active_accounts) > 1:
        if is_admin:
            by_pid = {str(a["phone_number_id"]): a for a in active_accounts}
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

    st.markdown(
        "<div class='wa-conn-hint' style='margin-bottom:10px;'>"
        "Numbers connected here receive customer messages straight into this "
        "organisation's CRM. You can connect more than one.</div>",
        unsafe_allow_html=True,
    )

    if accounts:
        for a in accounts:
            label = a.get("display_name") or a.get("agent_name") or "WhatsApp number"
            number = a.get("phone_number") or a.get("phone_number_id") or ""
            row, btn = st.columns([5, 1])
            with row:
                st.markdown(
                    f"<div class='wa-conn-row'><div>"
                    f"<div class='wa-conn-name'><span class='wa-conn-dot'></span>"
                    f"{html.escape(str(label))}</div>"
                    f"<div class='wa-conn-meta'>{html.escape(str(number))} · "
                    f"id {html.escape(str(a.get('phone_number_id') or ''))}</div>"
                    f"</div></div>",
                    unsafe_allow_html=True,
                )
            with btn:
                # Only admins can remove a connected number.
                if is_admin and st.button("Disconnect", key=f"wa_disc_{a.get('id')}"):
                    try:
                        pg.delete_whatsapp_account(a.get("id") or "", organization_id)
                        if str(a.get("phone_number_id") or "") == str(
                            st.session_state.get(_SENDER_SESSION_KEY) or ""
                        ):
                            st.session_state.pop(_SENDER_SESSION_KEY, None)
                        st.toast("WhatsApp number disconnected.")
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Disconnect failed: {exc}")
                    st.rerun()
    else:
        st.caption("No WhatsApp numbers connected yet.")

    # Connecting / removing numbers is an admin-only action.
    if not is_admin:
        st.markdown(
            "<div class='wa-conn-hint'>Only organisation admins can connect or "
            "remove WhatsApp numbers.</div>",
            unsafe_allow_html=True,
        )
        return

    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    # Official Embedded Signup launcher (scan-QR onboarding inside Meta's popup).
    if es.embedded_signup_configured():
        components.html(es.launcher_html(organization_id), height=240)
    else:
        st.markdown(
            "<div class='wa-conn-hint'>To enable one-click <b>Connect WhatsApp</b> "
            "(Meta Embedded Signup), set <code>META_APP_ID</code>, "
            "<code>META_CONFIG_ID</code>, <code>WA_CONNECT_SECRET</code> and "
            "<code>WEBHOOK_PUBLIC_URL</code>. Until then, add a number manually below.</div>",
            unsafe_allow_html=True,
        )

    with st.expander("Add a number manually"):
        st.caption(
            "Use this for a number already set up in Meta Business Manager — "
            "paste its details from WhatsApp → API Setup."
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
