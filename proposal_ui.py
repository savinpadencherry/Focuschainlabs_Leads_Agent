"""
Proposal Agent UI — AI-drafted B2B proposals.

Stages: setup → generating → preview
Select a qualified contact → configure pricing/scope → generate via Gemini →
preview/edit, download HTML (print-to-PDF), send via email, log to CRM.
"""

from __future__ import annotations

import html as _html
import os
import time
from datetime import date
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

from agent.proposal_agent import build_html, generate_proposal, send_proposal_email
from utils.crm_models import normalize_comment, normalize_email_event, utc_now_iso
from utils.crm_store import load_crm, save_crm


# ── Session state ─────────────────────────────────────────────────────────────

def _init() -> None:
    defaults: dict[str, Any] = {
        "proposal_stage":    "setup",
        "proposal_contact":  None,
        "proposal_config":   {},
        "proposal_data":     None,
        "proposal_html":     None,
        "proposal_crm_db":   None,
        "proposal_crm_meta": None,
        "pa_show_send":      False,
        "pa_email_sent":     "",
        "pa_sel_id":         "",
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


def _reset() -> None:
    st.session_state.proposal_stage    = "setup"
    st.session_state.proposal_contact  = None
    st.session_state.proposal_config   = {}
    st.session_state.proposal_data     = None
    st.session_state.proposal_html     = None
    st.session_state.proposal_crm_db   = None
    st.session_state.proposal_crm_meta = None
    st.session_state.pa_show_send      = False
    st.session_state.pa_email_sent     = ""


def _load_crm_cached() -> tuple[list, dict]:
    if st.session_state.proposal_crm_db is None:
        db, meta = load_crm()
        st.session_state.proposal_crm_db   = db
        st.session_state.proposal_crm_meta = meta
    return (
        st.session_state.proposal_crm_db.get("contacts", []),
        st.session_state.proposal_crm_meta or {},
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _e(text: Any) -> str:
    return _html.escape(str(text or ""))


# ── Page CSS ──────────────────────────────────────────────────────────────────

_CSS = """
<style>
/* Proposal-specific — brand vars come from streamlit_app.py global CSS */

/* header replaced by .pg-hero — kept for compat */
.pa-head { display: none; }
.pa-sub  { display: none; }

/* Contact selection card */
.pa-co-card {
    padding: 10px 13px; border-radius: 8px;
    border: 1.5px solid var(--line); background: var(--cream-3);
    margin-bottom: 6px;
    transition: all .15s;
}
.pa-co-card.sel {
    border-color: var(--green);
    background: var(--green-bg);
    box-shadow: 0 0 0 2px rgba(46,139,77,.12);
}
.pa-co-name { font-weight: 700; font-size: 13.5px; color: var(--ink); }
.pa-co-meta { font-size: 11.5px; color: var(--ink-mute); margin-top: 2px; }

/* Section labels */
.pa-sec {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px; font-weight: 700; letter-spacing: .14em;
    text-transform: uppercase; color: var(--ink-mute);
    padding: 16px 0 8px;
    border-bottom: 1px solid var(--line-soft);
    margin-bottom: 12px;
}

/* Generating console rows */
.pa-gen-row {
    display: flex; align-items: center; gap: 9px;
    padding: 4px 0;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11.5px; color: rgba(245,242,235,.65);
    line-height: 1.4;
}
.pa-badge {
    font-size: 9px; font-weight: 700; letter-spacing: .1em;
    padding: 2px 7px; border-radius: 3px;
    white-space: nowrap; flex-shrink: 0;
}
.pa-badge-init   { background: rgba(107,127,133,.2);  color: rgba(245,242,235,.5); }
.pa-badge-intel  { background: rgba(183,121,31,.25);  color: #d4a847; }
.pa-badge-gen    { background: rgba(90,45,130,.3);    color: #c49ee0; }
.pa-badge-render { background: rgba(26,58,107,.35);   color: #7ba3d4; }
.pa-badge-done   { background: rgba(46,139,77,.3);    color: #37A85C; }
.pa-badge-error  { background: rgba(169,61,61,.3);    color: #e07070; }

@keyframes paPulse { 0%,100%{opacity:1;} 50%{opacity:.3;} }
.pa-pulse {
    width: 6px; height: 6px; background: var(--green); border-radius: 50%;
    display: inline-block;
    animation: paPulse 1.2s ease-in-out infinite;
}

/* Sent confirmation banner */
.pa-sent {
    background: var(--green-bg); border: 1px solid rgba(46,139,77,.25);
    border-radius: var(--rs); padding: 14px 18px;
    font-size: 13.5px; color: var(--ink); line-height: 1.6;
    margin-bottom: 14px;
}
.pa-sent strong { color: var(--green); }
</style>
"""


# ── Main render ───────────────────────────────────────────────────────────────

def render_proposal_page() -> None:
    _init()

    # Allow other pages to pre-select a contact
    presel = st.session_state.pop("proposal_sel_id", None)
    if presel:
        st.session_state.pa_sel_id = presel

    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown("""
<div class="pg-eyebrow">
  <span class="dot"></span><span class="dash"></span>
  FOCUSCHAIN LABS · PROPOSALS
</div>
<h2 class="pg-hero">Proposal <span class="accent">Agent</span></h2>
<p class="pg-sub">AI-draft a polished B2B proposal&nbsp;&nbsp;→&nbsp;&nbsp;auto-enriched with Intel signals&nbsp;&nbsp;→&nbsp;&nbsp;download PDF or send via email</p>
""", unsafe_allow_html=True)
    st.markdown("")

    stage = st.session_state.proposal_stage
    if stage == "setup":
        _render_setup()
    elif stage == "generating":
        _render_generating()
    elif stage == "preview":
        _render_preview()


# ── Setup phase ───────────────────────────────────────────────────────────────

def _render_setup() -> None:
    contacts, _ = _load_crm_cached()

    if not contacts:
        st.info(
            "No CRM contacts yet. Run the Scout Agent first, add leads to the CRM, "
            "then come back here to draft a proposal."
        )
        return

    proposal_stages = {"qualified", "proposal"}
    active_stages   = {"new", "contacted", "qualified", "proposal"}

    priority_conts = [c for c in contacts if (c.get("status") or "new") in proposal_stages]
    active_conts   = [c for c in contacts
                      if (c.get("status") or "new") in active_stages
                      and (c.get("status") or "new") not in proposal_stages]

    col_sel, col_cfg = st.columns([1.4, 1.6], gap="large")

    # ── Left: contact picker ──────────────────────────────────────────────────
    with col_sel:
        st.markdown('<div class="pa-sec">Select client contact</div>', unsafe_allow_html=True)

        sel_id: str = st.session_state.pa_sel_id

        def _contact_card(c: dict) -> None:
            nonlocal sel_id
            cid   = c.get("id", "")
            cstage = c.get("status") or "new"
            name  = c.get("company") or c.get("name") or "Unnamed"
            person = c.get("name", "") if c.get("company") else ""
            sub   = " · ".join(
                p for p in [person, c.get("industry", ""), c.get("title", "")] if p
            )
            is_sel = cid == sel_id

            stage_colors = {
                "qualified": "#1a6b3c",
                "proposal":  "#1a3a6b",
                "contacted": "#B7791F",
                "new":       "#6B7F85",
                "won":       "#2E8B4D",
            }
            sc = stage_colors.get(cstage, "#6B7F85")
            card_cls = "pa-co-card sel" if is_sel else "pa-co-card"

            st.markdown(f"""
            <div class="{card_cls}">
              <div class="pa-co-name">{_e(name)}</div>
              <div class="pa-co-meta">
                {_e(sub)}&nbsp;&nbsp;·&nbsp;&nbsp;
                <span style="color:{sc};font-weight:700;font-size:10.5px;
                             text-transform:uppercase;letter-spacing:.06em;">{cstage}</span>
              </div>
            </div>
            """, unsafe_allow_html=True)

            lbl  = "✓ Selected" if is_sel else "Select"
            kind = "primary" if is_sel else "secondary"
            if st.button(lbl, key=f"psel_{cid}", use_container_width=True, type=kind):
                st.session_state.pa_sel_id = cid
                st.rerun()

        for group_label, group in [
            ("Qualified & proposal stage", priority_conts),
            ("Active contacts",            active_conts),
        ]:
            if not group:
                continue
            st.caption(group_label)
            for c in sorted(group, key=lambda x: -int(x.get("score") or 0))[:30]:
                _contact_card(c)

    # ── Right: configuration form ─────────────────────────────────────────────
    with col_cfg:
        sel_contact = next((c for c in contacts if c.get("id") == sel_id), None)

        if sel_contact:
            company = sel_contact.get("company") or sel_contact.get("name") or "Client"
            st.markdown(
                f'<div class="pa-sec">Configure proposal for '
                f'<span style="color:var(--green);">{_e(company)}</span></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<div class="pa-sec">Configure proposal</div>', unsafe_allow_html=True)
            st.info("Select a contact on the left to continue.")
            return

        service_type = st.text_input(
            "Service / Engagement type",
            key="pa_service_type",
            value=st.session_state.get("pa_service_type",
                                       "B2B AI Automation & Workflow Optimisation"),
            placeholder="e.g. B2B AI Automation & CRM Integration",
        )

        deliverables_raw = st.text_area(
            "Deliverables (one per line)",
            key="pa_deliverables_raw",
            value=st.session_state.get("pa_deliverables_raw", ""),
            placeholder=(
                "AI-powered lead qualification pipeline\n"
                "CRM integration and workflow automation\n"
                "Weekly progress reports and KPI dashboard\n"
                "3 months of onboarding support"
            ),
            height=120,
        )

        pc1, pc2 = st.columns(2)
        with pc1:
            price = st.text_input(
                "Investment amount",
                key="pa_price",
                value=st.session_state.get("pa_price", ""),
                placeholder="e.g. 1,50,000",
            )
        with pc2:
            currency = st.selectbox(
                "Currency",
                options=["INR", "USD", "EUR", "GBP", "AED"],
                index=0,
                key="pa_currency",
            )

        payment_terms = st.text_input(
            "Payment terms",
            key="pa_payment_terms",
            value=st.session_state.get("pa_payment_terms", "50% upfront, 50% on delivery"),
        )

        td1, td2 = st.columns(2)
        with td1:
            duration = st.text_input(
                "Duration",
                key="pa_duration",
                value=st.session_state.get("pa_duration", "4–6 weeks"),
            )
        with td2:
            start_date_val = st.date_input(
                "Proposed start date",
                value=date.today(),
                key="pa_start_date",
            )

        st.markdown('<div class="pa-sec" style="margin-top:4px;">Sender details</div>',
                    unsafe_allow_html=True)

        sn1, sn2 = st.columns(2)
        with sn1:
            sender_name = st.text_input(
                "Your name",
                key="pa_sender_name",
                value=st.session_state.get("pa_sender_name",
                                           os.getenv("SENDER_NAME", "")),
            )
        with sn2:
            sender_title = st.text_input(
                "Your title",
                key="pa_sender_title",
                value=st.session_state.get("pa_sender_title",
                                           os.getenv("SENDER_TITLE", "")),
            )

        sender_company = st.text_input(
            "Your company",
            key="pa_sender_company",
            value=st.session_state.get("pa_sender_company",
                                       os.getenv("SENDER_COMPANY", "FocusChain Labs")),
        )

        st.markdown("")

        can_gen = bool(
            sel_id
            and service_type.strip()
            and price.strip()
            and os.getenv("GEMINI_API_KEY")
        )
        if not os.getenv("GEMINI_API_KEY"):
            st.warning("GEMINI_API_KEY not configured — needed for proposal generation.")

        if st.button(
            "Generate Proposal with AI",
            type="primary",
            use_container_width=True,
            disabled=not can_gen,
        ):
            config = {
                "service_type":   service_type.strip(),
                "deliverables":   [l.strip() for l in deliverables_raw.splitlines()
                                   if l.strip()],
                "price":          price.strip(),
                "currency":       currency,
                "payment_terms":  payment_terms.strip(),
                "duration":       duration.strip(),
                "start_date":     str(start_date_val),
                "sender_name":    sender_name.strip(),
                "sender_title":   sender_title.strip(),
                "sender_company": sender_company.strip(),
            }
            st.session_state.proposal_contact = sel_contact
            st.session_state.proposal_config  = config
            st.session_state.proposal_stage   = "generating"
            st.rerun()


# ── Generating phase ──────────────────────────────────────────────────────────

def _render_generating() -> None:
    contact = st.session_state.proposal_contact or {}
    config  = st.session_state.proposal_config  or {}
    company = contact.get("company") or contact.get("name") or "the client"

    log_slot = st.empty()

    def _console(rows_html: str) -> str:
        return f"""
<div class="run-console" style="margin-bottom:16px;">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;">
    <span style="font-family:'JetBrains Mono',monospace;font-size:10px;font-weight:700;
                 letter-spacing:.2em;text-transform:uppercase;
                 color:rgba(245,242,235,.45);">PROPOSAL AGENT</span>
    <div style="flex:1;height:1px;background:rgba(245,242,235,.1);"></div>
    <span class="pa-pulse"></span>
    <span style="font-family:'JetBrains Mono',monospace;font-size:9px;
                 color:var(--green);letter-spacing:.15em;">GENERATING</span>
  </div>
  <div style="display:flex;flex-direction:column;gap:3px;">
    {rows_html}
  </div>
</div>"""

    def _row(badge_cls: str, badge_txt: str, msg: str) -> str:
        return (
            f'<div class="pa-gen-row">'
            f'<span class="pa-badge {badge_cls}">{_e(badge_txt)}</span>'
            f'<span style="color:rgba(245,242,235,.8);">{_e(company)}</span>'
            f'<span style="color:rgba(245,242,235,.4);font-size:11px;">{_e(msg)}</span>'
            f'</div>'
        )

    rows: list[str] = []

    rows.append(_row("pa-badge-init", "INIT", "Preparing context…"))
    log_slot.markdown(_console("\n".join(rows)), unsafe_allow_html=True)
    time.sleep(0.2)

    rows.append(_row("pa-badge-intel", "INTEL", "Loading Intel signals for context…"))
    log_slot.markdown(_console("\n".join(rows)), unsafe_allow_html=True)
    time.sleep(0.15)

    rows.append(_row("pa-badge-gen", "GEMINI", "Drafting proposal via AI — may take 15–30s…"))
    log_slot.markdown(_console("\n".join(rows)), unsafe_allow_html=True)

    error_msg: str | None = None
    proposal_data: dict | None = None

    try:
        proposal_data = generate_proposal(contact, config)
    except Exception as exc:
        error_msg = str(exc)

    if error_msg:
        rows.append(_row("pa-badge-error", "ERROR", error_msg[:120]))
        log_slot.markdown(_console("\n".join(rows)), unsafe_allow_html=True)
        st.error(f"Proposal generation failed: {error_msg}")
        if st.button("← Back to setup", key="pa_back_err"):
            st.session_state.proposal_stage = "setup"
            st.rerun()
        return

    rows.append(_row("pa-badge-render", "RENDER", "Building proposal HTML…"))
    log_slot.markdown(_console("\n".join(rows)), unsafe_allow_html=True)
    time.sleep(0.12)

    proposal_html = build_html(proposal_data, config, contact)

    rows.append(_row("pa-badge-done", "DONE", "Proposal ready"))
    log_slot.markdown(_console("\n".join(rows)), unsafe_allow_html=True)
    time.sleep(0.35)

    st.session_state.proposal_data  = proposal_data
    st.session_state.proposal_html  = proposal_html
    st.session_state.proposal_stage = "preview"
    st.rerun()


# ── Preview phase ─────────────────────────────────────────────────────────────

def _render_preview() -> None:
    proposal_data = st.session_state.proposal_data
    proposal_html = st.session_state.proposal_html
    config        = st.session_state.proposal_config or {}
    contact       = st.session_state.proposal_contact or {}

    if not proposal_data or not proposal_html:
        st.error("No proposal to display. Please go back and generate one.")
        if st.button("← Back to setup"):
            st.session_state.proposal_stage = "setup"
            st.rerun()
        return

    company       = contact.get("company") or contact.get("name") or "Client"
    contact_email = contact.get("email", "")

    # ── Sent confirmation banner ───────────────────────────────────────────────
    if st.session_state.get("pa_email_sent"):
        st.markdown(
            f'<div class="pa-sent">Proposal sent to '
            f'<strong>{_e(st.session_state.pa_email_sent)}</strong> · '
            f'CRM stage updated to <strong>proposal</strong>.</div>',
            unsafe_allow_html=True,
        )

    # ── Action bar ─────────────────────────────────────────────────────────────
    ac1, ac2, ac3, ac4 = st.columns(4)

    with ac1:
        if st.button("← Regenerate", use_container_width=True, key="pa_regen"):
            _reset()
            st.rerun()

    with ac2:
        fname = f"proposal_{company.lower().replace(' ', '_')}.html"
        st.download_button(
            "Download HTML",
            data=proposal_html.encode("utf-8"),
            file_name=fname,
            mime="text/html",
            use_container_width=True,
            key="pa_dl",
        )

    with ac3:
        if st.button("Log to CRM", use_container_width=True, key="pa_log_crm"):
            err = _log_proposal_to_crm(proposal_data, config, contact)
            if err:
                st.error(err)
            else:
                _update_crm_stage(contact, "proposal")
                st.success(f"Logged to {company} CRM thread · Stage → proposal")
                st.session_state.proposal_crm_db   = None
                st.session_state.proposal_crm_meta = None
                st.rerun()

    with ac4:
        if st.button("Send via Email", type="primary",
                     use_container_width=True, key="pa_send_btn"):
            st.session_state.pa_show_send = not st.session_state.get("pa_show_send", False)
            st.rerun()

    # ── Email send panel ───────────────────────────────────────────────────────
    if st.session_state.get("pa_show_send"):
        with st.container():
            st.markdown('<div class="pa-sec">Send Proposal Email</div>', unsafe_allow_html=True)

            to_email = st.text_input(
                "Recipient email",
                value=contact_email,
                key="pa_to_email",
            )
            subject = st.text_input(
                "Subject",
                value=(
                    f"Proposal — {config.get('service_type', 'Our Services')} "
                    f"for {company}"
                ),
                key="pa_email_subject",
            )
            intro = st.text_area(
                "Intro (shown before the proposal)",
                key="pa_email_intro",
                value=(
                    f"Hi {contact.get('name', 'there')},\n\n"
                    f"Thank you for your time. Please find our proposal for "
                    f"{config.get('service_type', 'our services')} below.\n\n"
                    f"Happy to walk you through it on a call — just say the word."
                ),
                height=110,
            )

            smtp_ok = bool(
                os.getenv("SMTP_FROM_EMAIL") and os.getenv("SMTP_APP_PASSWORD")
            )
            if not smtp_ok:
                st.warning(
                    "Gmail SMTP not configured. Add SMTP_FROM_EMAIL and "
                    "SMTP_APP_PASSWORD to Streamlit Cloud secrets to send directly."
                )

            sc1, sc2 = st.columns(2)
            with sc1:
                if st.button(
                    "Send Now",
                    type="primary",
                    use_container_width=True,
                    disabled=not smtp_ok,
                    key="pa_send_now",
                ):
                    with st.spinner("Sending…"):
                        result = send_proposal_email(to_email, subject, intro, proposal_html)
                    if result.get("ok"):
                        _log_email_sent(contact, to_email, subject)
                        _update_crm_stage(contact, "proposal")
                        st.session_state.pa_show_send  = False
                        st.session_state.pa_email_sent = to_email
                        st.session_state.proposal_crm_db   = None
                        st.session_state.proposal_crm_meta = None
                        st.rerun()
                    else:
                        st.error(result.get("error", "Send failed"))
            with sc2:
                if st.button("Cancel", use_container_width=True, key="pa_send_cancel"):
                    st.session_state.pa_show_send = False
                    st.rerun()

        st.markdown("")

    # ── PDF hint ──────────────────────────────────────────────────────────────
    st.caption(
        "To save as PDF: download the HTML file, open it in Chrome/Safari, "
        "and press Cmd+P (or Ctrl+P) → 'Save as PDF'."
    )
    st.markdown("")

    # ── Proposal preview ──────────────────────────────────────────────────────
    st.markdown('<div class="pa-sec">Preview</div>', unsafe_allow_html=True)
    components.html(proposal_html, height=920, scrolling=True)

    # ── Edit sections (collapsed) ─────────────────────────────────────────────
    with st.expander("Edit & rebuild proposal", expanded=False):
        st.caption(
            "Adjust any section, then click Rebuild to refresh the preview and download."
        )

        edited: dict[str, Any] = {}
        for key, label in [
            ("executive_summary", "Executive Summary"),
            ("situation_analysis", "Situation Analysis"),
            ("our_approach",       "Our Approach"),
            ("validity_note",      "Validity Note"),
        ]:
            edited[key] = st.text_area(
                label,
                value=proposal_data.get(key, ""),
                height=110,
                key=f"pa_ed_{key}",
            )

        scope_raw = st.text_area(
            "Scope of Work (one item per line)",
            value="\n".join(proposal_data.get("scope") or []),
            height=100,
            key="pa_ed_scope",
        )
        why_raw = st.text_area(
            "Why Us (one point per line)",
            value="\n".join(proposal_data.get("why_us") or []),
            height=80,
            key="pa_ed_why",
        )
        next_raw = st.text_area(
            "Next Steps (one step per line)",
            value="\n".join(proposal_data.get("next_steps") or []),
            height=80,
            key="pa_ed_next",
        )

        if st.button("Rebuild preview", type="primary",
                     use_container_width=True, key="pa_rebuild"):
            updated = {**proposal_data, **edited}
            updated["scope"]      = [l.strip() for l in scope_raw.splitlines() if l.strip()]
            updated["why_us"]     = [l.strip() for l in why_raw.splitlines() if l.strip()]
            updated["next_steps"] = [l.strip() for l in next_raw.splitlines() if l.strip()]
            new_html = build_html(updated, config, contact)
            st.session_state.proposal_data = updated
            st.session_state.proposal_html = new_html
            st.rerun()


# ── CRM helpers ───────────────────────────────────────────────────────────────

def _log_proposal_to_crm(
    proposal: dict, config: dict, contact: dict
) -> str | None:
    """Add a proposal summary as a comment in the CRM thread."""
    contacts, meta = _load_crm_cached()
    target = next(
        (c for c in contacts if c.get("id") == contact.get("id")), None
    )
    if not target:
        return f"Contact not found in CRM for '{contact.get('company', '')}'."

    service  = config.get("service_type", "")
    price    = f"{config.get('price','')} {config.get('currency','')}".strip()
    duration = config.get("duration", "")
    date_str = utc_now_iso()[:10]
    scope_lines = "\n".join(
        f"  • {s}" for s in (proposal.get("scope") or [])[:6]
    )
    summary = (proposal.get("executive_summary") or "")[:300]

    body = (
        f"[Proposal Drafted — {date_str}]\n\n"
        f"Service: {service}\n"
        f"Investment: {price}\n"
        f"Duration: {duration}\n\n"
        + (f"Scope:\n{scope_lines}\n\n" if scope_lines else "")
        + (f"Summary:\n{summary}" if summary else "")
    )

    comment = normalize_comment({
        "author": "Proposal Agent",
        "body":   body,
        "type":   "proposal",
    })

    db = st.session_state.proposal_crm_db
    for c in db.get("contacts", []):
        if c.get("id") == target.get("id"):
            c.setdefault("comments", []).insert(0, comment)
            c["updated_at"] = utc_now_iso()
            break

    result = save_crm(
        db,
        sha=meta.get("sha"),
        message=f"Proposal: drafted for {contact.get('company', contact.get('name',''))}",
    )
    if isinstance(result, dict):
        st.session_state.proposal_crm_meta = {
            **meta,
            "sha": result.get("sha") or meta.get("sha"),
        }
    return None


def _update_crm_stage(contact: dict, new_stage: str) -> None:
    """Move the CRM contact to a new pipeline stage."""
    contacts, meta = _load_crm_cached()
    db = st.session_state.proposal_crm_db
    changed = False
    for c in db.get("contacts", []):
        if c.get("id") == contact.get("id"):
            if c.get("status") != new_stage:
                c["status"]     = new_stage
                c["updated_at"] = utc_now_iso()
                changed = True
            break
    if changed:
        save_crm(
            db,
            sha=meta.get("sha"),
            message=f"Stage → {new_stage}: {contact.get('company', contact.get('name',''))}",
        )


def _log_email_sent(contact: dict, to_email: str, subject: str) -> None:
    """Record the sent email in the CRM contact's email_events."""
    try:
        contacts, meta = _load_crm_cached()
        db = st.session_state.proposal_crm_db
        event = normalize_email_event({
            "to":      to_email,
            "subject": subject,
            "body":    "(Proposal email sent via Proposal Agent)",
            "author":  os.getenv("SENDER_NAME", "Proposal Agent"),
        })
        for c in db.get("contacts", []):
            if c.get("id") == contact.get("id"):
                c.setdefault("email_events", []).insert(0, event)
                c["updated_at"] = utc_now_iso()
                break
        save_crm(
            db,
            sha=meta.get("sha"),
            message=f"Proposal email sent to {to_email}",
        )
    except Exception:
        pass
