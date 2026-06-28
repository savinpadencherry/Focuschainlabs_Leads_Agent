"""
Finance Agent UI — invoicing, payment tracking & AI dunning.

Views: dashboard → create → preview
  • dashboard: cashflow snapshot, "ready to invoice" won deals, invoice ledger,
    overdue invoices with one-click AI payment reminders (dunning).
  • create:    pick a CRM contact → line-item form → build invoice (no API cost).
  • preview:   invoice HTML preview → download / send / mark-paid / log to CRM.

Invoices live on the CRM contact (GitHub-backed) — persistent financial records.
"""

from __future__ import annotations

import html as _html
import os
import time
from datetime import date
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

from agent.finance_agent import (
    build_invoice,
    build_invoice_html,
    cashflow_snapshot,
    collect_invoices,
    compose_dunning_email,
    currency_symbol,
    dunning_level_for,
    fmt_money,
    line_items_from_proposal,
    next_invoice_number,
    send_invoice_email,
    send_plain_email,
    smtp_configured,
)
from utils.crm_models import (
    invoice_display_status,
    normalize_comment,
    normalize_email_event,
    normalize_invoice,
    to_amount,
    utc_now_iso,
)
from utils.crm_store import load_crm, save_crm
from utils.usage_guide import render_usage_guide
from utils import auth


# ── Session state ─────────────────────────────────────────────────────────────

