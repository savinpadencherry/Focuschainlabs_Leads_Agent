"""
Reach Agent UI — outreach workflow page.

Contact queue (left) → draft + send area (right).
AI generates personalised cold email + 2-step follow-up → send via Gmail SMTP
or copy / open in Gmail → email auto-logged to CRM thread, stage → Contacted.
"""

from __future__ import annotations

import html
import os
import re
import urllib.parse
from typing import Any

import streamlit as st

from utils.crm_models import normalize_email_event, utc_now_iso
from utils.crm_store import load_crm, save_crm
from utils.usage_guide import render_usage_guide
from agent.contact_finder import (
    best_guess_email,
    extract_domain,
    hunter_find_email,
    split_name,
)
from agent.reach_agent import compose_outreach, send_email_smtp, smtp_configured


# ── State init ────────────────────────────────────────────────────────────────

def _init() -> None:
    defaults: dict[str, Any] = {
        "reach_sel_id":      None,
        "reach_draft":       None,
        "reach_filter":      "all",
        "reach_db":          None,
        "reach_meta":        None,
        "reach_sent_msg":    None,
        "reach_find_error":  None,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


def _load() -> tuple[list, dict]:
    if st.session_state.reach_db is None:
        db, meta = load_crm()
        st.session_state.reach_db   = db
        st.session_state.reach_meta = meta
    return st.session_state.reach_db.get("contacts", []), st.session_state.reach_meta or {}


def _invalidate() -> None:
    st.session_state.reach_db   = None
    st.session_state.reach_meta = None


def _save(message: str) -> None:
    meta = st.session_state.reach_meta or {}
    result = save_crm(
        st.session_state.reach_db,
        sha=meta.get("sha"),
        message=message,
    )
    if isinstance(result, dict):
        st.session_state.reach_meta = {**meta, "sha": result.get("sha") or meta.get("sha")}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _badge(label: str, color: str, bg: str) -> str:
    return (
        f'<span class="cq-badge" style="color:{color};background:{bg};'
        f'border-color:{color};">{html.escape(label)}</span>'
    )


def _stage_badge(stage: str) -> str:
    MAP = {
        "new":       ("#6B7F85", "rgba(107,127,133,.1)"),
        "contacted": ("#B7791F", "rgba(183,121,31,.1)"),
        "qualified": ("#1a6b3c", "rgba(26,107,60,.1)"),
        "proposal":  ("#1a3a6b", "rgba(26,58,107,.1)"),
        "won":       ("#2E8B4D", "rgba(46,139,77,.1)"),
        "lost":      ("#A93D3D", "rgba(169,61,61,.1)"),
    }
    c, bg = MAP.get(stage, ("#6B7F85", "rgba(107,127,133,.1)"))
    return _badge(stage, c, bg)


def _confidence_badge(tier: str) -> str:
    MAP = {
        "verified": ("#1a6b3c", "rgba(26,107,60,.1)",  "✓ verified"),
        "likely":   ("#B7791F", "rgba(183,121,31,.1)", "~ likely"),
        "guess":    ("#A93D3D", "rgba(169,61,61,.1)",  "? guess"),
    }
    c, bg, label = MAP.get(tier, ("#6B7F85", "rgba(107,127,133,.1)", tier or "unknown"))
    return _badge(label, c, bg)


def _filter_contacts(contacts: list, flt: str) -> list:
    if flt == "has_email":
        return [c for c in contacts if c.get("email")]
    if flt == "no_email":
        return [c for c in contacts if not c.get("email")]
    if flt == "new":
        return [c for c in contacts if c.get("status") == "new"]
    if flt == "contacted":
        return [c for c in contacts if c.get("status") == "contacted"]
    return list(contacts)


def _try_find_email(contact: dict, meta: dict) -> str | None:
    """Hunter.io → pattern guess. Updates CRM in place. Returns found email or None."""
    name    = contact.get("name", "")
    website = contact.get("website", "")
    company = contact.get("company", "")

    domain = extract_domain(website)
    if not domain and company:
        # Heuristic domain guess — low confidence but worth trying
        slug = re.sub(r"[^a-z0-9]", "", company.lower())[:20]
        domain = f"{slug}.com" if slug else ""

    first, last = split_name(name)
    if not (domain and first):
        return None

    found: dict[str, Any] = {}
    if first and last:
        hit = hunter_find_email(domain, first, last)
        if hit.get("email"):
            found = {"email": hit["email"], "tier": "verified" if hit.get("confidence", 0) >= 70 else "likely"}

    if not found and first and last:
        guess = best_guess_email(domain, first, last)
        if guess.get("email"):
            found = {"email": guess["email"], "tier": guess.get("confidence_tier", "guess")}

    if found.get("email"):
        db = st.session_state.reach_db
        for c in db.get("contacts", []):
            if c.get("id") == contact.get("id"):
                c["email"]             = found["email"]
                c["email_confidence"]  = found["tier"]
                c["updated_at"]        = utc_now_iso()
                break
        _save(f"Reach: found email for {name}")
        return found["email"]
    return None


def _log_sent_email(contact: dict, subject: str, body: str) -> None:
    """Append sent email to CRM thread and advance stage to contacted."""
    event = normalize_email_event({
        "direction": "sent",
        "sent_at":   utc_now_iso(),
        "from_addr": os.getenv("SMTP_FROM_EMAIL", ""),
        "to":        contact.get("email", ""),
        "subject":   subject,
        "body":      body,
        "source":    "reach_agent",
    })
    db = st.session_state.reach_db
    for c in db.get("contacts", []):
        if c.get("id") == contact.get("id"):
            c.setdefault("email_events", []).insert(0, event)
            if (c.get("status") or "new") == "new":
                c["status"] = "contacted"
            c["updated_at"] = utc_now_iso()
            break
    _save(f"Reach: email sent to {contact.get('name', contact.get('company', ''))}")
    _invalidate()


# ── Main render ───────────────────────────────────────────────────────────────

def render_reach_page() -> None:
    _init()

    st.markdown("""
    <style>
    .ra-head {
        font-family: 'Bricolage Grotesque', sans-serif;
        font-size: clamp(24px, 3.2vw, 30px);
        font-weight: 850;
        letter-spacing: -.03em;
        margin-bottom: 2px;
    }
    .ra-sub {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 11px; color: var(--ink-mute);
        letter-spacing: .03em;
        margin-bottom: 12px;
    }
    .ra-filters {
        display: flex; flex-wrap: wrap; gap: 6px;
        margin-bottom: 12px;
    }
    /* Queue filter radio → wrapping chips */
    [data-testid="stRadio"] [role="radiogroup"] {
        display: flex; flex-wrap: wrap; gap: 6px;
    }
    [data-testid="stRadio"] label {
        border: 1px solid var(--line-soft) !important;
        border-radius: 999px !important;
        padding: 5px 13px !important;
        background: rgba(255,255,255,.72) !important;
        margin: 0 !important;
        transition: border-color .18s ease, background .18s ease, box-shadow .18s ease;
        cursor: pointer;
    }
    [data-testid="stRadio"] label:hover {
        border-color: rgba(46,139,77,.30) !important;
        background: #fff !important;
        box-shadow: 0 4px 12px rgba(15,42,51,.06);
    }
    [data-testid="stRadio"] label:has(input:checked) {
        border-color: var(--green) !important;
        background: rgba(46,139,77,.10) !important;
        box-shadow: inset 0 1px 0 rgba(255,255,255,.6);
    }
    [data-testid="stRadio"] label:has(input:checked) p { color: var(--green) !important; font-weight: 700 !important; }
    [data-testid="stRadio"] label > div:first-child { display: none !important; }  /* hide the radio dot */
    [data-testid="stRadio"] label p {
        font-size: 12px !important; font-weight: 600 !important;
        color: var(--ink-soft) !important; white-space: nowrap !important;
        line-height: 1.2 !important;
    }
div[data-testid="stElementContainer"]:has(.reach-row-anchor) + div[data-testid="stElementContainer"] [data-testid="stHorizontalBlock"],
div[data-testid="stElementContainer"]:has(.reach-row-anchor) + div[data-testid="stHorizontalBlock"] {
        margin-bottom: 5px;
        min-width: 0 !important;
        max-width: 100% !important;
        animation: reachRowIn .34s var(--ease-out) both;
        animation-delay: calc(var(--reach-i, 0) * 38ms);
    }
    div[data-testid="stElementContainer"]:has(.reach-row-anchor) + div[data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child,
    div[data-testid="stElementContainer"]:has(.reach-row-anchor) + div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child {
        min-width: 0 !important;
        overflow: hidden !important;
    }
    div[data-testid="stElementContainer"]:has(.reach-row-anchor) + div[data-testid="stElementContainer"] [data-testid="stMarkdownContainer"],
    div[data-testid="stElementContainer"]:has(.reach-row-anchor) + div[data-testid="stHorizontalBlock"] [data-testid="stMarkdownContainer"] {
        min-width: 0 !important;
        overflow: hidden !important;
    }
    div[data-testid="stElementContainer"]:has(.reach-row-anchor) + div[data-testid="stElementContainer"] [data-testid="stHorizontalBlock"]:hover .cq-card,
    div[data-testid="stElementContainer"]:has(.reach-row-anchor) + div[data-testid="stHorizontalBlock"]:hover .cq-card {
        border-color: rgba(46,139,77,.28);
        background: #fff;
        box-shadow: 0 10px 24px rgba(15,42,51,.08);
        transform: translateY(-2px);
    }
    div[data-testid="stElementContainer"]:has(.reach-row-anchor) + div[data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] > div[data-testid="column"]:last-child button,
    div[data-testid="stElementContainer"]:has(.reach-row-anchor) + div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:last-child button {
        min-height: 52px !important;
        border-radius: 0 10px 10px 0 !important;
        border-left: none !important;
        font-size: 17px !important;
        font-weight: 700 !important;
        color: var(--ink-mute) !important;
        background: rgba(255,255,255,.72) !important;
        box-shadow: 0 4px 14px rgba(15,42,51,.05) !important;
        transition: transform .14s var(--ease-out), background .14s var(--ease-out),
                    box-shadow .14s var(--ease-out), border-color .14s var(--ease-out) !important;
    }
    div[data-testid="stElementContainer"]:has(.reach-row-anchor) + div[data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] > div[data-testid="column"]:last-child button:active,
    div[data-testid="stElementContainer"]:has(.reach-row-anchor) + div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:last-child button:active {
        transform: scale(.96) !important;
    }
    div[data-testid="stElementContainer"]:has(.reach-row-anchor) + div[data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] > div[data-testid="column"]:last-child [data-testid="stBaseButton-primary"] button,
    div[data-testid="stElementContainer"]:has(.reach-row-anchor) + div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:last-child [data-testid="stBaseButton-primary"] button {
        background: var(--green) !important;
        color: #fff !important;
        border-color: var(--green) !important;
    }
    .cq-card {
        position: relative;
        z-index: 1;
        padding: 10px 12px;
        border-radius: 10px 0 0 10px;
        border: 1px solid var(--line-soft);
        border-right: none;
        background: rgba(255,255,255,.68);
        min-height: 52px;
        max-width: 100%;
        box-sizing: border-box;
        overflow: hidden;
        transition: border-color .18s var(--ease-out), background .18s var(--ease-out),
                    box-shadow .18s var(--ease-out), transform .18s var(--ease-out);
        box-shadow: 0 4px 14px rgba(15,42,51,.05);
    }
    .cq-card-sel {
        border-color: rgba(46,139,77,.34) !important;
        background: linear-gradient(135deg, rgba(46,139,77,.07), rgba(255,255,255,.92)) !important;
        box-shadow: 0 10px 24px rgba(46,139,77,.12) !important;
        animation: reachSelect .28s var(--ease-out) both;
    }
    .cq-top {
        display: flex; align-items: center; justify-content: space-between;
        gap: 6px; margin-bottom: 4px;
        min-width: 0; max-width: 100%;
    }
    .cq-name {
        font-family: 'Bricolage Grotesque', sans-serif;
        font-weight: 800; font-size: 14px; line-height: 1.15;
        color: var(--ink);
        flex: 1 1 auto;
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .cq-badge {
        flex: 0 0 auto;
        font-size: 9px;
        font-weight: 700;
        letter-spacing: .05em;
        text-transform: uppercase;
        white-space: nowrap;
        padding: 2px 6px;
        border-radius: 3px;
        border: 1px solid;
        line-height: 1.2;
        max-width: 42%;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .cq-meta {
        font-size: 11px; color: var(--ink-mute); line-height: 1.35;
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .cq-foot {
        display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-top: 5px;
    }
    .cq-score {
        font-family: 'JetBrains Mono', monospace;
        font-size: 9px; font-weight: 700; letter-spacing: .06em;
        color: var(--ink-mute); text-transform: uppercase;
    }

    .reach-detail-in {
        animation: reachDetailIn .34s var(--ease-out) both;
    }
    @keyframes reachDetailIn {
        from { opacity: 0; transform: translateX(10px); }
        to   { opacity: 1; transform: translateX(0); }
    }
    .draft-wrap {
        position: relative;
        z-index: 10;
        background: var(--cream-3); border: 1.5px solid var(--line);
        border-radius: 12px; padding: 20px 22px;
        margin-top: 20px;
        animation: reachDetailIn .34s var(--ease-out) both;
    }
    .no-email-box {
        background: var(--amber-bg); border: 1px solid rgba(183,121,31,.3);
        border-radius: 8px; padding: 12px 14px;
        font-size: 12.5px; color: var(--ink-soft); margin-bottom: 14px;
    }
    .smtp-hint {
        background: var(--green-bg); border: 1px solid rgba(46,139,77,.2);
        border-radius: 8px; padding: 12px 14px; font-size: 12px;
        color: var(--ink-soft); margin-top: 14px; line-height: 1.7;
    }
    .smtp-hint code {
        background: rgba(46,139,77,.1); padding: 1px 5px;
        border-radius: 3px; font-size: 11px;
    }
    .seq-label {
        font-family: 'JetBrains Mono', monospace;
        font-size: 10px; font-weight: 700;
        letter-spacing: .1em; text-transform: uppercase;
        color: var(--ink-mute); margin-bottom: 4px;
    }
    .empty-state {
        text-align:center; padding: 40px 16px; color: var(--ink-mute);
    }
    .empty-state .es-kicker {
        font-family: 'JetBrains Mono', monospace;
        font-size: 9px; letter-spacing: .18em; text-transform: uppercase;
        color: var(--green); margin-bottom: 10px;
    }
    .empty-state .es-title { font-size: 16px; font-weight: 800; margin-bottom: 6px; color: var(--ink); }
    .empty-state .es-body  { font-size: 12.5px; line-height: 1.55; }
    @keyframes reachRowIn {
        from { opacity: 0; transform: translateY(8px) scale(.985); }
        to   { opacity: 1; transform: translateY(0) scale(1); }
    }
    @keyframes reachSelect {
        0%   { box-shadow: 0 0 0 0 rgba(46,139,77,.28); }
        55%  { box-shadow: 0 0 0 4px rgba(46,139,77,.14); }
        100% { box-shadow: 0 10px 24px rgba(46,139,77,.12); }
    }

    @media (prefers-reduced-motion: reduce) {
        *, *::before, *::after {
            animation-duration: 0.01ms !important;
            animation-iteration-count: 1 !important;
            transition-duration: 0.01ms !important;
        }
    }

    @media (max-width: 720px) {
        .ra-head { font-size: 28px; line-height: 1.1; }
        .ra-sub { font-size: 11px; line-height: 1.6; margin-bottom: 16px; }
        .cq-card { padding: 12px 14px; }
        .cq-card.sel { transform: none; }
        .draft-wrap { padding: 16px; margin-top: 12px; }
        div[class*="st-key-reach_main_split"] [data-testid="stHorizontalBlock"] {
            flex-direction: column !important;
            gap: 16px !important;
        }
        div[class*="st-key-reach_main_split"] [data-testid="column"] {
            width: 100% !important;
            flex: 1 1 auto !important;
        }
        div[class*="st-key-reach_row_"] [data-testid="stHorizontalBlock"] {
            flex-direction: row !important;
            align-items: center !important;
        }
        div[class*="st-key-reach_row_"] [data-testid="column"]:first-child {
            flex: 1 1 auto !important;
            width: auto !important;
        }
        div[class*="st-key-reach_row_"] [data-testid="column"]:last-child {
            flex: 0 0 44px !important;
            width: 44px !important;
        }
        div[class*="st-key-reach_row_"] .stButton > button {
            min-height: 44px !important;
            touch-action: manipulation;
        }
    }
    
div[data-testid="stElementContainer"]:has(> [data-testid="stMarkdownContainer"] .reach-row-anchor) {
    margin: 0 !important; height: 0 !important; min-height: 0 !important; overflow: hidden;
}
</style>
    """, unsafe_allow_html=True)

    st.markdown(
        '<div class="ra-head">Reach <span style="color:var(--green)">Agent</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="ra-sub">contact&nbsp;&nbsp;→&nbsp;&nbsp;compose&nbsp;&nbsp;→&nbsp;&nbsp;send</div>',
        unsafe_allow_html=True,
    )

    render_usage_guide("reach")

    contacts, meta = _load()

    if not contacts:
        st.info(
            "No contacts in CRM yet. Run the Scout Agent to generate leads, "
            "then click **Add all to CRM** on the results page."
        )
        return

    with st.container(key="reach_main_split"):
        col_q, col_d = st.columns([1, 1.85], gap="large")

        # ══════════════════════════════════ LEFT — QUEUE ══════════════════════════
        with col_q:
            st.markdown("**Contact queue**")

            has_email_n  = sum(1 for c in contacts if c.get("email"))
            no_email_n   = len(contacts) - has_email_n
            new_n        = sum(1 for c in contacts if c.get("status") == "new")
            contacted_n  = sum(1 for c in contacts if c.get("status") == "contacted")

            filter_defs = [
                ("all", f"All {len(contacts)}"),
                ("has_email", f"Email {has_email_n}"),
                ("no_email", f"No email {no_email_n}"),
                ("new", f"New {new_n}"),
                ("contacted", f"Contacted {contacted_n}"),
            ]
            flt = st.session_state.reach_filter
            f_keys = [k for k, _ in filter_defs]
            f_labels = [lbl for _, lbl in filter_defs]
            current_idx = f_keys.index(flt) if flt in f_keys else 0
            picked = st.radio(
                "Queue filter", f_labels, index=current_idx,
                horizontal=True, label_visibility="collapsed",
            )
            picked_key = f_keys[f_labels.index(picked)]
            if picked_key != flt:
                st.session_state.reach_filter = picked_key
                st.rerun()

            filtered = _filter_contacts(contacts, flt)
            filtered = sorted(
                filtered,
                key=lambda c: (-int(c.get("score") or 0), (c.get("company") or c.get("name") or "").lower()),
            )

            if not filtered:
                st.caption("No contacts match this filter.")

            st.markdown("")

            for row_i, c in enumerate(filtered[:60]):
                cid        = c.get("id", "")
                is_sel     = st.session_state.reach_sel_id == cid
                email      = c.get("email") or ""
                score      = int(c.get("score") or 0)
                stage      = c.get("status") or "new"
                name_disp  = c.get("company") or c.get("name") or "Unnamed"
                sub_disp   = c.get("name") if c.get("name") != name_disp else ""
                email_disp = email if email else "No email"
                email_col  = "var(--ink-soft)" if email else "var(--amber)"
                card_cls   = "cq-card cq-card-sel" if is_sel else "cq-card"
                score_html = f'<span class="cq-score">Score {score}</span>' if score else ""

                st.markdown(
                    f'<span class="reach-row-anchor" style="--reach-i:{row_i}"></span>',
                    unsafe_allow_html=True,
                )
                row_col, pick_col = st.columns([20, 1.05], gap="small")
                with row_col:
                    st.markdown(f"""
                    <div class="{card_cls}">
                      <div class="cq-top">
                        <div class="cq-name">{html.escape(name_disp)}</div>
                        {_stage_badge(stage)}
                      </div>
                      <div class="cq-meta">
                        {"<span>" + html.escape(sub_disp) + " · </span>" if sub_disp else ""}
                        <span style="color:{email_col};">{html.escape(email_disp)}</span>
                      </div>
                      <div class="cq-foot">{score_html}</div>
                    </div>
                    """, unsafe_allow_html=True)
                with pick_col:
                    if st.button(
                        "›",
                        key=f"selb_{cid}",
                        use_container_width=True,
                        type="primary" if is_sel else "secondary",
                    ):
                        st.session_state.reach_sel_id   = cid
                        st.session_state.reach_draft    = None
                        st.session_state.reach_sent_msg = None
                        st.session_state.reach_find_error = None
                        st.rerun()

        # ══════════════════════════════════ RIGHT — DRAFT ═════════════════════════
        with col_d:
            sel_id = st.session_state.reach_sel_id
            if not sel_id:
                st.markdown("""
                <div class="empty-state">
                  <div class="es-kicker">Outreach workspace</div>
                  <div class="es-title">Select a contact to start</div>
                  <div class="es-body">AI writes a personalised 3-email sequence<br>using Scout-Agent signals.</div>
                </div>
                """, unsafe_allow_html=True)
                return

            contact = next((c for c in contacts if c.get("id") == sel_id), None)
            if not contact:
                st.warning("Contact not found — please refresh.")
                if st.button("Reload", key="reload_reach"):
                    _invalidate()
                    st.rerun()
                return

            name    = contact.get("company") or contact.get("name") or "Contact"
            subname = contact.get("name") if contact.get("name") != name else ""
            email   = contact.get("email") or ""
            stage   = contact.get("status") or "new"
            conf    = contact.get("email_confidence") or ""

            # Contact summary
            c1, c2 = st.columns([2, 1])
            with c1:
                st.markdown(f"**{name}**")
                if subname:
                    st.caption(subname + ((" · " + contact["title"]) if contact.get("title") else ""))
                if contact.get("industry"):
                    st.caption(contact["industry"])
            with c2:
                badges = _stage_badge(stage)
                if email and conf:
                    badges += "&nbsp;" + _confidence_badge(conf)
                st.markdown(badges, unsafe_allow_html=True)
                if email:
                    st.caption(email)

            st.divider()

            # ── No email: find / manual entry ────────────────────────────────────
            if not email:
                st.markdown("""
                <div class="no-email-box">
                  ⚠️ <strong>No email for this contact.</strong>
                  Use Hunter.io to look one up, or enter it manually.
                </div>
                """, unsafe_allow_html=True)

                if st.session_state.reach_find_error:
                    st.error(st.session_state.reach_find_error)

                fa, fb = st.columns([1, 1], gap="medium")
                with fa:
                    hunter_key = os.getenv("HUNTER_API_KEY", "")
                    if st.button(
                        "Find Email (Hunter.io)",
                        key="find_email_btn",
                        use_container_width=True,
                        type="primary",
                        disabled=not bool(contact.get("name")),
                        help="Requires HUNTER_API_KEY in Streamlit secrets (free 25/month at hunter.io)",
                    ):
                        with st.spinner("Looking up email…"):
                            found = _try_find_email(contact, meta)
                        if found:
                            st.session_state.reach_find_error = None
                            st.success(f"Found: **{found}**")
                            st.rerun()
                        else:
                            st.session_state.reach_find_error = (
                                "Couldn't find an email automatically. "
                                "Try entering it manually or check LinkedIn."
                            )
                            st.rerun()

                    if not hunter_key:
                        st.caption("Add HUNTER_API_KEY to secrets to enable this.")

                with fb:
                    st.markdown("**Enter manually**")
                    manual = st.text_input(
                        "Email address",
                        placeholder="name@company.com",
                        key="manual_email",
                        label_visibility="collapsed",
                    )
                    if st.button("Save", key="save_manual_email") and manual and "@" in manual:
                        db = st.session_state.reach_db
                        for c in db.get("contacts", []):
                            if c.get("id") == sel_id:
                                c["email"]            = manual.strip().lower()
                                c["email_confidence"] = "guess"
                                c["updated_at"]       = utc_now_iso()
                                break
                        _save(f"Reach: manual email for {name}")
                        _invalidate()
                        st.rerun()

                return

            # ── Sender details ────────────────────────────────────────────────────
            with st.expander("Sender details & pitch context", expanded=False):
                scol1, scol2 = st.columns(2)
                with scol1:
                    sender_name  = st.text_input("Your name",  key="r_sname",  value=os.getenv("SENDER_NAME", ""))
                    sender_title = st.text_input("Your title", key="r_stitle", value=os.getenv("SENDER_TITLE", ""))
                with scol2:
                    sender_co    = st.text_input("Your company", key="r_sco",  value=os.getenv("SENDER_COMPANY", "FocusChain Labs"))

                offering = st.text_area(
                    "What you're pitching (1-2 sentences)",
                    key="r_offering",
                    value=os.getenv("SENDER_OFFERING", contact.get("notes") or ""),
                    height=60,
                    placeholder="e.g. We help D2C brands automate their lead generation and outreach using AI agents.",
                )

            # ── Generate draft ────────────────────────────────────────────────────
            draft = st.session_state.reach_draft
            gcol1, gcol2 = st.columns([1.5, 1])
            with gcol1:
                gen_label = "Generate Email Sequence" if not draft else "↺ Regenerate Sequence"
                if st.button(gen_label, key="gen_draft", use_container_width=True, type="primary"):
                    with st.spinner("Composing personalised sequence…"):
                        try:
                            st.session_state.reach_draft = compose_outreach(
                                contact,
                                sender_name    = st.session_state.get("r_sname", ""),
                                sender_title   = st.session_state.get("r_stitle", ""),
                                sender_company = st.session_state.get("r_sco", "FocusChain Labs"),
                                offering       = st.session_state.get("r_offering", ""),
                            )
                            draft = st.session_state.reach_draft
                        except Exception as exc:
                            st.error(f"Draft generation failed: {exc}")
            with gcol2:
                if st.button("Reload CRM", key="reload_reach2", use_container_width=True):
                    _invalidate()
                    st.rerun()

            if not draft:
                st.caption("Click **Generate Email Sequence** to compose a personalised 3-email sequence.")
                return

            # ── Email sequence tabs ───────────────────────────────────────────────
            t1, t2, t3 = st.tabs(["1 · Cold email", "2 · Day-3 follow-up", "3 · Day-7 close"])

            seq_items = [
                (t1, "e1", "email_1", draft.get("subject", ""), False),
                (t2, "e2", "email_2", f"Re: {draft.get('subject', '')}", True),
                (t3, "e3", "email_3", f"Re: {draft.get('subject', '')}", True),
            ]

            for tab, pfx, body_key, default_subj, is_followup in seq_items:
                with tab:
                    subj = st.text_input(
                        "Subject line",
                        value=default_subj,
                        key=f"r_subj_{pfx}",
                    )
                    body = st.text_area(
                        "Email body",
                        value=draft.get(body_key, ""),
                        key=f"r_body_{pfx}",
                        height=220,
                    )

                    if not body.strip():
                        st.caption("No draft content for this step.")
                        continue

                    st.markdown("")

                    act1, act2, act3 = st.columns([1, 1, 1], gap="small")

                    # ── Send ──────────────────────────────────────────────────────
                    with act1:
                        can_send = smtp_configured()
                        if can_send:
                            if st.button(
                                "Send via Gmail →",
                                key=f"r_send_{pfx}",
                                use_container_width=True,
                                type="primary",
                            ):
                                result = send_email_smtp(email, subj, body)
                                if result.get("ok"):
                                    _log_sent_email(contact, subj, body)
                                    st.session_state.reach_sent_msg = (
                                        f"Sent to {email} · Logged to CRM thread · Stage → Contacted"
                                    )
                                    st.rerun()
                                else:
                                    st.error(result.get("error", "Send failed."))
                        else:
                            st.button(
                                "Send via Gmail →",
                                key=f"r_send_{pfx}",
                                use_container_width=True,
                                type="primary",
                                disabled=True,
                                help="Configure SMTP in Streamlit secrets to enable sending.",
                            )

                    # ── Open in Gmail ─────────────────────────────────────────────
                    with act2:
                        mailto = (
                            f"mailto:{email}"
                            f"?subject={urllib.parse.quote(subj)}"
                            f"&body={urllib.parse.quote(body[:1800])}"
                        )
                        st.link_button("Open in Gmail ↗", mailto, use_container_width=True)

                    # ── Copy ──────────────────────────────────────────────────────
                    with act3:
                        copy_txt = f"To: {email}\nSubject: {subj}\n\n{body}"
                        st.code(copy_txt, language=None)

            # ── Sent confirmation banner ──────────────────────────────────────────
            if st.session_state.reach_sent_msg:
                st.success(f"✓  {st.session_state.reach_sent_msg}")

            # ── SMTP setup hint ───────────────────────────────────────────────────
            if not smtp_configured():
                st.markdown("""
                <div class="smtp-hint">
                  <strong>Enable direct sending from this app</strong><br>
                  Add to your Streamlit Cloud secrets panel:<br><br>
                  <code>SMTP_FROM_EMAIL = "you@gmail.com"</code><br>
                  <code>SMTP_APP_PASSWORD = "xxxx xxxx xxxx xxxx"</code><br><br>
                  <small>Generate an App Password:
                  Google Account → Security → 2-Step Verification → App Passwords → Create new.
                  Use the 16-character password (not your account password).</small>
                </div>
                """, unsafe_allow_html=True)