def _init() -> None:
    defaults: dict[str, Any] = {
        "fin_view":       "dashboard",   # dashboard | create | preview
        "fin_crm_db":     None,
        "fin_crm_meta":   None,
        "fin_sel_id":     "",
        "fin_invoice":    None,           # in-progress / previewing invoice dict
        "fin_invoice_html": None,
        "fin_contact":    None,
        "fin_config":     {},
        "fin_flash":      "",
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


def _invalidate() -> None:
    st.session_state.fin_crm_db   = None
    st.session_state.fin_crm_meta = None


def _load_crm() -> tuple[list, dict]:
    if st.session_state.fin_crm_db is None:
        db, meta = load_crm(organization_id=auth.active_org_id())
        st.session_state.fin_crm_db   = db
        st.session_state.fin_crm_meta = meta
    return (
        st.session_state.fin_crm_db.get("contacts", []),
        st.session_state.fin_crm_meta or {},
    )


def _save(message: str) -> None:
    meta = st.session_state.fin_crm_meta or {}
    result = save_crm(
        st.session_state.fin_crm_db, sha=meta.get("sha"), message=message,
        organization_id=auth.active_org_id(),
    )
    if isinstance(result, dict):
        st.session_state.fin_crm_meta = {**meta, "sha": result.get("sha") or meta.get("sha")}


def _e(text: Any) -> str:
    return _html.escape(str(text or ""))


# ── Page CSS ──────────────────────────────────────────────────────────────────

_CSS = """
<style>
/* Finance-specific styles — brand vars come from streamlit_app.py global CSS */

.fin-cost-pill {
    display: inline-flex; align-items: center; gap: 7px;
    background: var(--green-bg); border: 1px solid rgba(46,139,77,.25);
    border-radius: 20px; padding: 4px 12px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10.5px; font-weight: 700; letter-spacing: .04em;
    color: var(--green); margin-bottom: 4px;
}
.fin-cost-pill .dot { width:6px;height:6px;background:var(--green);border-radius:50%; }

/* Cashflow snapshot cards */
.fin-stats {
    display: grid; grid-template-columns: repeat(4, minmax(0,1fr));
    gap: 10px; margin: 4px 0 6px;
}
.fin-stat {
    background: var(--cream-3); border: 1px solid var(--line-soft);
    border-radius: var(--r); padding: 14px 15px;
    position: relative; overflow: hidden;
}
.fin-stat::before {
    content:""; position:absolute; left:0; top:0; bottom:0; width:3px;
    background: var(--ink-mute);
}
.fin-stat.invoiced::before { background: var(--ink); }
.fin-stat.paid::before     { background: var(--green); }
.fin-stat.out::before      { background: var(--amber); }
.fin-stat.over::before     { background: var(--red); }
.fin-stat .n {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 21px; font-weight: 800; color: var(--ink); line-height: 1;
    word-break: break-word;
}
.fin-stat .l {
    font-size: 9.5px; letter-spacing: .1em; text-transform: uppercase;
    color: var(--ink-mute); margin-top: 6px;
    font-family: 'JetBrains Mono', monospace;
}
.fin-stat.paid .n { color: var(--green); }
.fin-stat.over .n { color: var(--red); }
@media (max-width: 640px) { .fin-stats { grid-template-columns: repeat(2,1fr); } }
@media (max-width: 720px) {
    .fin-head h2 { font-size: 26px; }
    .fin-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .fin-stat { padding: 12px; }
    .fin-stat .n { font-size: 18px; }
    .fin-row {
        grid-template-columns: 1fr;
        gap: 8px;
        padding: 14px;
    }
    .fin-row .fin-amt { text-align: left; }
    .fin-ready {
        flex-direction: column;
        align-items: flex-start;
        gap: 10px;
    }
    .fin-co-card { padding: 10px 12px; }
    .fin-co-card.sel { transform: none; }
    div[class*="st-key-finance_main_split"] [data-testid="stHorizontalBlock"] {
        flex-direction: column !important;
        gap: 16px !important;
    }
    div[class*="st-key-finance_main_split"] [data-testid="column"] {
        width: 100% !important;
        flex: 1 1 auto !important;
    }
}

/* Invoice ledger row */
.fin-row {
    border: 1px solid var(--line-soft); border-radius: var(--r);
    background: rgba(255,255,255,.65);
    padding: 12px 15px; margin-bottom: 8px;
    display: grid; grid-template-columns: 110px 1.5fr 1fr auto;
    gap: 14px; align-items: center;
    transition: border-color .15s, box-shadow .15s, transform .15s;
}
.fin-row:hover { border-color: rgba(46,139,77,.28); transform: translateY(-1px);
                 box-shadow: 0 10px 24px rgba(15,42,51,.06); }
.fin-row.over { border-color: rgba(169,61,61,.30); background: rgba(169,61,61,.03); }
.fin-num {
    font-family: 'JetBrains Mono', monospace; font-size: 11.5px; font-weight: 700;
    color: var(--green); letter-spacing: .02em;
}
.fin-co   { font-size: 14px; font-weight: 700; color: var(--ink); }
.fin-sub  { font-size: 11px; color: var(--ink-mute); margin-top: 2px;
            font-family: 'JetBrains Mono', monospace; }
.fin-amt  { font-family: 'Bricolage Grotesque', sans-serif; font-size: 16px;
            font-weight: 800; color: var(--ink); text-align: right;
            font-variant-numeric: tabular-nums; }

/* Status pills */
.fin-pill {
    display: inline-block; padding: 3px 9px; border-radius: 999px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 9.5px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
}
.fin-pill.draft     { background: rgba(15,42,51,.07);    color: var(--ink-mute); }
.fin-pill.sent      { background: rgba(15,101,139,.12);  color: #0D6E8C; }
.fin-pill.paid      { background: rgba(46,139,77,.15);   color: var(--green); }
.fin-pill.overdue   { background: rgba(169,61,61,.13);   color: var(--red); }
.fin-pill.cancelled { background: rgba(15,42,51,.06);    color: var(--ink-mute); }

/* Ready-to-invoice card */
.fin-ready {
    background: linear-gradient(135deg, rgba(46,139,77,.07), rgba(46,139,77,.02));
    border: 1px solid rgba(46,139,77,.22); border-radius: var(--r);
    padding: 12px 15px; margin-bottom: 8px;
    display: flex; align-items: center; justify-content: space-between; gap: 12px;
}
.fin-ready .rc-name { font-size: 14px; font-weight: 700; color: var(--ink); }
.fin-ready .rc-meta { font-size: 11px; color: var(--ink-mute); margin-top: 2px;
                      font-family: 'JetBrains Mono', monospace; }

/* Contact picker card (matches Proposal) */
.fin-co-card {
    padding: 10px 13px; border-radius: var(--r);
    border: 1.5px solid var(--line-soft); background: var(--cream-3);
    margin-bottom: 6px; transition: all .15s;
}
.fin-co-card:hover { border-color: var(--line-mid); background: #fff; }
.fin-co-card.sel {
    border-color: var(--green); background: var(--green-bg);
    box-shadow: 0 0 0 3px rgba(46,139,77,.10);
}
.fin-co-name { font-weight: 700; font-size: 13.5px; color: var(--ink); }
.fin-co-meta { font-size: 11.5px; color: var(--ink-mute); margin-top: 2px; }

/* Empty state */
.fin-empty { text-align:center; padding: 48px 20px; color: var(--ink-mute); }
.fin-empty .es-icon { font-size: 32px; margin-bottom: 12px; }
.fin-empty .es-title { font-size: 15px; font-weight: 700; margin-bottom: 6px; color: var(--ink); }
.fin-empty .es-body  { font-size: 13px; }

/* Sent banner */
.fin-flash {
    background: var(--green-bg); border: 1px solid rgba(46,139,77,.25);
    border-radius: var(--rs); padding: 13px 17px;
    font-size: 13.5px; color: var(--ink); line-height: 1.6; margin-bottom: 14px;
}
.fin-flash strong { color: var(--green); }

@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
    }
}
</style>
"""


# ── Main render ─────────────────────────────────────────────────────────────────

def render_finance_page() -> None:
    _init()

    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown("""
<div class="pg-eyebrow">
  <span class="dot"></span><span class="dash"></span>
  FOCUSCHAIN LABS · REVENUE
</div>
<h2 class="pg-hero">Finance <span class="accent">Agent</span></h2>
<p class="pg-sub">Won deal&nbsp;&nbsp;→&nbsp;&nbsp;invoice in one click&nbsp;&nbsp;→&nbsp;&nbsp;track payment&nbsp;&nbsp;→&nbsp;&nbsp;AI chases overdue</p>
<div class="fin-cost-pill"><div class="dot"></div>Invoicing is free (no API) &nbsp;·&nbsp; AI reminders ~1 Gemini call each</div>
""", unsafe_allow_html=True)
    render_usage_guide("finance")
    st.markdown("")

    view = st.session_state.fin_view
    if view == "create":
        _render_create()
    elif view == "preview":
        _render_preview()
    else:
        _render_dashboard()


# ── Dashboard view ──────────────────────────────────────────────────────────────

def _render_dashboard() -> None:
    contacts, _ = _load_crm()

    if st.session_state.fin_flash:
        st.markdown(f'<div class="fin-flash">{st.session_state.fin_flash}</div>',
                    unsafe_allow_html=True)
        st.session_state.fin_flash = ""

    # New-invoice button
    nc1, nc2 = st.columns([3, 1])
    with nc2:
        if st.button("+ New invoice", type="primary", use_container_width=True, key="fin_new"):
            st.session_state.fin_view   = "create"
            st.session_state.fin_sel_id = ""
            st.rerun()

    if not contacts:
        st.markdown("""
        <div class="fin-empty">
          <div class="es-icon">💰</div>
          <div class="es-title">No contacts yet</div>
          <div class="es-body">Run the Scout Agent and close a deal, then invoice it here.</div>
        </div>
        """, unsafe_allow_html=True)
        return

    today = utc_now_iso()[:10]
    snap = cashflow_snapshot(contacts, today=today)
    invoices = collect_invoices(contacts)

    # ── Cashflow snapshot ─────────────────────────────────────────────────────
    st.markdown('<div class="sec">Cashflow snapshot <span class="line"></span></div>',
                unsafe_allow_html=True)

    by_ccy = snap["by_currency"]
    if not by_ccy:
        st.caption("No invoices yet. Create your first invoice to see cashflow here.")
    else:
        # Show the dominant currency's totals as headline cards
        primary_ccy = max(by_ccy, key=lambda c: by_ccy[c]["invoiced"]) if by_ccy else "INR"
        b = by_ccy[primary_ccy]
        st.markdown(f"""
        <div class="fin-stats">
          <div class="fin-stat invoiced"><div class="n">{_e(fmt_money(b['invoiced'], primary_ccy))}</div><div class="l">Invoiced</div></div>
          <div class="fin-stat paid"><div class="n">{_e(fmt_money(b['paid'], primary_ccy))}</div><div class="l">Collected</div></div>
          <div class="fin-stat out"><div class="n">{_e(fmt_money(b['outstanding'], primary_ccy))}</div><div class="l">Outstanding</div></div>
          <div class="fin-stat over"><div class="n">{_e(fmt_money(b['overdue'], primary_ccy))}</div><div class="l">Overdue</div></div>
        </div>
        """, unsafe_allow_html=True)

        # Secondary currencies, if any
        for ccy, bucket in by_ccy.items():
            if ccy == primary_ccy:
                continue
            st.caption(
                f"{ccy}: {fmt_money(bucket['invoiced'], ccy)} invoiced · "
                f"{fmt_money(bucket['paid'], ccy)} collected · "
                f"{fmt_money(bucket['outstanding'], ccy)} outstanding"
            )

    # ── Overdue → AI dunning ──────────────────────────────────────────────────
    overdue = [
        inv for inv in invoices
        if invoice_display_status(inv, today=today) == "overdue"
    ]
    if overdue:
        st.markdown('<div class="sec">Overdue — chase payment <span class="line"></span></div>',
                    unsafe_allow_html=True)
        st.caption(
            "The agent drafts an escalating, human-sounding reminder. Level rises "
            "automatically the longer an invoice stays unpaid."
        )
        for inv in sorted(overdue, key=lambda x: x.get("due_date", "")):
            _render_overdue_row(inv, today)

    # ── Ready to invoice (won deals with no invoice) ──────────────────────────
    won_no_invoice = [
        c for c in contacts
        if (c.get("status") or "") == "won" and not (c.get("invoices") or [])
    ]
    if won_no_invoice:
        st.markdown('<div class="sec">Ready to invoice <span class="line"></span></div>',
                    unsafe_allow_html=True)
        st.caption("Won deals that don't have an invoice yet.")
        for c in won_no_invoice[:12]:
            name = c.get("company") or c.get("name") or "Unnamed"
            value = to_amount(c.get("value"))
            meta = c.get("name", "") if c.get("company") else ""
            rc1, rc2 = st.columns([3, 1])
            with rc1:
                st.markdown(f"""
                <div class="fin-ready">
                  <div>
                    <div class="rc-name">{_e(name)}</div>
                    <div class="rc-meta">{_e(meta)}{(' · deal value ' + fmt_money(value)) if value else ''}</div>
                  </div>
                </div>
                """, unsafe_allow_html=True)
            with rc2:
                if st.button("Invoice →", key=f"fin_inv_{c.get('id')}",
                             use_container_width=True):
                    st.session_state.fin_sel_id = c.get("id", "")
                    st.session_state.fin_view   = "create"
                    st.rerun()

    # ── Full invoice ledger ───────────────────────────────────────────────────
    st.markdown('<div class="sec">All invoices <span class="line"></span></div>',
                unsafe_allow_html=True)
    if not invoices:
        st.caption("No invoices yet.")
        return

    for inv in sorted(invoices, key=lambda x: x.get("issue_date", ""), reverse=True):
        _render_ledger_row(inv, today)


def _render_ledger_row(inv: dict, today: str) -> None:
    status  = invoice_display_status(inv, today=today)
    contact = inv.get("_contact") or {}
    company = contact.get("company") or contact.get("name") or inv.get("company") or "—"
    ccy     = inv.get("currency", "INR")
    due     = inv.get("due_date", "")
    row_cls = "fin-row over" if status == "overdue" else "fin-row"

    c1, c2 = st.columns([5, 1])
    with c1:
        st.markdown(f"""
        <div class="{row_cls}">
          <div><span class="fin-num">{_e(inv.get('number','—'))}</span></div>
          <div><div class="fin-co">{_e(company)}</div>
               <div class="fin-sub">issued {_e(inv.get('issue_date',''))} · due {_e(due)}</div></div>
          <div><span class="fin-pill {status}">{_e(status)}</span></div>
          <div class="fin-amt">{_e(fmt_money(inv.get('total'), ccy))}</div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        # Quick status actions in a popover
        with st.popover("Manage", use_container_width=True):
            st.caption(f"{inv.get('number','')} · {company}")
            if status != "paid":
                if st.button("✓ Mark paid", key=f"paid_{inv.get('id')}", use_container_width=True):
                    _set_invoice_status(inv, "paid")
                    st.session_state.fin_flash = f"Invoice <strong>{_e(inv.get('number',''))}</strong> marked paid."
                    _invalidate(); st.rerun()
            if status in ("draft",):
                if st.button("Mark sent", key=f"sent_{inv.get('id')}", use_container_width=True):
                    _set_invoice_status(inv, "sent")
                    _invalidate(); st.rerun()
            if st.button("Open / preview", key=f"open_{inv.get('id')}", use_container_width=True):
                _open_invoice_preview(inv, contact)
                st.rerun()
            if status != "cancelled" and status != "paid":
                if st.button("Cancel invoice", key=f"cancel_{inv.get('id')}", use_container_width=True):
                    _set_invoice_status(inv, "cancelled")
                    _invalidate(); st.rerun()


def _render_overdue_row(inv: dict, today: str) -> None:
    from datetime import datetime as _dt
    contact = inv.get("_contact") or {}
    company = contact.get("company") or contact.get("name") or "—"
    ccy     = inv.get("currency", "INR")
    due     = inv.get("due_date", "")
    days = 0
    try:
        days = (date.today() - _dt.fromisoformat(due[:10]).date()).days
    except (ValueError, TypeError):
        days = 0
    level = dunning_level_for(max(days, 0))
    prior = len(inv.get("dunning") or [])

    c1, c2 = st.columns([5, 1])
    with c1:
        st.markdown(f"""
        <div class="fin-row over">
          <div><span class="fin-num">{_e(inv.get('number','—'))}</span></div>
          <div><div class="fin-co">{_e(company)}</div>
               <div class="fin-sub">{days}d overdue · {prior} reminder{'s' if prior != 1 else ''} sent · level {level}</div></div>
          <div><span class="fin-pill overdue">overdue</span></div>
          <div class="fin-amt">{_e(fmt_money(inv.get('total'), ccy))}</div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        if st.button("Chase", key=f"chase_{inv.get('id')}", use_container_width=True, type="primary"):
            st.session_state[f"dun_open_{inv.get('id')}"] = True
            st.rerun()

    # Dunning compose panel
    if st.session_state.get(f"dun_open_{inv.get('id')}"):
        _render_dunning_panel(inv, contact, level)


def _render_dunning_panel(inv: dict, contact: dict, level: int) -> None:
    iid = inv.get("id", "")
    with st.container():
        st.markdown('<div class="sec">AI payment reminder <span class="line"></span></div>',
                    unsafe_allow_html=True)

        draft_key = f"dun_draft_{iid}"
        to_email = contact.get("email", "")

        if not os.getenv("GEMINI_API_KEY"):
            st.warning("GEMINI_API_KEY not configured — needed to draft the reminder.")

        gen_c, lvl_c = st.columns([1, 1])
        with lvl_c:
            chosen_level = st.selectbox(
                "Escalation level",
                options=[1, 2, 3],
                index=level - 1,
                format_func=lambda x: {1: "1 · Gentle nudge", 2: "2 · Firmer", 3: "3 · Final notice"}[x],
                key=f"dun_lvl_{iid}",
            )
        with gen_c:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            if st.button("Draft reminder with AI", key=f"dun_gen_{iid}",
                         use_container_width=True, disabled=not os.getenv("GEMINI_API_KEY")):
                with st.spinner("Drafting…"):
                    try:
                        st.session_state[draft_key] = compose_dunning_email(
                            inv, contact, level=chosen_level,
                            sender_name=os.getenv("SENDER_NAME", ""),
                            sender_company=os.getenv("SENDER_COMPANY", ""),
                        )
                    except Exception as exc:
                        st.error(f"Draft failed: {exc}")

        draft = st.session_state.get(draft_key)
        if draft:
            subject = st.text_input("Subject", value=draft.get("subject", ""), key=f"dun_subj_{iid}")
            body = st.text_area("Reminder body", value=draft.get("body", ""), height=160, key=f"dun_body_{iid}")
            to_addr = st.text_input("Send to", value=to_email, key=f"dun_to_{iid}")

            sm_ok = smtp_configured()
            if not sm_ok:
                st.warning("Gmail SMTP not configured — add SMTP_FROM_EMAIL + SMTP_APP_PASSWORD to send.")

            s1, s2 = st.columns(2)
            with s1:
                if st.button("Send reminder", type="primary", key=f"dun_send_{iid}",
                             use_container_width=True, disabled=not sm_ok):
                    with st.spinner("Sending…"):
                        res = send_plain_email(to_addr, subject, body)
                    if res.get("ok"):
                        _record_dunning(inv, contact, chosen_level, to_addr, subject, body)
                        st.session_state.fin_flash = (
                            f"Reminder sent to <strong>{_e(to_addr)}</strong> for invoice "
                            f"<strong>{_e(inv.get('number',''))}</strong>."
                        )
                        st.session_state.pop(draft_key, None)
                        st.session_state.pop(f"dun_open_{iid}", None)
                        _invalidate(); st.rerun()
                    else:
                        st.error(res.get("error", "Send failed"))
            with s2:
                if st.button("Close", key=f"dun_close_{iid}", use_container_width=True):
                    st.session_state.pop(f"dun_open_{iid}", None)
                    st.rerun()
        else:
            if st.button("Close", key=f"dun_close2_{iid}"):
                st.session_state.pop(f"dun_open_{iid}", None)
                st.rerun()
        st.markdown("")


# ── Create view ─────────────────────────────────────────────────────────────────

def _render_create() -> None:
    contacts, _ = _load_crm()

    top1, top2 = st.columns([3, 1])
    with top2:
        if st.button("← Back", use_container_width=True, key="fin_create_back"):
            st.session_state.fin_view = "dashboard"
            st.rerun()

    if not contacts:
        st.info("No CRM contacts yet. Run the Scout Agent and add leads first.")
        return

    # Prioritise won / proposal stage
    won_conts  = [c for c in contacts if (c.get("status") or "") == "won"]
    prop_conts = [c for c in contacts if (c.get("status") or "") in ("proposal", "qualified")]
    other_conts = [c for c in contacts
                   if (c.get("status") or "") not in ("won", "proposal", "qualified")]

    with st.container(key="finance_main_split"):
        col_sel, col_cfg = st.columns([1.3, 1.7], gap="large")

        with col_sel:
            st.markdown('<div class="sec">Bill to <span class="line"></span></div>',
                        unsafe_allow_html=True)
            sel_id = st.session_state.fin_sel_id

            def _card(c: dict) -> None:
                cid = c.get("id", "")
                name = c.get("company") or c.get("name") or "Unnamed"
                person = c.get("name", "") if c.get("company") else ""
                sub = " · ".join(p for p in [person, c.get("email", "")] if p)
                is_sel = cid == sel_id
                cls = "fin-co-card sel" if is_sel else "fin-co-card"
                st.markdown(f"""
                <div class="{cls}">
                  <div class="fin-co-name">{_e(name)}</div>
                  <div class="fin-co-meta">{_e(sub)}</div>
                </div>
                """, unsafe_allow_html=True)
                if st.button("✓ Selected" if is_sel else "Select",
                             key=f"fin_sel_{cid}", use_container_width=True,
                             type="primary" if is_sel else "secondary"):
                    st.session_state.fin_sel_id = cid
                    st.rerun()

            for label, group in [
                ("Won deals", won_conts),
                ("Proposal / qualified", prop_conts),
                ("Other contacts", other_conts),
            ]:
                if not group:
                    continue
                st.caption(label)
                for c in sorted(group, key=lambda x: -int(x.get("score") or 0))[:25]:
                    _card(c)

        with col_cfg:
            sel = next((c for c in contacts if c.get("id") == sel_id), None)
            if not sel:
                st.markdown('<div class="sec">Invoice details <span class="line"></span></div>',
                            unsafe_allow_html=True)
                st.info("Select who to bill on the left to continue.")
                return

            company = sel.get("company") or sel.get("name") or "Client"
            st.markdown(
                f'<div class="sec">Invoice for '
                f'<span style="color:var(--green);">{_e(company)}</span> <span class="line"></span></div>',
                unsafe_allow_html=True,
            )

            all_numbers = [inv.get("number", "") for inv in collect_invoices(contacts)]
            suggested_num = next_invoice_number(all_numbers)

            nc1, nc2 = st.columns(2)
            with nc1:
                number = st.text_input("Invoice number", value=suggested_num, key="fin_number")
            with nc2:
                currency = st.selectbox("Currency", ["INR", "USD", "EUR", "GBP", "AED"],
                                        index=0, key="fin_currency")

            dc1, dc2 = st.columns(2)
            with dc1:
                issue_date = st.date_input("Issue date", value=date.today(), key="fin_issue")
            with dc2:
                net_days = st.selectbox("Payment terms", [7, 14, 30, 45, 60],
                                        index=1, format_func=lambda d: f"Net {d} days", key="fin_net")

            st.markdown("**Line items**")
            st.caption("Item · Qty · Rate — amount auto-calculates. Leave a row blank to skip it.")

            default_rows = line_items_from_proposal(sel)
            n_rows = st.number_input("Number of line items", min_value=1, max_value=10,
                                     value=max(1, len(default_rows)), key="fin_nrows")
            line_items = []
            for i in range(int(n_rows)):
                d = default_rows[i] if i < len(default_rows) else {}
                lc1, lc2, lc3 = st.columns([3, 1, 1.4])
                with lc1:
                    item = st.text_input(f"Item {i+1}", value=d.get("item", ""),
                                         key=f"fin_item_{i}", label_visibility="collapsed",
                                         placeholder=f"Line item {i+1}")
                with lc2:
                    qty = st.text_input(f"Qty {i+1}", value=str(int(d.get("qty", 1)) if d else 1),
                                        key=f"fin_qty_{i}", label_visibility="collapsed",
                                        placeholder="Qty")
                with lc3:
                    rate = st.text_input(f"Rate {i+1}", value=str(d.get("rate", "")) if d.get("rate") else "",
                                         key=f"fin_rate_{i}", label_visibility="collapsed",
                                         placeholder="Rate")
                if item.strip():
                    line_items.append({"item": item.strip(), "qty": qty or 1, "rate": rate or 0})

            tc1, tc2 = st.columns(2)
            with tc1:
                tax_rate = st.text_input("Tax / GST %", value=os.getenv("INVOICE_TAX_RATE", "0"),
                                         key="fin_tax")
            with tc2:
                subtotal = sum(to_amount(li["rate"]) * to_amount(li["qty"]) for li in line_items)
                tax_amt = subtotal * to_amount(tax_rate) / 100.0
                st.markdown(
                    f"<div style='padding-top:6px'><span style='font-family:JetBrains Mono,monospace;"
                    f"font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-mute)'>"
                    f"Total</span><br><span style='font-family:Bricolage Grotesque;font-size:22px;"
                    f"font-weight:800;color:var(--green)'>{_e(fmt_money(subtotal + tax_amt, currency))}</span></div>",
                    unsafe_allow_html=True,
                )

            notes = st.text_area("Notes (optional)", key="fin_notes",
                                 placeholder="Thank you for your business. Payment due within terms above.",
                                 height=70)

            st.markdown("")
            can_build = bool(sel_id and line_items)
            if not line_items:
                st.caption("Add at least one line item with a description.")

            if st.button("Build invoice", type="primary", use_container_width=True,
                         disabled=not can_build, key="fin_build"):
                config = {
                    "number":     number.strip(),
                    "currency":   currency,
                    "issue_date": issue_date.isoformat(),
                    "net_days":   int(net_days),
                    "line_items": line_items,
                    "tax_rate":   to_amount(tax_rate),
                    "notes":      notes.strip(),
                    "status":     "draft",
                    "sender_name":    os.getenv("SENDER_NAME", ""),
                    "sender_company": os.getenv("SENDER_COMPANY", "FocusChain Labs"),
                    "sender_email":   os.getenv("SMTP_FROM_EMAIL", ""),
                    "payment_instructions": os.getenv("PAYMENT_INSTRUCTIONS", ""),
                }
                invoice = build_invoice(sel, config)
                st.session_state.fin_invoice      = invoice
                st.session_state.fin_invoice_html = build_invoice_html(invoice, config, sel)
                st.session_state.fin_contact      = sel
                st.session_state.fin_config       = config
                st.session_state.fin_view         = "preview"
                st.rerun()


# ── Preview view ────────────────────────────────────────────────────────────────

def _render_preview() -> None:
    invoice = st.session_state.fin_invoice
    inv_html = st.session_state.fin_invoice_html
    contact = st.session_state.fin_contact or {}
    config  = st.session_state.fin_config or {}

    if not invoice or not inv_html:
        st.error("No invoice to display.")
        if st.button("← Back"):
            st.session_state.fin_view = "dashboard"
            st.rerun()
        return

    company = contact.get("company") or contact.get("name") or "Client"
    currency = invoice.get("currency", "INR")
    saved = bool(st.session_state.get("fin_saved_id") == invoice.get("id"))

    # Action bar
    ac1, ac2, ac3, ac4 = st.columns(4)
    with ac1:
        if st.button("← Edit", use_container_width=True, key="fin_pv_back"):
            st.session_state.fin_view = "create"
            st.rerun()
    with ac2:
        fname = f"invoice_{(invoice.get('number') or company).lower().replace(' ', '_').replace('-', '_')}.html"
        st.download_button("Download HTML", data=inv_html.encode("utf-8"),
                           file_name=fname, mime="text/html",
                           use_container_width=True, key="fin_dl")
    with ac3:
        if st.button("Save to CRM", use_container_width=True, key="fin_save"):
            err = _save_invoice_to_crm(invoice, contact)
            if err:
                st.error(err)
            else:
                st.session_state.fin_saved_id = invoice.get("id")
                st.success(f"Invoice {invoice.get('number','')} saved to {company}.")
                _invalidate()
                st.rerun()
    with ac4:
        if st.button("Send invoice", type="primary", use_container_width=True, key="fin_send_btn"):
            st.session_state.fin_show_send = not st.session_state.get("fin_show_send", False)
            st.rerun()

    if saved:
        st.caption(f"✓ Saved to CRM · status: {invoice.get('status','draft')}")

    # Send panel
    if st.session_state.get("fin_show_send"):
        _render_send_panel(invoice, inv_html, contact, config)

    st.caption(
        "To save as PDF: download the HTML, open in Chrome/Safari, "
        "press Cmd+P (Ctrl+P) → 'Save as PDF'."
    )
    st.markdown("")
    st.markdown('<div class="sec">Preview <span class="line"></span></div>',
                unsafe_allow_html=True)
    components.html(inv_html, height=900, scrolling=True)


def _render_send_panel(invoice: dict, inv_html: str, contact: dict, config: dict) -> None:
    company = contact.get("company") or contact.get("name") or "Client"
    with st.container():
        st.markdown('<div class="sec">Send invoice <span class="line"></span></div>',
                    unsafe_allow_html=True)
        to_email = st.text_input("Recipient email", value=contact.get("email", ""), key="fin_to")
        subject = st.text_input(
            "Subject",
            value=f"Invoice {invoice.get('number','')} from {config.get('sender_company','FocusChain Labs')}",
            key="fin_subj",
        )
        intro = st.text_area(
            "Intro (shown above the invoice)",
            value=(
                f"Hi {contact.get('name', 'there')},\n\n"
                f"Please find invoice {invoice.get('number','')} for "
                f"{fmt_money(invoice.get('total'), invoice.get('currency','INR'))} below. "
                f"Payment is due by {invoice.get('due_date','')}.\n\n"
                f"Thank you for your business — just reply here with any questions."
            ),
            height=120, key="fin_intro",
        )
        sm_ok = smtp_configured()
        if not sm_ok:
            st.warning("Gmail SMTP not configured. Add SMTP_FROM_EMAIL + SMTP_APP_PASSWORD to send.")

        s1, s2 = st.columns(2)
        with s1:
            if st.button("Send now", type="primary", use_container_width=True,
                         disabled=not sm_ok, key="fin_send_now"):
                with st.spinner("Sending…"):
                    res = send_invoice_email(to_email, subject, intro, inv_html)
                if res.get("ok"):
                    # Mark sent + log to CRM
                    invoice["status"] = "sent"
                    _save_invoice_to_crm(invoice, contact, email_to=to_email, email_subject=subject)
                    st.session_state.fin_show_send = False
                    st.session_state.fin_flash = (
                        f"Invoice <strong>{_e(invoice.get('number',''))}</strong> sent to "
                        f"<strong>{_e(to_email)}</strong> · status → sent."
                    )
                    st.session_state.fin_view = "dashboard"
                    _invalidate()
                    st.rerun()
                else:
                    st.error(res.get("error", "Send failed"))
        with s2:
            if st.button("Cancel", use_container_width=True, key="fin_send_cancel"):
                st.session_state.fin_show_send = False
                st.rerun()
        st.markdown("")


# ── CRM persistence helpers ─────────────────────────────────────────────────────

def _upsert_invoice_on_contact(db: dict, contact_id: str, invoice: dict) -> bool:
    """Insert or replace the invoice in the contact's invoices list. Returns True if found."""
    for c in db.get("contacts", []):
        if c.get("id") == contact_id:
            invs = c.setdefault("invoices", [])
            for i, existing in enumerate(invs):
                if existing.get("id") == invoice.get("id"):
                    invs[i] = invoice
                    break
            else:
                invs.insert(0, invoice)
            c["updated_at"] = utc_now_iso()
            return True
    return False


def _save_invoice_to_crm(
    invoice: dict, contact: dict,
    *, email_to: str = "", email_subject: str = "",
) -> str | None:
    """Persist the invoice onto the CRM contact, with a comment + optional email event."""
    contacts, meta = _load_crm()
    db = st.session_state.fin_crm_db
    cid = contact.get("id", "")

    invoice = normalize_invoice({**invoice, "updated_at": utc_now_iso()})
    if not _upsert_invoice_on_contact(db, cid, invoice):
        return f"Contact not found in CRM for '{contact.get('company','')}'."

    # Add an audit comment
    ccy = invoice.get("currency", "INR")
    body = (
        f"[Invoice {invoice.get('number','')} — {invoice.get('status','draft')}]\n"
        f"Amount: {fmt_money(invoice.get('total'), ccy)}\n"
        f"Issued: {invoice.get('issue_date','')} · Due: {invoice.get('due_date','')}"
    )
    comment = normalize_comment({"author": "Finance Agent", "body": body, "type": "invoice"})
    for c in db.get("contacts", []):
        if c.get("id") == cid:
            c.setdefault("comments", []).insert(0, comment)
            if email_to:
                c.setdefault("email_events", []).insert(0, normalize_email_event({
                    "to": email_to, "subject": email_subject,
                    "body": f"(Invoice {invoice.get('number','')} sent via Finance Agent)",
                    "source": "finance_agent",
                }))
            break

    _save(f"Finance: invoice {invoice.get('number','')} for {contact.get('company', contact.get('name',''))}")
    return None


def _set_invoice_status(inv: dict, status: str) -> None:
    """Update an invoice's stored status in the CRM (used from the ledger)."""
    contacts, meta = _load_crm()
    db = st.session_state.fin_crm_db
    cid = (inv.get("_contact") or {}).get("id") or inv.get("contact_id")
    updated = normalize_invoice({
        **{k: v for k, v in inv.items() if k != "_contact"},
        "status": status,
        "paid_at": utc_now_iso()[:10] if status == "paid" else inv.get("paid_at", ""),
        "updated_at": utc_now_iso(),
    })
    _upsert_invoice_on_contact(db, cid, updated)
    _save(f"Finance: invoice {inv.get('number','')} → {status}")


def _record_dunning(inv: dict, contact: dict, level: int, to: str, subject: str, body: str) -> None:
    """Log a sent reminder onto the invoice + email_events thread."""
    contacts, meta = _load_crm()
    db = st.session_state.fin_crm_db
    cid = (inv.get("_contact") or {}).get("id") or inv.get("contact_id") or contact.get("id")

    dunning = list(inv.get("dunning") or [])
    dunning.append({"level": level, "sent_at": utc_now_iso(), "to": to})
    updated = normalize_invoice({
        **{k: v for k, v in inv.items() if k != "_contact"},
        "dunning": dunning,
        "updated_at": utc_now_iso(),
    })
    _upsert_invoice_on_contact(db, cid, updated)

    for c in db.get("contacts", []):
        if c.get("id") == cid:
            c.setdefault("email_events", []).insert(0, normalize_email_event({
                "to": to, "subject": subject, "body": body, "source": "finance_agent",
            }))
            break

    _save(f"Finance: reminder L{level} sent for invoice {inv.get('number','')}")


def _open_invoice_preview(inv: dict, contact: dict) -> None:
    """Load an existing invoice into the preview view."""
    config = {
        "sender_name":    os.getenv("SENDER_NAME", ""),
        "sender_company": os.getenv("SENDER_COMPANY", "FocusChain Labs"),
        "sender_email":   os.getenv("SMTP_FROM_EMAIL", ""),
        "payment_instructions": os.getenv("PAYMENT_INSTRUCTIONS", ""),
    }
    clean = {k: v for k, v in inv.items() if k != "_contact"}
    st.session_state.fin_invoice      = clean
    st.session_state.fin_invoice_html = build_invoice_html(clean, config, contact)
    st.session_state.fin_contact      = contact
    st.session_state.fin_config       = config
    st.session_state.fin_view         = "preview"
