"""FocusChain CRM — simple contact book backed by GitHub."""

from __future__ import annotations

import html
import random
import re
import string
from datetime import date, datetime, timedelta

import streamlit as st

import utils.crm_models as crm_models
import utils.tenancy as tenancy
from utils import auth
from agent.broadcast_agent import compose_broadcast, personalise
from agent.crm_search_agent import resolve_status_update, search_contacts
from agent.reach_agent import send_email_smtp, smtp_configured
from utils.crm_store import github_configured, import_leads_to_crm, load_crm, save_crm
from utils.llm import llm_configured
from utils.usage_guide import render_usage_guide
from utils.whatsapp import (
    broadcast_feasibility,
    extract_sent_message_id,
    send_whatsapp_template,
    send_whatsapp_text,
    whatsapp_configured,
)
from utils.wa_events import append_outbound_event, campaign_summary


CRM_STATUSES = getattr(crm_models, "CRM_STATUSES", ["new", "contacted", "qualified", "proposal", "won", "lost"])
STATUS_LABELS = getattr(
    crm_models,
    "STATUS_LABELS",
    {
        "new": "New",
        "contacted": "Contacted",
        "qualified": "Qualified",
        "proposal": "Proposal",
        "won": "Won",
        "lost": "Lost",
    },
)
CRM_SOURCE_OPTIONS = getattr(crm_models, "CRM_SOURCE_OPTIONS", ["linkedin", "referral", "inbound", "whatsapp", "event", "other"])
SOURCE_LABELS = getattr(
    crm_models,
    "SOURCE_LABELS",
    {
        "linkedin": "LinkedIn",
        "referral": "Referral",
        "inbound": "Inbound",
        "whatsapp": "WhatsApp",
        "event": "Event",
        "other": "Other",
    },
)
DEAL_STATUSES = getattr(crm_models, "DEAL_STATUSES", ["open", "won", "lost"])
DEAL_STATUS_LABELS = getattr(crm_models, "DEAL_STATUS_LABELS", {"open": "Open", "won": "Won", "lost": "Lost"})

contact_fingerprint = crm_models.contact_fingerprint
display_name = crm_models.display_name
merge_contacts = crm_models.merge_contacts
new_contact_id = crm_models.new_contact_id
normalize_contact = crm_models.normalize_contact
normalize_status = crm_models.normalize_status
next_pipeline_status = crm_models.next_pipeline_status
utc_now_iso = crm_models.utc_now_iso


def generate_meet_link() -> str:
    """Generate a unique Google Meet link using random meeting code."""
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
    return f"https://meet.google.com/{suffix}"


AI_INTAKE_TEMPLATES = [
    {
        "label": "Expo",
        "source": "event",
        "icon": "✦",
        "desc": "Met at event or booth",
        "example": "Met at expo — Rajesh, Prestige Group, 9876543210, wants 3BHK Whitefield demo",
    },
    {
        "label": "Referral",
        "source": "referral",
        "icon": "◎",
        "desc": "Introduced by partner",
        "example": "SN Realtors referral — priya@zenith.in, founder Zenith Interiors, follow up Friday",
    },
    {
        "label": "LinkedIn",
        "source": "linkedin",
        "icon": "in",
        "desc": "Inbound or outbound social",
        "example": "LinkedIn inbound — hiring sales head, Bangalore, budget 2Cr+",
    },
]


def _render_ai_template_picker(*, active: int) -> None:
    """Source selector — each option is a styled card button."""
    st.markdown('<div class="ai-template-row">', unsafe_allow_html=True)
    cols = st.columns(len(AI_INTAKE_TEMPLATES))
    for i, tmpl in enumerate(AI_INTAKE_TEMPLATES):
        is_active = i == active
        slot_cls = "ai-tmpl-slot is-active" if is_active else "ai-tmpl-slot"
        with cols[i]:
            st.markdown(f'<div class="{slot_cls}">', unsafe_allow_html=True)
            if st.button(
                f'{tmpl["icon"]}  {tmpl["label"]}',
                key=f"ai_ex_{i}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
                help=tmpl["desc"],
            ):
                st.session_state["_ai_active_template"] = i
                st.session_state["_ai_example_placeholder"] = tmpl["example"]
                st.session_state["_ai_template_source"] = tmpl["source"]
                st.session_state["ai_text"] = ""
                st.rerun()
            st.markdown(
                f'<span class="tmpl-desc-below">{html.escape(tmpl["desc"])}</span></div>',
                unsafe_allow_html=True,
            )
    st.markdown("</div>", unsafe_allow_html=True)


def _render_ai_dialog_header(*, title: str, subtitle: str, step: str = "capture") -> None:
    st.markdown(
        f'<div class="ai-dialog-head">'
        f'<p class="ai-dialog-kicker">CRM · New lead</p>'
        f'<p class="ai-dialog-title">{html.escape(title)}</p>'
        f'<p class="ai-dialog-sub">{html.escape(subtitle)}</p>'
        f"</div>",
        unsafe_allow_html=True,
    )


def _resolve_ai_capture_text() -> str:
    """Return typed notes, or the active template example if the box is still empty."""
    typed = (st.session_state.get("ai_text") or "").strip()
    if typed:
        return typed
    idx = st.session_state.get("_ai_active_template", -1)
    if 0 <= idx < len(AI_INTAKE_TEMPLATES):
        return AI_INTAKE_TEMPLATES[idx]["example"]
    return ""


def normalize_source(raw: str) -> str:
    fn = getattr(crm_models, "normalize_source", None)
    if fn:
        return fn(raw)
    slug = (raw or "other").lower().strip().replace(" ", "_")
    aliases = {"agent": "other", "manual": "other", "website": "inbound", "web": "inbound", "wa": "whatsapp"}
    slug = aliases.get(slug, slug)
    return slug if slug in CRM_SOURCE_OPTIONS else "other"


def normalize_deal_status(raw: str, *, stage: str = "") -> str:
    fn = getattr(crm_models, "normalize_deal_status", None)
    if fn:
        return fn(raw, stage=stage)
    if not raw and stage in {"won", "lost"}:
        return stage
    slug = (raw or "open").lower().strip().replace(" ", "_")
    aliases = {"active": "open", "closed_won": "won", "closed_lost": "lost"}
    slug = aliases.get(slug, slug)
    return slug if slug in DEAL_STATUSES else "open"


def normalize_email_event(raw: dict) -> dict:
    fn = getattr(crm_models, "normalize_email_event", None)
    if fn:
        return fn(raw)
    now = utc_now_iso()
    return {
        "id": raw.get("id") or new_contact_id(),
        "direction": (raw.get("direction") or "sent").strip().lower(),
        "sent_at": str(raw.get("sent_at") or raw.get("date") or now).strip(),
        "from": (raw.get("from") or raw.get("sender") or "").strip(),
        "to": (raw.get("to") or raw.get("recipient") or "").strip(),
        "subject": (raw.get("subject") or "").strip(),
        "body": (raw.get("body") or raw.get("message") or "").strip(),
        "summary": (raw.get("summary") or raw.get("insight") or "").strip(),
        "source": (raw.get("source") or "manual").strip(),
        "created_at": raw.get("created_at") or now,
    }


def normalize_comment(raw: dict) -> dict:
    fn = getattr(crm_models, "normalize_comment", None)
    if fn:
        return fn(raw)
    return {
        "id": raw.get("id") or new_contact_id(),
        "created_at": raw.get("created_at") or utc_now_iso(),
        "author": (raw.get("author") or raw.get("owner") or "").strip(),
        "body": (raw.get("body") or raw.get("comment") or raw.get("note") or "").strip(),
        "subject": (raw.get("subject") or "").strip(),
        "meeting_link": (raw.get("meeting_link") or "").strip(),
        "source": (raw.get("source") or "manual").strip(),
    }


def normalize_contact_person(raw: dict) -> dict:
    fn = getattr(crm_models, "normalize_contact_person", None)
    if fn:
        return fn(raw)
    return {
        "id": raw.get("id") or new_contact_id(),
        "name": (raw.get("name") or raw.get("contact_name") or "").strip(),
        "title": (raw.get("title") or raw.get("contact_title") or "").strip(),
        "email": (raw.get("email") or raw.get("contact_email") or "").strip(),
        "phone": (raw.get("phone") or "").strip(),
        "role": (raw.get("role") or "").strip(),
        "created_at": raw.get("created_at") or utc_now_iso(),
    }


CRM_CSS = """
<style>
.crm-shell {
    display: flex;
    flex-direction: column;
    gap: 18px;
}
.crm-head {
    display: flex; align-items: flex-start; justify-content: space-between;
    gap: 16px; margin-bottom: 6px; flex-wrap: wrap;
}
.crm-head h2 {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 30px; font-weight: 800; color: var(--ink);
    margin: 0 0 4px 0; letter-spacing: 0;
}
.crm-head p { margin: 0; color: var(--ink-mute); font-size: 14px; max-width: 620px; line-height: 1.5; }
.crm-sync {
    display: inline-flex; align-items: center; gap: 7px;
    padding: 6px 11px; border-radius: 999px; font-size: 11px; font-weight: 700;
    border: 1px solid var(--line-soft); background: var(--cream-3);
    white-space: nowrap;
}
.crm-sync.ok { color: var(--green); background: var(--green-bg); border-color: rgba(46,139,77,.22); }
.crm-sync.warn { color: var(--amber); background: var(--amber-bg); border-color: rgba(183,121,31,.22); }
.crm-sync .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.crm-stats {
    display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 10px; margin-bottom: 2px;
}
.crm-stat {
    background: var(--cream-3); border: 1px solid var(--line-soft);
    border-radius: var(--r); padding: 14px 15px;
}
.crm-stat .n {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 24px; font-weight: 800; color: var(--ink); line-height: 1;
}
.crm-stat .l {
    font-size: 10px; letter-spacing: .08em; text-transform: uppercase;
    color: var(--ink-mute); margin-top: 5px;
}
.crm-add-box {
    background: var(--cream-3); border: 1px solid var(--line-soft);
    border-radius: var(--r); padding: 16px 18px; margin: 10px 0 0;
}
.crm-add-box .label {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 18px; font-weight: 800; color: var(--ink); margin-bottom: 2px;
}
.crm-add-box .hint { font-size: 13px; color: var(--ink-mute); line-height: 1.45; }
.crm-list { display: flex; flex-direction: column; gap: 10px; }

/* Ledger header */
.crm-ledger-head {
    display: grid;
    grid-template-columns: minmax(0, 2.5fr) minmax(0, 1.8fr) minmax(0, 1.4fr);
    gap: 14px;
    padding: 0 18px 8px;
    margin-bottom: 4px;
    color: var(--ink-mute);
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    letter-spacing: .16em;
    text-transform: uppercase;
}
.crm-ledger-head span { display: inline-flex; align-items: center; gap: 8px; }
.crm-ledger-head .line {
    height: 1px;
    flex: 1;
    background: linear-gradient(90deg, rgba(15,42,51,.12), transparent);
}
.crm-lead-hit { margin: 0; pointer-events: none; }
/* The whole card is a plain link → taps open the lead reliably on mobile
   (no invisible-button overlay, no :has() positioning to misfire). */
.crm-lead-link {
    display: block;
    text-decoration: none;
    color: inherit;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
}
.crm-lead-link + .crm-lead-link { margin-top: 10px; }
.crm-lead-link:hover .crm-lead-card {
    border-color: rgba(46,139,77,.38);
    background: linear-gradient(180deg, #ffffff, rgba(253,252,249,.96));
    box-shadow:
      0 2px 4px rgba(15,42,51,.05),
      0 18px 38px -16px rgba(15,42,51,.28),
      0 24px 52px -20px rgba(46,139,77,.32);
    transform: translateY(-3px);
}
.crm-lead-link:hover .crm-lead-card::before { opacity: 1; }
.crm-lead-link:hover .crm-rail { height: 66px; opacity: 1; }
.crm-lead-link:hover .crm-mono {
    transform: scale(1.05);
    box-shadow: inset 0 1px 0 rgba(255,255,255,.9), 0 6px 14px -4px rgba(15,42,51,.3);
}
.crm-lead-link:hover .crm-lead-chev {
    color: #fff; background: var(--green); border-color: var(--green);
    transform: translateX(2px);
}
.crm-lead-link:active .crm-lead-card {
    transform: translateY(-1px) scale(.992);
    transition-duration: .08s;
}
/* Lead row — one invisible tap target over the full card (on_click, no column split). */
div[class*="st-key-crm_row_"] {
    position: relative !important;
    margin-bottom: 10px !important;
}
div[class*="st-key-crm_row_"] [data-testid="stElementContainer"]:has(.crm-lead-hit) {
    pointer-events: none !important;
    margin: 0 !important;
}
div[class*="st-key-crm_row_"] [data-testid="stElementContainer"]:has(.crm-lead-hit) + [data-testid="stElementContainer"] {
    position: absolute !important;
    top: 0 !important;
    left: 0 !important;
    right: 0 !important;
    height: 92px !important;
    z-index: 4 !important;
    margin: 0 !important;
    padding: 0 !important;
    pointer-events: auto !important;
}
div[class*="st-key-crm_row_"] [data-testid="stElementContainer"]:has(.crm-lead-hit) + [data-testid="stElementContainer"] [data-testid="stButton"] {
    margin: 0 !important;
    height: 92px !important;
}
div[class*="st-key-crm_row_"] [data-testid="stElementContainer"]:has(.crm-lead-hit) + [data-testid="stElementContainer"] button {
    width: 100% !important;
    min-height: 92px !important;
    height: 92px !important;
    opacity: 0 !important;
    border: none !important;
    background: transparent !important;
    cursor: pointer !important;
    box-shadow: none !important;
    touch-action: manipulation !important;
    -webkit-tap-highlight-color: transparent !important;
}
div[class*="st-key-crm_row_"]:hover .crm-lead-card {
    border-color: rgba(46,139,77,.38);
    background: linear-gradient(180deg, #ffffff, rgba(253,252,249,.96));
    box-shadow:
      0 2px 4px rgba(15,42,51,.05),
      0 18px 38px -16px rgba(15,42,51,.28),
      0 24px 52px -20px rgba(46,139,77,.32);
    transform: translateY(-2px);
}
div[class*="st-key-crm_row_"]:hover .crm-lead-card::before { opacity: 1; }
div[class*="st-key-crm_row_"]:hover .crm-rail { height: 66px; opacity: 1; }
div[class*="st-key-crm_row_"]:hover .crm-mono {
    transform: scale(1.05);
    box-shadow: inset 0 1px 0 rgba(255,255,255,.9), 0 6px 14px -4px rgba(15,42,51,.3);
}
div[class*="st-key-crm_row_"]:hover .crm-lead-chev {
    color: #fff;
    background: var(--green);
    border-color: var(--green);
    transform: translateX(2px);
    box-shadow: 0 10px 24px -10px rgba(46,139,77,.45);
}
div[class*="st-key-crm_row_"]:has(button:active) .crm-lead-card {
    transform: translateY(-1px) scale(.992);
    transition-duration: .08s;
}
.crm-lead-card {
    position: relative;
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 0 20px 0 26px;
    height: 92px;
    border: 1px solid var(--line-soft);
    border-radius: 16px;
    background: linear-gradient(180deg, #ffffff, var(--cream-3));
    box-shadow:
      0 1px 2px rgba(15,42,51,.04),
      0 8px 18px -12px rgba(15,42,51,.22),
      inset 0 1px 0 rgba(255,255,255,.75);
    transition: transform .28s var(--ease-out), box-shadow .28s var(--ease-out),
                border-color .28s var(--ease-out), background .28s var(--ease-out);
    animation: cardIn .42s var(--ease-out) both;
    overflow: hidden;
}
/* Left status accent rail — a quiet colour cue for the lead's stage. */
.crm-rail {
    position: absolute;
    left: 0; top: 50%;
    transform: translateY(-50%);
    width: 4px; height: 44px;
    border-radius: 0 4px 4px 0;
    background: var(--line-mid);
    opacity: .9;
    transition: height .28s var(--ease-out), opacity .28s var(--ease-out);
}
.crm-rail.new, .crm-rail.won { background: var(--green); }
.crm-rail.contacted, .crm-rail.meeting { background: #3B82F6; }
.crm-rail.qualified { background: #A855F7; }
.crm-rail.proposal { background: var(--amber); }
.crm-rail.nurture { background: var(--ink-mute); }
.crm-rail.lost { background: var(--red); }
/* Soft glow that warms the card on hover. */
.crm-lead-card::before {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: 16px;
    background: radial-gradient(135% 150% at 0% 50%, rgba(46,139,77,.06), transparent 45%);
    opacity: 0;
    transition: opacity .32s var(--ease-out);
    pointer-events: none;
}
.crm-lead-card.crm-due {
    border-color: rgba(183,121,31,.28);
    background: linear-gradient(180deg, #fffdf8, #fffaef);
}
.crm-lead-card.crm-active {
    border-color: rgba(46,139,77,.45);
    background: linear-gradient(180deg, #ffffff, var(--green-bg));
    box-shadow:
      0 1px 2px rgba(15,42,51,.05),
      0 12px 26px -14px rgba(46,139,77,.45),
      inset 0 1px 0 rgba(255,255,255,.8);
}
.crm-lead-body {
    display: grid;
    grid-template-columns: minmax(0, 2.3fr) minmax(0, 1.7fr) minmax(0, 1.7fr);
    gap: 16px;
    align-items: center;
    flex: 1;
    min-width: 0;
}
.crm-lead-chev {
    flex: none;
    width: 30px;
    height: 30px;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 17px;
    font-weight: 700;
    line-height: 1;
    color: rgba(15,42,51,.34);
    background: rgba(15,42,51,.045);
    border: 1px solid transparent;
    transition: color .22s var(--ease-out), background .22s var(--ease-out),
                transform .22s var(--ease-out), border-color .22s var(--ease-out);
}
.crm-lead-co-wrap { display: flex; align-items: center; gap: 13px; min-width: 0; width: 100%; }
.crm-mono {
    flex: none;
    width: 46px; height: 46px; border-radius: 14px;
    display: inline-flex; align-items: center; justify-content: center;
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 15px; font-weight: 800; letter-spacing: .01em;
    color: var(--ink);
    background: linear-gradient(150deg, rgba(15,42,51,.10), rgba(15,42,51,.03));
    border: 1px solid rgba(15,42,51,.10);
    box-shadow: inset 0 1px 0 rgba(255,255,255,.85), 0 4px 10px -5px rgba(15,42,51,.28);
    transition: transform .26s var(--ease-out), box-shadow .26s var(--ease-out);
}
.crm-mono.new       { color: #1d6b39; background: linear-gradient(150deg, rgba(46,139,77,.20), rgba(46,139,77,.06));  border-color: rgba(46,139,77,.26); }
.crm-mono.contacted { color: #1D4ED8; background: linear-gradient(150deg, rgba(59,130,246,.18), rgba(59,130,246,.05)); border-color: rgba(59,130,246,.26); }
.crm-mono.qualified { color: #7E22CE; background: linear-gradient(150deg, rgba(168,85,247,.18), rgba(168,85,247,.05)); border-color: rgba(168,85,247,.28); }
.crm-mono.meeting   { color: #1E40AF; background: linear-gradient(150deg, rgba(59,130,246,.18), rgba(59,130,246,.05)); border-color: rgba(59,130,246,.28); }
.crm-mono.proposal  { color: #8a5a14; background: linear-gradient(150deg, rgba(183,121,31,.20), rgba(183,121,31,.06)); border-color: rgba(183,121,31,.30); }
.crm-mono.nurture   { color: var(--ink-mute); }
.crm-mono.won       { color: #166534; background: linear-gradient(150deg, rgba(46,139,77,.26), rgba(46,139,77,.08));  border-color: rgba(46,139,77,.30); }
.crm-mono.lost      { color: #A93D3D; background: linear-gradient(150deg, rgba(169,61,61,.18), rgba(169,61,61,.05));  border-color: rgba(169,61,61,.26); }
/* Each column stacks a primary line over a muted secondary line. */
.crm-lead-co-text,
.crm-lead-name-wrap,
.crm-lead-status-wrap { display: flex; flex-direction: column; justify-content: center; gap: 3px; min-width: 0; }
.crm-lead-co {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 15px;
    font-weight: 800;
    color: var(--ink);
    line-height: 1.2;
    letter-spacing: -.01em;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 100%;
}
.crm-lead-name {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 13.5px;
    font-weight: 700;
    color: var(--ink-soft);
    line-height: 1.2;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 100%;
}
.crm-lead-sub {
    font-size: 11.5px;
    font-weight: 600;
    color: var(--ink-mute);
    line-height: 1.25;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 100%;
}
.crm-lead-status {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: nowrap;
    min-width: 0;
}
.crm-lead-status .crm-pill {
    flex-shrink: 0;
    white-space: nowrap;
    display: inline-flex;
    align-items: center;
}
.crm-lead-status .crm-pill::before {
    content: '';
    width: 5px; height: 5px;
    border-radius: 50%;
    background: currentColor;
    margin-right: 5px;
    opacity: .85;
}
.crm-lead-meta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10.5px;
    font-weight: 600;
    color: var(--ink-mute);
    letter-spacing: .02em;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 100%;
}

.crm-pill {
    display: inline-block; padding: 4px 9px; border-radius: 999px;
    font-size: 10px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase;
    background: rgba(15,42,51,.06); color: var(--ink-soft);
}
.crm-pill.new { background: rgba(46,139,77,.12); color: var(--green); }
.crm-pill.contacted { background: rgba(59,130,246,.12); color: #1D4ED8; }
.crm-pill.qualified { background: rgba(168,85,247,.12); color: #7E22CE; }
.crm-pill.meeting { background: rgba(59,130,246,.12); color: #1E40AF; }
.crm-pill.proposal { background: rgba(183,121,31,.12); color: var(--amber); }
.crm-pill.nurture { background: rgba(15,42,51,.06); color: var(--ink-mute); }
.crm-pill.meeting { background: rgba(59,130,246,.12); color: #1E40AF; }
.crm-pill.won { background: rgba(46,139,77,.18); color: #166534; }
.crm-pill.lost { background: rgba(169,61,61,.12); color: var(--red); }
.crm-pill.due { background: rgba(183,121,31,.12); color: var(--amber); }
.crm-pill.open { background: rgba(59,130,246,.10); color: #1D4ED8; }
.crm-stage-snap {
    margin: 10px 0 2px;
}
.crm-snapshot-card {
    background:
      linear-gradient(135deg, rgba(255,255,255,.86), rgba(255,255,255,.58)),
      radial-gradient(95% 130% at 100% 0%, rgba(46,139,77,.11), transparent 50%);
    border: 1px solid var(--line-soft);
    border-radius: var(--rl);
    padding: 16px;
    box-shadow: 0 14px 34px rgba(15,42,51,.06);
}
.crm-snapshot-top {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 14px;
    margin-bottom: 14px;
    flex-wrap: wrap;
}
.crm-snapshot-title {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 18px;
    font-weight: 850;
    color: var(--ink);
    line-height: 1.1;
}
.crm-snapshot-sub {
    color: var(--ink-mute);
    font-size: 12.5px;
    margin-top: 4px;
}
.crm-snapshot-totals {
    display: grid;
    grid-template-columns: repeat(4, minmax(72px, 1fr));
    gap: 8px;
    min-width: min(100%, 360px);
}
.crm-snapshot-total {
    background: rgba(255,255,255,.66);
    border: 1px solid var(--line-soft);
    border-radius: var(--rs);
    padding: 9px 10px;
}
.crm-snapshot-total .n {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 18px;
    font-weight: 850;
    color: var(--ink);
    line-height: 1;
}
.crm-snapshot-total .l {
    color: var(--ink-mute);
    font-family: 'JetBrains Mono', monospace;
    font-size: 8px;
    font-weight: 700;
    letter-spacing: .12em;
    margin-top: 5px;
    text-transform: uppercase;
}
.crm-stage-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(108px, 1fr));
    gap: 8px;
}
.crm-stage {
    background: rgba(255,255,255,.66);
    border: 1px solid var(--line-soft);
    border-radius: var(--r);
    padding: 10px 11px;
    min-height: 78px;
    position: relative;
    overflow: hidden;
    box-shadow: inset 3px 0 0 rgba(15,42,51,.12);
}
.crm-stage.open { box-shadow: inset 3px 0 0 var(--green); }
.crm-stage.close { box-shadow: inset 3px 0 0 var(--ink-mute); }
.crm-stage.win { box-shadow: inset 3px 0 0 var(--green-br); }
.crm-stage.loss { box-shadow: inset 3px 0 0 var(--red); }
.crm-stage-top {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
    margin-bottom: 6px;
}
.crm-stage-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    font-weight: 800;
    letter-spacing: .08em;
    text-transform: uppercase;
    color: var(--ink-mute);
    white-space: normal;
}
.crm-stage .n {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 26px;
    font-weight: 850;
    color: var(--ink);
    line-height: .95;
}
.crm-stage .pct {
    color: var(--ink-mute);
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    font-weight: 700;
    margin-top: 3px;
}
.crm-stage-bar {
    height: 5px;
    border-radius: 999px;
    background: rgba(15,42,51,.07);
    overflow: hidden;
}
.crm-stage-fill {
    display: block;
    height: 100%;
    border-radius: inherit;
    background: linear-gradient(90deg, var(--green), #9BCF9E);
}
.crm-stage.close .crm-stage-fill { background: linear-gradient(90deg, var(--ink-mute), rgba(107,127,133,.38)); }
.crm-stage.win .crm-stage-fill { background: linear-gradient(90deg, var(--green-br), #9BCF9E); }
.crm-stage.loss .crm-stage-fill { background: linear-gradient(90deg, var(--red), rgba(169,61,61,.38)); }
.crm-stage-empty .crm-stage-fill { width: 0 !important; }
.crm-stage-empty .n { color: var(--ink-soft); }
.crm-stage-empty { opacity: .72; }
.crm-stage-note {
    margin-top: 10px;
    color: var(--ink-mute);
    font-size: 12px;
    line-height: 1.45;
}
.crm-stage-tools {
    background: rgba(255,255,255,.62);
    border: 1px solid var(--line-soft);
    border-radius: var(--r);
    padding: 14px 16px;
    margin: 12px 0 0;
}
.crm-stage-tools-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 10px;
    flex-wrap: wrap;
}
.crm-stage-tools-title {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 16px;
    font-weight: 850;
    color: var(--ink);
}
.crm-stage-tools-hint {
    color: var(--ink-mute);
    font-size: 12.5px;
}
.crm-setup-card {
    background: rgba(183,121,31,.08);
    border: 1px solid rgba(183,121,31,.20);
    border-radius: var(--r);
    padding: 13px 15px;
    margin: 0 0 2px;
    color: var(--ink-soft);
    font-size: 13px;
    line-height: 1.5;
}
.crm-setup-card strong { color: var(--ink); }
.crm-setup-card code {
    background: rgba(255,255,255,.65);
    border: 1px solid var(--line-soft);
    border-radius: 5px;
    padding: 1px 5px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
}
.crm-email-insights {
    background: linear-gradient(135deg, rgba(46,139,77,.08), rgba(255,255,255,.72));
    border: 1px solid rgba(46,139,77,.16);
    border-radius: var(--r);
    padding: 14px 16px;
    margin: 12px 0;
}
.crm-email-insights .title {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 16px;
    font-weight: 850;
    color: var(--ink);
}
.crm-email-insights .hint {
    color: var(--ink-mute);
    font-size: 12.5px;
    line-height: 1.5;
    margin-top: 4px;
}
.crm-email-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin: 10px 0;
}
.crm-email-item {
    background: rgba(255,255,255,.70);
    border: 1px solid var(--line-soft);
    border-radius: var(--rs);
    padding: 10px 12px;
}
.crm-email-item .meta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    letter-spacing: .08em;
    text-transform: uppercase;
    color: var(--ink-mute);
    margin-bottom: 4px;
}
.crm-email-item .subject {
    color: var(--ink);
    font-size: 13px;
    font-weight: 800;
}
.crm-email-item .summary {
    color: var(--ink-soft);
    font-size: 12.5px;
    line-height: 1.45;
    margin-top: 4px;
}
.crm-client-thread {
    background: rgba(255,255,255,.66);
    border: 1px solid var(--line-soft);
    border-radius: var(--r);
    padding: 14px 16px;
    margin: 12px 0;
}
.crm-client-thread .title {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 16px;
    font-weight: 850;
    color: var(--ink);
}
.crm-client-thread .hint {
    color: var(--ink-mute);
    font-size: 12.5px;
    line-height: 1.5;
    margin: 4px 0 10px;
}
.crm-contact-person {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    align-items: flex-start;
    background: rgba(255,255,255,.70);
    border: 1px solid var(--line-soft);
    border-radius: var(--rs);
    padding: 10px 12px;
    margin-bottom: 8px;
}
.crm-contact-person .name {
    color: var(--ink);
    font-weight: 850;
}
.crm-contact-person .meta {
    color: var(--ink-mute);
    font-size: 12px;
    line-height: 1.45;
    margin-top: 0;
}
.crm-thread {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin: 2px 0 16px;
}
.crm-thread-item {
    background: rgba(255,255,255,.68);
    border: 1px solid var(--line-soft);
    border-left: 3px solid rgba(15,42,51,.18);
    border-radius: var(--rs);
    padding: 11px 13px;
}
.crm-thread-item.email { border-left-color: rgba(59,130,246,.48); }
.crm-thread-item.comment { border-left-color: rgba(46,139,77,.48); }
.crm-thread-item.meeting { border-left-color: rgba(46,139,77,.55); background: rgba(46,139,77,.04); }
.crm-thread-meta {
    color: var(--ink-mute);
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    font-weight: 750;
    letter-spacing: .08em;
    text-transform: uppercase;
}
.crm-thread-title {
    color: var(--ink);
    font-size: 13.5px;
    font-weight: 800;
    margin-top: 5px;
}
.crm-thread-body {
    color: var(--ink-soft);
    font-size: 12.5px;
    line-height: 1.5;
    margin-top: 4px;
    white-space: pre-wrap;
}
.crm-filter-summary {
    color: var(--ink-mute);
    font-size: 12px;
    margin: 4px 0 10px;
}
.crm-src {
    font-size: 10px; color: var(--ink-mute); letter-spacing: .04em;
    text-transform: uppercase; font-weight: 600;
}
.crm-actions {
    display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; margin-top: 8px;
}
.crm-actions a {
    display: inline-flex; align-items: center; justify-content: center;
    min-height: 28px; padding: 5px 10px; border-radius: 999px;
    border: 1px solid var(--line-soft); background: rgba(255,255,255,.55);
    color: var(--ink-soft); text-decoration: none; font-size: 11.5px; font-weight: 750;
    transition: transform .15s ease, border-color .15s ease, background .15s ease;
}
.crm-actions a:hover { border-color: rgba(46,139,77,.35); color: var(--green); background: var(--green-bg); }
.crm-edit-wrap {
    margin: -2px 0 14px;
}
.crm-empty {
    text-align: center; padding: 40px 20px;
    border: 1px dashed var(--line-mid); border-radius: var(--rl);
    color: var(--ink-mute); font-size: 14px;
}

/* CRM overrides for global Lead Agent composer styles. */
[data-testid="stForm"] {
    background: var(--cream-3) !important;
    border: 1px solid var(--line-soft) !important;
    border-radius: var(--r) !important;
    overflow: visible !important;
    padding: 16px !important;
    box-shadow: none !important;
}
[data-testid="stForm"]::before,
[data-testid="stForm"] [data-testid="stFormSubmitButton"] button::after {
    display: none !important;
}
[data-testid="stForm"] > div > [data-testid="stVerticalBlock"] {
    gap: 12px !important;
}
[data-testid="stForm"] [data-testid="stHorizontalBlock"] {
    border-top: 0 !important;
    padding: 0 !important;
    margin: 0 !important;
    gap: 12px !important;
    align-items: stretch !important;
    min-height: auto !important;
}
[data-testid="stForm"] [data-testid="stHorizontalBlock"] > [data-testid="column"] {
    padding: 0 !important;
}
[data-testid="stForm"] .stTextInput input,
[data-testid="stForm"] .stTextArea textarea,
[data-testid="stForm"] [data-baseweb="select"] {
    background: #fff !important;
}
[data-testid="stForm"] .stTextArea textarea {
    border: 1px solid var(--line-soft) !important;
    border-radius: var(--rs) !important;
    padding: 11px 12px !important;
    min-height: 86px !important;
    font-size: 14px !important;
    line-height: 1.5 !important;
    resize: vertical !important;
}
[data-testid="stForm"] [data-testid="stFormSubmitButton"] {
    width: 100% !important;
    justify-content: stretch !important;
}
[data-testid="stForm"] [data-testid="stFormSubmitButton"] button {
    width: 100% !important;
    height: auto !important;
    min-width: 0 !important;
    min-height: 42px !important;
    border-radius: var(--rs) !important;
    padding: 11px 18px !important;
    font-size: 14px !important;
    line-height: 1.2 !important;
    display: inline-flex !important;
    transition: transform .15s ease, box-shadow .15s ease, background .15s ease !important;
    transform: none !important;
}
.crm-shell [data-testid="stForm"] [data-testid="stFormSubmitButton"] button { transform: none !important; }
[data-testid="stForm"] [data-testid="stFormSubmitButton"] button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 8px 22px rgba(46,139,77,.18) !important;
}
[data-testid="stForm"] [data-testid="stFormSubmitButton"] button:active {
    transform: translateY(0) scale(.985) !important;
}
.stTextInput input,
.stTextArea textarea {
    font-size: 14px !important;
}

@media (max-width: 720px) {
    .crm-head h2 { font-size: 26px; }
    .crm-sync { width: 100%; justify-content: center; white-space: normal; text-align: center; }
    .crm-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .crm-stage-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .crm-snapshot-totals { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .crm-stat { padding: 13px 12px; }
    .crm-ledger-head { display: none; }
    .crm-lead-card { gap: 11px; padding: 0 14px 0 20px; }
    .crm-mono { width: 38px; height: 38px; border-radius: 12px; font-size: 13px; }
    .crm-rail { height: 32px; }
    .crm-lead-body { grid-template-columns: 1fr; gap: 5px; }
    .crm-lead-co, .crm-lead-name { white-space: normal; }
    .crm-lead-sub, .crm-lead-meta { display: none; }
    .crm-lead-status { flex-wrap: wrap; }
    div[class*="st-key-crm_row_"] [data-testid="stElementContainer"]:has(.crm-lead-hit) + [data-testid="stElementContainer"] button {
        min-height: 92px !important;
        height: 92px !important;
    }
    [data-testid="stForm"] [data-testid="stHorizontalBlock"] {
        display: flex !important;
        flex-direction: column !important;
        gap: 10px !important;
    }
    [data-testid="stForm"] [data-testid="stHorizontalBlock"] > [data-testid="column"] {
        width: 100% !important;
        flex: 1 1 auto !important;
    }
    .stTextArea label, .stTextInput label, .stSelectbox label {
        letter-spacing: .16em !important;
    }
    .crm-toolbar [data-testid="stHorizontalBlock"] {
        flex-direction: column !important;
        gap: 8px !important;
    }
    .crm-toolbar [data-testid="stHorizontalBlock"] > [data-testid="column"] {
        width: 100% !important;
        flex: 1 1 auto !important;
    }
    .crm-filter-summary { font-size: 12px; line-height: 1.5; }
    [data-testid="stDialog"] [data-testid="stModal"] > div:first-child {
        max-width: calc(100vw - 24px) !important;
        margin: 12px !important;
        padding: 16px !important;
        border-radius: 20px !important;
    }
}

/* ═══════════════════════════════════════════════════════════════════════════
   AI INTAKE DIALOG — Premium composer layout
   ═══════════════════════════════════════════════════════════════════════════ */

[data-testid="stDialog"] {
    background: rgba(15, 42, 51, 0.58) !important;
    backdrop-filter: blur(12px) saturate(120%);
    animation: aiBackdropIn .28s ease both;
}
@keyframes aiBackdropIn {
    from { opacity: 0; }
    to   { opacity: 1; }
}

[data-testid="stDialog"] [data-testid="stModal"] > div:first-child {
    background: linear-gradient(180deg, #FDFCF9 0%, #F5F1E8 100%) !important;
    border: 1px solid rgba(15, 42, 51, 0.07) !important;
    border-radius: 28px !important;
    box-shadow:
        0 48px 140px rgba(15, 42, 51, 0.30),
        0 0 0 1px rgba(255,255,255,.60) inset !important;
    padding: 18px 20px 20px !important;
    max-width: 580px !important;
    animation: aiModalIn .38s cubic-bezier(.22,1,.36,1) both;
    position: relative;
    overflow: hidden;
}
[data-testid="stDialog"] [data-testid="stModal"] > div:first-child::before {
    content: "";
    position: absolute; top: 0; left: 0; right: 0; height: 3px;
    background: linear-gradient(90deg, transparent, var(--green), #7DD99A, var(--green), transparent);
    opacity: .85;
}
@keyframes aiModalIn {
    from { opacity: 0; transform: translateY(16px) scale(.97); }
    to   { opacity: 1; transform: translateY(0) scale(1); }
}

[data-testid="stDialog"] h2 {
    font-size: 0 !important;
    height: 0 !important;
    overflow: hidden !important;
    padding: 0 !important;
    margin: 0 !important;
    border: none !important;
}

[data-testid="stDialog"] [data-testid="stVerticalBlock"] {
    gap: 0.55rem !important;
}

.ai-dialog-wrap {
    padding: 6px 4px 4px;
    animation: aiFadeUp .35s ease both;
}
.ai-dialog-wrap.ai-review-reveal { animation: aiFadeUp .45s ease both; }

.ai-dialog-head { margin: 0 0 10px; animation: aiFadeUp .4s ease both; }
.ai-dialog-kicker {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px; letter-spacing: .18em; text-transform: uppercase;
    color: var(--green); font-weight: 700; margin: 0 0 6px;
}
.ai-dialog-title {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 26px; font-weight: 800; color: var(--ink);
    letter-spacing: -0.03em; margin: 0 0 5px; line-height: 1.12;
}
.ai-dialog-sub {
    font-size: 13.5px; color: var(--ink-mute); margin: 0; line-height: 1.5;
}
.ai-step-badge { display: none !important; }

/* Progress track */
.ai-progress-wrap { margin: 0 0 16px; }
.ai-progress-meta {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 7px;
}
.ai-progress-step {
    font-size: 10px; font-weight: 700; letter-spacing: .06em;
    text-transform: uppercase; color: var(--ink-mute);
    transition: color .3s ease;
}
.ai-progress-step.on { color: var(--green); }
.ai-progress-step.done { color: var(--green); opacity: .75; }
.ai-progress-track {
    height: 4px; border-radius: 999px;
    background: rgba(15,42,51,.08); overflow: hidden;
}
.ai-progress-fill {
    height: 100%; border-radius: inherit;
    background: linear-gradient(90deg, var(--green), #5BCF82);
    transition: width .55s cubic-bezier(.22,1,.36,1);
    box-shadow: 0 0 12px rgba(46,139,77,.35);
}

/* Composer — native Streamlit bordered container */
[data-testid="stDialog"] [data-testid="stVerticalBlockBorderWrapper"] {
    background: rgba(255,255,255,.98) !important;
    border: 1px solid rgba(15,42,51,.08) !important;
    border-radius: 20px !important;
    padding: 16px 18px 14px !important;
    box-shadow: 0 14px 40px rgba(15,42,51,.07) !important;
    animation: aiFadeUp .4s ease both;
}
[data-testid="stDialog"] .ai-field-label {
    display: block;
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px; letter-spacing: .16em; text-transform: uppercase;
    color: var(--ink-mute); font-weight: 700;
    margin: 0 0 10px;
}
[data-testid="stDialog"] .ai-field-label--spaced { margin-top: 16px; }
[data-testid="stDialog"] [data-testid="stCaptionContainer"] {
    display: none !important;
}

/* Template cards */
.ai-template-row [data-testid="stHorizontalBlock"] { gap: 8px !important; align-items: stretch !important; }
.ai-tmpl-slot { margin-bottom: 2px; }
.ai-tmpl-slot [data-testid="stButton"] { width: 100% !important; }
.ai-tmpl-slot button {
    width: 100% !important;
    min-height: 46px !important;
    border-radius: 14px !important;
    font-family: 'Bricolage Grotesque', sans-serif !important;
    font-size: 13px !important;
    font-weight: 800 !important;
    letter-spacing: .01em !important;
    transition: all .22s cubic-bezier(.22,1,.36,1) !important;
}
.ai-tmpl-slot button[kind="secondary"] {
    background: #fff !important;
    border: 1.5px solid rgba(15,42,51,.09) !important;
    color: var(--ink) !important;
    box-shadow: 0 2px 8px rgba(15,42,51,.04) !important;
}
.ai-tmpl-slot button[kind="secondary"]:hover {
    border-color: rgba(46,139,77,.28) !important;
    color: var(--green) !important;
    transform: translateY(-1px) !important;
}
.ai-tmpl-slot.is-active button[kind="primary"] {
    background: linear-gradient(135deg, var(--ink), #1a4450) !important;
    border: none !important;
    color: #fff !important;
    box-shadow: 0 8px 24px rgba(15,42,51,.22) !important;
}
.tmpl-desc-below {
    display: block; text-align: center;
    font-size: 10px; color: var(--ink-mute);
    margin-top: 5px; line-height: 1.3;
}
.ai-tmpl-slot.is-active .tmpl-desc-below { color: var(--green); font-weight: 600; }

/* Example ghost — separate from input, not placeholder clutter */
.ai-example-ghost {
    margin: 0 0 10px;
    padding: 10px 12px;
    border-radius: 14px;
    border: 1px dashed rgba(46,139,77,.22);
    background: linear-gradient(135deg, rgba(46,139,77,.04), rgba(255,255,255,.8));
    animation: aiFadeUp .3s ease both;
}
.ai-example-ghost .eg-tag {
    display: inline-block;
    font-family: 'JetBrains Mono', monospace;
    font-size: 8px; letter-spacing: .14em; text-transform: uppercase;
    font-weight: 700; color: var(--green);
    background: rgba(46,139,77,.12);
    padding: 2px 7px; border-radius: 999px; margin-bottom: 6px;
}
.ai-example-ghost p {
    margin: 0; font-size: 13px; line-height: 1.55;
    color: var(--ink-mute); font-style: italic;
}

/* Textarea + buttons inside bordered container */
[data-testid="stDialog"] [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stForm"] {
    border: none !important; padding: 0 !important;
    box-shadow: none !important; background: transparent !important;
}
[data-testid="stDialog"] [data-testid="stForm"] {
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    box-shadow: none !important;
}
[data-testid="stDialog"] [data-testid="stVerticalBlockBorderWrapper"] .stTextArea textarea {
    border-radius: 14px !important;
    border: 1.5px solid rgba(15,42,51,.08) !important;
    background: var(--cream-3) !important;
    padding: 12px 14px !important;
    min-height: 96px !important;
    font-size: 15px !important;
    line-height: 1.6 !important;
}
[data-testid="stDialog"] [data-testid="stVerticalBlockBorderWrapper"] .stTextArea textarea:focus {
    border-color: rgba(46,139,77,.45) !important;
    background: #fff !important;
    box-shadow: 0 0 0 4px rgba(46,139,77,.10) !important;
}
[data-testid="stDialog"] [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stForm"] [data-testid="stHorizontalBlock"] {
    gap: 10px !important; margin-top: 14px !important;
}
[data-testid="stDialog"] [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stForm"] [data-testid="column"]:first-child button {
    background: #fff !important;
    border: 1.5px solid rgba(15,42,51,.12) !important;
    color: var(--ink-soft) !important;
    font-weight: 600 !important;
    border-radius: 12px !important;
    min-height: 44px !important;
    animation: none !important;
}
[data-testid="stDialog"] [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stForm"] [data-testid="column"]:last-child button {
    background: linear-gradient(135deg, var(--green), #3DB86A) !important;
    border: none !important;
    color: #fff !important;
    font-weight: 700 !important;
    border-radius: 12px !important;
    min-height: 44px !important;
    box-shadow: 0 10px 28px rgba(46,139,77,.30) !important;
    animation: none !important;
}

/* Dialog footer */
.ai-dialog-footer {
    margin-top: 14px; padding-top: 12px;
    border-top: 1px solid rgba(15,42,51,.06);
    animation: aiFadeUp .45s ease .1s both;
}
.ai-dialog-footer [data-testid="column"]:first-child [data-testid="stButton"] {
    width: auto !important;
}
.ai-dialog-footer [data-testid="column"]:first-child button {
    width: auto !important; min-width: 0 !important;
    background: transparent !important; border: none !important;
    color: var(--ink-mute) !important; font-size: 13px !important;
    font-weight: 600 !important; padding: 6px 0 !important;
    box-shadow: none !important; animation: none !important;
}
.ai-dialog-footer [data-testid="column"]:first-child button:hover { color: var(--ink) !important; }
.ai-footer-note {
    display: block; text-align: right;
    font-size: 10px; color: var(--ink-mute); letter-spacing: .04em;
    padding-top: 8px;
}

[data-testid="stDialog"] [data-testid="stCaptionContainer"] { display: none !important; }

/* Legacy hero — hidden in new layout */
.ai-hero { display: none; }

/* ── Step rail (legacy) ── */
/* ── Google Meet panel ── */
.crm-meet-shell {
    padding: 14px 16px;
    border-radius: 18px;
    border: 1.5px solid var(--line-soft);
    background: linear-gradient(165deg, rgba(255,255,255,.95), rgba(244,240,231,.55));
    box-shadow: 0 8px 28px rgba(15,42,51,.05);
    animation: aiFadeUp .35s ease both;
}
.crm-meet-shell .meet-head {
    display: flex; align-items: center; gap: 10px; margin-bottom: 12px;
}
.crm-meet-shell .meet-icon {
    width: 36px; height: 36px; border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    background: linear-gradient(135deg, #1a73e8, #4285f4);
    color: #fff; font-size: 16px; font-weight: 800;
    box-shadow: 0 6px 18px rgba(26,115,232,.25);
}
.crm-meet-shell .meet-title {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 15px; font-weight: 800; color: var(--ink); margin: 0;
}
.crm-meet-shell .meet-sub {
    font-size: 12px; color: var(--ink-mute); margin: 2px 0 0;
}
.crm-meet-chat {
    margin-top: 12px; padding: 12px 14px;
    border-radius: 14px;
    border: 1px solid rgba(46,139,77,.16);
    background: rgba(46,139,77,.05);
    font-size: 13px; line-height: 1.55; color: var(--ink-soft);
    white-space: pre-wrap;
}
.crm-meet-actions {
    display: flex; flex-wrap: wrap; gap: 10px;
    margin: 0; padding: 14px 0 18px;
    border-top: 1px solid var(--line-soft);
    border-bottom: 1px solid var(--line-soft);
}
.crm-meet-schedule-spacer { height: 18px; }
.crm-meet-schedule-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px; font-weight: 700; letter-spacing: .14em;
    text-transform: uppercase; color: var(--ink-mute);
    margin: 4px 0 10px;
}
.crm-meet-actions a, .crm-meet-actions span.pill {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 7px 14px; border-radius: 999px;
    font-size: 12px; font-weight: 700; text-decoration: none;
    transition: transform .15s ease, box-shadow .15s ease;
}
.crm-meet-actions a:hover { transform: translateY(-1px); }
.crm-meet-actions a.cal {
    border: 1px solid rgba(26,115,232,.22);
    background: rgba(26,115,232,.08); color: #1a73e8;
}
.crm-meet-actions a.meet {
    border: 1px solid rgba(46,139,77,.25);
    background: rgba(46,139,77,.10); color: var(--green);
}

/* ── Step rail ── */
.ai-step-rail {
    display: flex; align-items: center; gap: 0;
    margin: 0 0 10px; padding: 0 2px;
}
.ai-step-node {
    display: flex; align-items: center; gap: 8px;
    flex: 1; min-width: 0;
}
.ai-step-dot {
    width: 26px; height: 26px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px; font-weight: 700;
    border: 2px solid var(--line-soft);
    background: #fff; color: var(--ink-mute);
    flex-shrink: 0;
    transition: all .35s var(--ease-spring);
}
.ai-step-label {
    font-size: 11px; font-weight: 600; color: var(--ink-mute);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    transition: color .3s ease;
}
.ai-step-node.active .ai-step-dot {
    background: var(--green); border-color: var(--green); color: #fff;
    box-shadow: 0 0 0 5px rgba(46, 139, 77, 0.14);
    transform: scale(1.08);
}
.ai-step-node.active .ai-step-label { color: var(--ink); font-weight: 700; }
.ai-step-node.done .ai-step-dot {
    background: var(--green); border-color: var(--green); color: #fff;
}
.ai-step-node.done .ai-step-label { color: var(--green); }
.ai-step-line {
    flex: 1; height: 2px; background: var(--line-soft); margin: 0 10px;
    border-radius: 2px;
    transition: background .4s ease;
}
.ai-step-line.done { background: rgba(46, 139, 77, 0.35); }

/* ── Hero ── */
.ai-hero {
    display: flex; align-items: center; gap: 14px;
    padding: 14px 18px; margin-bottom: 10px;
    border-radius: 16px;
    background: linear-gradient(135deg, rgba(46,139,77,.06), rgba(255,255,255,.40));
    border: 1px solid rgba(46, 139, 77, 0.12);
}
.ai-hero-icon {
    width: 40px; height: 40px; border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    background: var(--green); color: #fff;
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 20px; font-weight: 800; flex-shrink: 0;
    box-shadow: 0 4px 16px rgba(46, 139, 77, 0.18);
}
.ai-hero-title {
    font-size: 17px; font-weight: 800; color: var(--ink);
    margin: 0 0 1px 0; letter-spacing: -0.01em;
}
.ai-hero-sub {
    font-size: 12.5px; color: var(--ink-mute); line-height: 1.4; margin: 0;
}

/* ── Dialogs captions — use ai-field-label instead ── */
[data-testid="stDialog"] [data-testid="stCaptionContainer"] {
    display: none !important;
}

/* ── Input card ── */
.ai-input-card {
    background: #fff;
    border: 1.5px solid var(--line-soft);
    border-radius: 16px;
    padding: 10px 14px 6px;
    margin-bottom: 8px;
    transition: all .25s ease;
    box-shadow: 0 1px 4px rgba(15,42,51,.02);
}
.ai-input-card:focus-within {
    border-color: rgba(46,139,77,.35);
    box-shadow: 0 0 0 4px rgba(46,139,77,.06);
}
.ai-input-card .hint {
    font-size: 9px; letter-spacing: .14em; text-transform: uppercase;
    color: var(--ink-mute); font-weight: 700; margin-bottom: 2px;
}
.ai-input-card textarea {
    border: none !important; box-shadow: none !important;
    padding: 2px 2px !important; min-height: 64px !important;
    font-size: 15px !important; line-height: 1.6 !important;
    caret-color: var(--green) !important; background: transparent !important;
}

/* ── Form controls inside dialog ── */
[data-testid="stDialog"] [data-testid="stForm"] {
    border: none !important; padding: 0 !important;
    box-shadow: none !important; background: transparent !important;
}
[data-testid="stDialog"] .stTextArea textarea {
    border-radius: 10px !important;
    border-color: rgba(46, 139, 77, 0.18) !important;
    background: transparent !important;
    font-size: 15px !important; line-height: 1.6 !important;
}
[data-testid="stDialog"] .stTextArea textarea:focus {
    border-color: var(--green) !important;
    box-shadow: 0 0 0 3px rgba(46, 139, 77, 0.08) !important;
}
[data-testid="stDialog"] [data-testid="stFormSubmitButton"] button {
    border-radius: 10px !important; font-weight: 600 !important;
    min-height: 40px !important; font-size: 14px !important;
}
[data-testid="stDialog"] [data-testid="stFormSubmitButton"] button:hover {
    transform: translateY(-1px) !important;
}
[data-testid="stDialog"] [data-testid="stFormSubmitButton"] button:active {
    transform: scale(.98) !important;
}

/* Review-phase primary pulse only — not every dialog button */
.ai-save-bar [data-testid="baseButton-primary"]:not(:disabled) {
    animation: aiSavePulse 2.4s ease-in-out infinite;
}
.ai-save-bar [data-testid="baseButton-primary"]:not(:disabled):hover {
    animation: none;
}
.ai-action-bar [data-testid="baseButton-primary"]:not(:disabled) {
    animation: none !important;
}

/* ── Preview card ── */
.ai-preview-card {
    display: flex; align-items: center; gap: 14px;
    padding: 14px 18px; margin-bottom: 10px;
    border-radius: 16px;
    background: #fff;
    border: 1px solid var(--line-soft);
    box-shadow: 0 4px 16px rgba(15, 42, 51, 0.04);
}
.ai-preview-avatar {
    width: 46px; height: 46px; border-radius: 14px;
    display: flex; align-items: center; justify-content: center;
    background: linear-gradient(135deg, var(--green), var(--green-br));
    color: #fff;
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 18px; font-weight: 800;
    flex-shrink: 0;
    box-shadow: 0 4px 14px rgba(46, 139, 77, 0.18);
}
.ai-preview-name {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 18px; font-weight: 800; color: var(--ink);
    margin: 0 0 2px 0;
}
.ai-preview-meta {
    font-size: 12px; color: var(--ink-mute); margin: 0;
}

/* ── Field sections ── */
.ai-field-section {
    background: #fff;
    border: 1.5px solid var(--line-soft);
    border-radius: 16px;
    padding: 12px 16px 8px;
    margin-bottom: 8px;
    transition: all .2s ease;
    box-shadow: 0 1px 4px rgba(15,42,51,.02);
}
.ai-field-section .sec-label {
    font-size: 9px; letter-spacing: .16em; text-transform: uppercase;
    color: var(--ink-mute); font-weight: 700; margin-bottom: 8px;
    display: flex; align-items: center; gap: 8px;
}
.ai-field-section .sec-label::after {
    content: ""; flex: 1; height: 1px;
    background: linear-gradient(90deg, var(--line-soft), transparent);
}
.ai-field-section:focus-within {
    border-color: rgba(46,139,77,.28);
    box-shadow: 0 0 0 3px rgba(46,139,77,.05);
}

/* ── Note cards ── */
.ai-note {
    display: flex; align-items: flex-start; gap: 10px;
    font-size: 13px; line-height: 1.5; padding: 10px 14px;
    border-radius: 12px; border: 1px solid var(--line-soft);
    background: var(--cream-3); margin-bottom: 8px;
}
.ai-note .tag {
    flex: none; font-family: 'JetBrains Mono', monospace; font-weight: 700;
    font-size: 8.5px; letter-spacing: .14em; text-transform: uppercase;
    padding: 2px 7px; border-radius: 999px; margin-top: 1px;
}
.ai-note.ok { border-color: rgba(46,139,77,.18); background: var(--green-bg); }
.ai-note.ok .tag { color: var(--green); background: rgba(46,139,77,.12); }
.ai-note.warn { border-color: rgba(183,121,31,.18); background: var(--amber-bg); }
.ai-note.warn .tag { color: var(--amber); background: rgba(183,121,31,.14); }

/* ── Save bar ── */
.ai-save-bar {
    display: flex; align-items: center; gap: 8px;
    margin-top: 2px; padding: 10px 0 0;
    border-top: 1px solid var(--line-soft);
}
.ai-save-bar .missing-note {
    font-size: 12px; color: var(--ink-mute); line-height: 1.4;
    padding: 6px 10px; border-radius: 8px;
    background: var(--amber-bg); border: 1px solid rgba(183,121,31,.16);
    flex: 1;
}
.ai-save-bar .missing-note strong { color: var(--amber); }

.ai-preview-card {
    display: flex; align-items: center; gap: 16px;
    padding: 16px 20px; margin-bottom: 14px;
    border-radius: 20px;
    background: linear-gradient(135deg, #fff 0%, rgba(255,255,255,.85) 100%);
    border: 1px solid var(--line-soft);
    box-shadow: 0 10px 34px rgba(15, 42, 51, 0.06);
    position: relative; overflow: hidden;
    transition: all .3s var(--ease-out);
}
.ai-preview-card::before {
    content: "";
    position: absolute; top: 0; left: 0; right: 0; height: 2.5px;
    background: linear-gradient(90deg, transparent, var(--green), rgba(46,139,77,.30), transparent);
    opacity: .7;
}
.ai-preview-avatar {
    width: 52px; height: 52px; border-radius: 16px;
    display: flex; align-items: center; justify-content: center;
    background: linear-gradient(135deg, var(--green), #3DB86A);
    color: #fff;
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 21px; font-weight: 800;
    flex-shrink: 0;
    box-shadow: 0 6px 20px rgba(46, 139, 77, 0.22);
    position: relative;
    overflow: hidden;
    animation: aiAvatarGlow 3s ease-in-out infinite;
}
@keyframes aiAvatarGlow {
    0%, 100% { box-shadow: 0 6px 20px rgba(46, 139, 77, 0.22); }
    50% { box-shadow: 0 6px 28px rgba(46, 139, 77, 0.32), 0 0 0 5px rgba(46,139,77,.08); }
}
.ai-preview-avatar::after {
    content: "";
    position: absolute; top: -30%; left: -30%;
    width: 65%; height: 65%;
    background: radial-gradient(circle, rgba(255,255,255,.18), transparent 70%);
    pointer-events: none;
}
.ai-preview-name {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 20px; font-weight: 800; color: var(--ink);
    margin: 0 0 3px 0;
    letter-spacing: -0.01em;
}
.ai-preview-meta {
    font-size: 12.5px; color: var(--ink-mute); margin: 0;
    line-height: 1.45;
}

/* ── Field sections ── */
.ai-field-section {
    background: #fff;
    border: 1.5px solid var(--line-soft);
    border-radius: 18px;
    padding: 14px 16px 10px;
    margin-bottom: 10px;
    transition: all .25s var(--ease-out);
    box-shadow: 0 2px 8px rgba(15,42,51,.03);
}
.ai-field-section .sec-label {
    font-size: 9px; letter-spacing: .16em; text-transform: uppercase;
    color: var(--ink-mute); font-weight: 700; margin-bottom: 10px;
    display: flex; align-items: center; gap: 8px;
}
.ai-field-section .sec-label::after {
    content: ""; flex: 1; height: 1px;
    background: linear-gradient(90deg, var(--line-soft), transparent);
}
.ai-field-section:focus-within {
    border-color: rgba(46,139,77,.30) !important;
    box-shadow: 0 0 0 4px rgba(46,139,77,.07), 0 4px 16px rgba(15,42,51,.04);
}

[data-testid="stDialog"] .stTextInput input,
[data-testid="stDialog"] .stSelectbox > div > div {
    border-radius: 10px !important;
    padding: 8px 12px !important;
    font-size: 14px !important;
}

/* ── Note cards ── */
.ai-note {
    display: flex; align-items: flex-start; gap: 10px;
    font-size: 13px; line-height: 1.55; padding: 12px 15px;
    border-radius: 14px; border: 1px solid var(--line-soft);
    background: var(--cream-3); margin-bottom: 12px;
    transition: all .25s var(--ease-out);
}
.ai-note:hover { transform: translateY(-1px); box-shadow: 0 4px 14px rgba(15,42,51,.06); }
.ai-note .tag {
    flex: none; font-family: 'JetBrains Mono', monospace; font-weight: 700;
    font-size: 9px; letter-spacing: .14em; text-transform: uppercase;
    padding: 3px 8px; border-radius: 999px; margin-top: 2px;
}
.ai-note.ok { border-color: rgba(46,139,77,.20); background: linear-gradient(135deg, var(--green-bg), rgba(255,255,255,.60)); }
.ai-note.ok .tag { color: var(--green); background: rgba(46,139,77,.14); }
.ai-note.warn { border-color: rgba(183,121,31,.22); background: linear-gradient(135deg, var(--amber-bg), rgba(255,255,255,.60)); }
.ai-note.warn .tag { color: var(--amber); background: rgba(183,121,31,.16); }

.ai-captured {
    font-size: 12px; line-height: 1.55; color: var(--ink-mute);
    padding: 12px 14px; border-radius: 14px;
    background: linear-gradient(135deg, var(--cream-2), rgba(255,255,255,.55));
    border: 1px solid var(--line-soft);
    margin-bottom: 12px;
}
.ai-captured b { color: var(--ink); font-weight: 600; display: block; margin-bottom: 6px; }
.ai-captured .chip {
    display: inline-block; margin: 3px 6px 3px 0; padding: 3px 10px;
    border-radius: 999px; background: #fff; border: 1px solid var(--line-soft);
    font-size: 12px; color: var(--ink);
    transition: transform .15s ease, box-shadow .15s ease;
}
.ai-captured .chip:hover {
    transform: translateY(-1px);
    box-shadow: 0 3px 10px rgba(15,42,51,.06);
    border-color: rgba(46,139,77,.22);
}
.ai-captured .chip b { display: inline; margin-bottom: 0; }

.ai-review-grid label {
    font-size: 11px !important;
    letter-spacing: .06em !important;
    text-transform: uppercase !important;
    color: var(--ink-mute) !important;
    font-weight: 700 !important;
}

/* Expander in dialog */
[data-testid="stDialog"] .streamlit-expanderHeader {
    background: var(--cream-3) !important;
    border: 1.5px dashed var(--line-soft) !important;
    border-radius: 12px !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    color: var(--ink-mute) !important;
    padding: 10px 14px !important;
    transition: all .2s ease !important;
}
[data-testid="stDialog"] .streamlit-expanderHeader:hover {
    border-color: rgba(46,139,77,.25) !important;
    color: var(--green) !important;
    background: rgba(46,139,77,.04) !important;
}
[data-testid="stDialog"] .streamlit-expanderContent {
    background: transparent !important;
    border: none !important;
    padding: 8px 0 0 !important;
}

/* ── Dialog form controls ── */
[data-testid="stDialog"] [data-testid="stForm"] {
    border: none !important;
    padding: 0 !important;
    box-shadow: none !important;
    background: transparent !important;
}
[data-testid="stDialog"] .stTextArea textarea {
    border-radius: 12px !important;
    border-color: rgba(46, 139, 77, 0.20) !important;
    background: transparent !important;
    font-size: 15px !important;
    line-height: 1.65 !important;
}
[data-testid="stDialog"] .stTextArea textarea:focus {
    border-color: var(--green) !important;
    box-shadow: 0 0 0 3px rgba(46, 139, 77, 0.12) !important;
    background: transparent !important;
}
[data-testid="stDialog"] [data-testid="stFormSubmitButton"] button {
    border-radius: 10px !important;
    font-weight: 700 !important;
    min-height: 42px !important;
    font-size: 14px !important;
}
[data-testid="stDialog"] [data-testid="baseButton-secondary"] {
    border-radius: 10px !important;
    min-height: 38px !important;
}
[data-testid="stDialog"] [data-testid="stFormSubmitButton"] button {
    transition: transform .2s var(--ease-spring), box-shadow .2s ease !important;
}
[data-testid="stDialog"] [data-testid="stFormSubmitButton"] button:hover {
    transform: translateY(-1px) !important;
}
[data-testid="stDialog"] [data-testid="stFormSubmitButton"] button:active {
    transform: scale(.97) !important;
}

/* ── Save button pulse when enabled (review only) ── */
.ai-save-bar [data-testid="baseButton-primary"]:not(:disabled) {
    animation: aiSavePulse 2.4s ease-in-out infinite;
}
.ai-save-bar [data-testid="baseButton-primary"]:not(:disabled):hover {
    animation: none;
}
.ai-action-bar [data-testid="baseButton-primary"]:not(:disabled) {
    animation: none !important;
}

/* ── AI dialog motion ── */
@keyframes aiFadeUp {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes aiOrbitSpin { to { transform: rotate(360deg); } }
@keyframes aiOrbitGlow {
    0%, 100% { box-shadow: 0 0 0 8px rgba(46,139,77,.10), 0 0 14px rgba(46,139,77,.12); }
    50%       { box-shadow: 0 0 0 16px rgba(46,139,77,.04), 0 0 32px rgba(46,139,77,.28); }
}
@keyframes aiScanline { from { background-position: 0% 50%; } to { background-position: 220% 50%; } }
@keyframes aiScanCell {
    0%, 35% { transform: translateX(-100%); opacity: 0; }
    50%     { opacity: 1; }
    100%    { transform: translateX(100%); opacity: 0; }
}
@keyframes aiShimmerSweep {
    0%   { left: -80%; }
    100% { left: 160%; }
}
@keyframes aiChipPulse {
    0%, 100% { opacity: .55; transform: translateY(0); }
    50%      { opacity: 1; transform: translateY(-1px); }
}
@keyframes aiSavePulse {
    0%, 100% { box-shadow: 0 4px 16px rgba(46,139,77,.22); }
    50%      { box-shadow: 0 4px 26px rgba(46,139,77,.34), 0 0 0 5px rgba(46,139,77,.08); }
}

[data-testid="stDialog"] [data-testid="stSpinner"] { display: none !important; }

.ai-thinking-panel {
    position: relative;
    background: linear-gradient(165deg, #0F2A33 0%, #153942 100%);
    border-radius: 20px;
    padding: 24px 22px 20px;
    margin: 8px 0 10px;
    border: 1px solid rgba(155,207,158,.18);
    box-shadow: 0 20px 50px rgba(15,42,51,.18);
    overflow: hidden;
    animation: aiFadeUp .4s ease both;
}
.ai-thinking-panel::before {
    content: "";
    position: absolute; top: 0; left: -80%; width: 50%; height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,.03), transparent);
    animation: aiShimmerSweep 4s ease-in-out infinite;
    pointer-events: none; z-index: 0;
}
.ai-thinking-panel::after {
    content: "";
    position: absolute; left: 0; right: 0; bottom: 0; height: 3px;
    background: linear-gradient(90deg, transparent, var(--green), #9BCF9E, var(--green), transparent);
    background-size: 300% 100%;
    animation: aiScanline 2.8s linear infinite;
}
.ai-thinking-top {
    display: flex; align-items: center; gap: 16px;
    margin-bottom: 16px; position: relative; z-index: 1;
}
.ai-orbit {
    width: 44px; height: 44px; border-radius: 50%;
    border: 1.5px solid rgba(155,207,158,.65);
    display: flex; align-items: center; justify-content: center;
    color: #DFF0D8; font-family: 'JetBrains Mono', monospace;
    font-size: 11px; font-weight: 700; letter-spacing: .04em;
    box-shadow: 0 0 0 8px rgba(46,139,77,.12);
    animation: aiOrbitGlow 2s ease-in-out infinite;
    flex-shrink: 0; position: relative;
}
.ai-orbit::after {
    content: "";
    position: absolute; inset: -6px; border-radius: 50%;
    border: 1.5px solid transparent;
    border-top-color: rgba(155,207,158,.85);
    border-right-color: rgba(155,207,158,.20);
    border-bottom-color: rgba(155,207,158,.05);
    animation: aiOrbitSpin 1.8s linear infinite;
    pointer-events: none;
}
.ai-thinking-title {
    color: var(--cream) !important;
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 20px; font-weight: 800; line-height: 1.15;
    margin: 0 0 4px 0;
    letter-spacing: -0.01em;
}
.ai-thinking-sub {
    color: #CBD5C0 !important;
    font-size: 13px; line-height: 1.5; margin: 0;
    opacity: .85;
}
.ai-signal-strip {
    display: grid; grid-template-columns: repeat(7, 1fr); gap: 5px;
    margin-top: 16px; position: relative; z-index: 1;
}
.ai-signal-strip span {
    height: 4px; border-radius: 999px;
    background: rgba(155,207,158,.12);
    overflow: hidden; position: relative;
}
.ai-signal-strip span::after {
    content: "";
    position: absolute; inset: 0;
    background: linear-gradient(90deg, transparent, #9BCF9E, transparent);
    animation: aiScanCell 1.6s ease-in-out infinite;
    animation-delay: calc(var(--i) * .12s);
}
.ai-thinking-chips {
    display: flex; flex-wrap: wrap; gap: 8px;
    margin-top: 16px; position: relative; z-index: 1;
}
.ai-thinking-chip {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px; letter-spacing: .12em; text-transform: uppercase;
    color: #9BCF9E; padding: 6px 12px; border-radius: 999px;
    border: 1px solid rgba(155,207,158,.20);
    background: rgba(244,240,231,.07);
    animation: aiChipPulse 2.4s ease-in-out infinite;
    animation-delay: calc(var(--d) * .35s);
    backdrop-filter: blur(4px);
}

/* Staggered review reveal */
.ai-review-reveal .ai-preview-card { animation: aiFadeUp .45s ease both; }
.ai-review-reveal .ai-note:nth-of-type(1) { animation: aiFadeUp .4s ease .08s both; }
.ai-review-reveal .ai-note:nth-of-type(2) { animation: aiFadeUp .4s ease .14s both; }
.ai-review-reveal .ai-field-section:nth-of-type(1) { animation: aiFadeUp .45s ease .12s both; }
.ai-review-reveal .ai-field-section:nth-of-type(2) { animation: aiFadeUp .45s ease .18s both; }

/* Review save action bar */
.ai-save-bar {
    display: flex; align-items: center; gap: 10px;
    margin-top: 4px; padding: 12px 0 0;
    border-top: 1px solid var(--line-soft);
    animation: aiFadeUp .4s var(--ease-out) .3s both;
}
.ai-save-bar .missing-note {
    font-size: 12px; color: var(--ink-mute); line-height: 1.4;
    padding: 8px 12px; border-radius: 10px;
    background: var(--amber-bg); border: 1px solid rgba(183,121,31,.18);
    flex: 1;
}
.ai-save-bar .missing-note strong { color: var(--amber); }

.ai-field-section { transition: border-color .25s ease, box-shadow .25s ease; }
.ai-field-section:focus-within {
    border-color: rgba(46,139,77,.30) !important;
    box-shadow: 0 0 0 4px rgba(46,139,77,.07);
}
.crm-selected-lead-card {
    background: var(--cream-3);
    border: 1px solid var(--line-soft);
    border-radius: var(--r);
    padding: 18px;
    margin: 16px 0;
}
.crm-hero-wrap { margin: 0 0 18px; animation: fadeUp .55s var(--ease-out) both; }
.crm-hero-wrap .eyebrow { margin-bottom: 10px; }
.crm-hero-wrap .wordmark { margin: 8px 0 6px; font-size: clamp(30px, 4.8vw, 52px); }
.crm-hero-wrap .tagline { margin-bottom: 14px; }
.crm-detail-shell {
    background:
      linear-gradient(135deg, rgba(255,255,255,.94), rgba(253,252,249,.88)),
      radial-gradient(120% 140% at 100% 0%, rgba(46,139,77,.10), transparent 55%);
    border: 1px solid rgba(46,139,77,.14);
    border-radius: var(--rl);
    padding: 18px 20px 22px;
    box-shadow: var(--shadow-lg);
    animation: fadeUp .2s var(--ease-out) both;
    margin: 6px 0 20px;
}
.crm-detail-top {
    display: flex; align-items: flex-start; justify-content: space-between;
    gap: 14px; flex-wrap: wrap;
    margin-bottom: 14px; padding-bottom: 14px;
    border-bottom: 1px solid var(--line-soft);
}
.crm-detail-kicker {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px; font-weight: 700; letter-spacing: .18em;
    text-transform: uppercase; color: var(--green); margin-bottom: 6px;
}
.crm-detail-title {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: clamp(24px, 3.2vw, 32px);
    font-weight: 850; color: var(--ink); line-height: 1.02;
    margin: 0;
}
.crm-detail-sub {
    color: var(--ink-mute); font-size: 13px; margin-top: 6px; line-height: 1.45;
}
.crm-detail-badges { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.crm-detail-back-row { margin: 0 0 14px; }
.crm-detail-back-row button {
    max-width: 180px;
    font-weight: 700 !important;
}
.crm-detail-panel {
    background: rgba(255,255,255,.72);
    border: 1px solid var(--line-soft);
    border-radius: var(--r);
    padding: 14px 16px 8px;
    animation: cardIn .2s var(--ease-out) both;
}
@keyframes fadeUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
@keyframes cardIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
    }
    .crm-hero-wrap, .crm-card, .crm-detail-panel { animation: none !important; }
    .ai-thinking-panel, .ai-thinking-panel::before, .ai-thinking-panel::after { animation: none !important; }
    .ai-save-bar [data-testid="baseButton-primary"]:not(:disabled) { animation: none !important; }
}

div[data-testid="stElementContainer"]:has(> [data-testid="stMarkdownContainer"] .crm-row-anchor) {
    margin: 0 !important; height: 0 !important; min-height: 0 !important; overflow: hidden;
}

/* Multi-select toolbar */
.crm-select-toolbar {
    display: flex; align-items: center; justify-content: space-between; gap: 12px;
    flex-wrap: wrap; margin: 0 0 12px; padding: 12px 14px;
    background: linear-gradient(180deg, #ffffff, var(--cream-3));
    border: 1px solid var(--line-soft); border-radius: 14px;
    box-shadow: 0 8px 22px -16px rgba(15,42,51,.22);
}
.crm-select-toolbar .crm-sel-count {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase;
    color: var(--green);
}
.crm-lead-card.crm-selected {
    border-color: rgba(46,139,77,.52);
    background: linear-gradient(180deg, #ffffff, var(--green-bg));
    box-shadow:
      0 1px 2px rgba(15,42,51,.05),
      0 12px 26px -14px rgba(46,139,77,.42),
      inset 0 1px 0 rgba(255,255,255,.8);
}
.crm-sel-mark {
    position: absolute; left: 10px; top: 50%; transform: translateY(-50%);
    width: 22px; height: 22px; border-radius: 7px;
    border: 2px solid rgba(15,42,51,.18);
    background: rgba(255,255,255,.9);
    display: inline-flex; align-items: center; justify-content: center;
    font-size: 13px; font-weight: 800; color: #fff;
    transition: background .2s var(--ease-out), border-color .2s var(--ease-out), transform .2s var(--ease-out);
}
.crm-lead-card.crm-selected .crm-sel-mark {
    background: var(--green); border-color: var(--green); transform: translateY(-50%) scale(1.04);
}
.crm-lead-card.crm-selectable { padding-left: 42px; }
div[class*="st-key-crm_row_"].crm-select-mode [data-testid="stElementContainer"]:has(.crm-lead-hit) + [data-testid="stElementContainer"] button {
    cursor: pointer !important;
}
</style>
"""


def ensure_crm_loaded(*, force: bool = False) -> None:
    org = tenancy.active_org()
    if force or "crm_db" not in st.session_state or st.session_state.get("crm_loaded_org") != org["id"]:
        db, meta = load_crm(org=org, organization_id=org["id"])
        st.session_state["crm_loaded_org"] = org["id"]
        contacts = [
            normalize_contact(c)
            for c in (db.get("contacts") or [])
            if isinstance(c, dict)
        ]
        db["contacts"] = contacts

        raw_custom = db.get("custom_statuses") or []
        if not isinstance(raw_custom, list):
            raw_custom = []
        custom = []
        for s in raw_custom:
            slug = normalize_status(str(s))
            if slug and slug not in CRM_STATUSES and slug not in custom:
                custom.append(slug)
        db["custom_statuses"] = custom

        st.session_state.crm_db = db
        st.session_state.crm_meta = meta
        st.session_state.crm_sha = meta.get("sha")


def persist_crm(message: str = "Update CRM contacts") -> bool:
    db = st.session_state.get("crm_db") or {"contacts": []}
    org = tenancy.active_org()
    result = save_crm(
        db, sha=st.session_state.get("crm_sha"), message=message,
        org=org, organization_id=org["id"],
    )
    st.session_state.crm_meta = result
    if result.get("committed") or result.get("source") == "local":
        st.session_state.crm_sha = result.get("sha")
        return True
    if result.get("conflict"):
        st.warning("Someone else updated the CRM — click Sync, then try again.")
        return False
    if result.get("saved_locally"):
        # Data is safe for this session; only GitHub persistence is degraded.
        st.warning(result.get("error", "Saved locally — GitHub sync unavailable."))
        return True
    if result.get("error"):
        st.error(result.get("error"))
        return False
    st.session_state.crm_sha = result.get("sha")
    return True


def _sync_badge(meta: dict) -> str:
    """Sync badge hidden from UI — persistence still works in the background."""
    return ""


def _github_setup_hint_html() -> str:
    return (
        '<div class="crm-setup-card">'
        '<strong>CRM persistence is not active yet.</strong> Add a GitHub token in Streamlit Secrets as '
        '<code>GITHUB_TOKEN</code>. Optional overrides: <code>GITHUB_REPO</code> and <code>GITHUB_BRANCH</code>.'
        '</div>'
    )


def _status_label(status: str) -> str:
    return STATUS_LABELS.get(status, (status or "new").replace("_", " ").title())


def _source_label(source: str) -> str:
    return SOURCE_LABELS.get(source, (source or "other").replace("_", " ").title())


def _deal_status_label(status: str) -> str:
    return DEAL_STATUS_LABELS.get(status, (status or "open").replace("_", " ").title())


def _value_display(value: str) -> str:
    value = str(value or "").strip()
    return value or "—"


def _fmt_money(value: str) -> str:
    """Compact, India-grouped currency for the lead card (e.g. ₹10,00,000).

    Leaves free-form values ("$50k", "10 lakh") untouched so they still render
    exactly as typed; returns "" for empty so the meta line can be omitted.
    """
    raw = str(value or "").strip()
    if not raw:
        return ""
    cleaned = raw.replace(",", "").replace(" ", "").lstrip("₹$")
    if not cleaned.replace(".", "", 1).isdigit():
        return raw
    s = str(int(float(cleaned)))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return f"₹{s}"


def _available_statuses(db: dict, contacts: list[dict]) -> list[str]:
    """Return fixed pipeline stages plus any legacy values already saved."""
    base = list(CRM_STATUSES)
    extras: list[str] = []

    for c in contacts:
        slug = normalize_status(c.get("status") or "new")
        if slug and slug not in base and slug not in extras:
            extras.append(slug)

    return base + sorted(extras, key=_status_label)


def _stage_snapshot_html(statuses: list[str], contacts: list[dict]) -> str:
    counts = {s: 0 for s in statuses}
    for c in contacts:
        s = normalize_status(c.get("status") or "new")
        if s in counts:
            counts[s] += 1

    total = len(contacts)
    active_statuses = [s for s in statuses if s not in {"won", "lost"}]
    open_count = sum(counts.get(s, 0) for s in active_statuses)
    won_count = counts.get("won", 0)
    lost_count = counts.get("lost", 0)
    due_count = sum(
        1
        for c in contacts
        if _is_due(c) and normalize_deal_status(c.get("deal_status") or "", stage=normalize_status(c.get("status") or "new")) == "open"
    )
    max_count = max(counts.values(), default=0) or 1

    totals = (
        ("Total", total),
        ("Open", open_count),
        ("Due", due_count),
        ("Closed", won_count + lost_count),
    )
    totals_html = "".join(
        '<div class="crm-snapshot-total">'
        f'<div class="n">{value}</div>'
        f'<div class="l">{html.escape(label)}</div>'
        '</div>'
        for label, value in totals
    )

    cards = []
    for s in statuses:
        label = _status_label(s)
        count = counts.get(s, 0)
        pct = round((count / total) * 100) if total else 0
        width = round((count / max_count) * 100) if count else 0
        tone = "win" if s == "won" else "loss" if s == "lost" else "open" if s in active_statuses else "close"
        empty_cls = " crm-stage-empty" if count == 0 else ""
        pct_text = f"{pct}% share" if total else "No leads"
        cards.append(
            f'<div class="crm-stage {tone}{empty_cls}">'
            '<div class="crm-stage-top">'
            f'<div class="crm-stage-label" title="{html.escape(label)}">{html.escape(label)}</div>'
            f'<div class="pct">{html.escape(pct_text)}</div>'
            '</div>'
            f'<div class="n">{count}</div>'
            '<div class="crm-stage-bar">'
            f'<span class="crm-stage-fill" style="width:{width}%"></span>'
            '</div>'
            "</div>"
        )

    empty_hint = (
        "Add contacts or import a lead-agent run to see pipeline movement."
        if not contacts else
        "Counts update instantly as contacts move through the pipeline."
    )

    return (
        '<div class="crm-stage-snap">'
        '<div class="crm-snapshot-card">'
        '<div class="crm-snapshot-top">'
        '<div>'
        '<div class="crm-snapshot-title">Pipeline snapshot</div>'
        f'<div class="crm-snapshot-sub">{html.escape(empty_hint)}</div>'
        '</div>'
        f'<div class="crm-snapshot-totals">{totals_html}</div>'
        '</div>'
        f'<div class="crm-stage-grid">{"".join(cards)}</div>'
        '</div>'
        '</div>'
    )


def _render_pipeline_stage_controls(statuses: list[str]) -> None:
    stage_flow = " → ".join(_status_label(s) for s in CRM_STATUSES)
    source_flow = " · ".join(_source_label(s) for s in CRM_SOURCE_OPTIONS)
    deal_flow = " · ".join(_deal_status_label(s) for s in DEAL_STATUSES)
    st.markdown(
        '<div class="crm-stage-tools">'
        '<div class="crm-stage-tools-head">'
        '<div class="crm-stage-tools-title">CRM fields</div>'
        '<div class="crm-stage-tools-hint">Use dropdowns while adding or editing leads.</div>'
        '</div>'
        f'<div class="crm-stage-note"><strong>Stage:</strong> {html.escape(stage_flow)}</div>'
        f'<div class="crm-stage-note"><strong>Source:</strong> {html.escape(source_flow)}</div>'
        f'<div class="crm-stage-note"><strong>Status:</strong> {html.escape(deal_flow)}</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def _clean_follow_up(raw) -> str | None:
    if isinstance(raw, date):
        return raw.isoformat()
    raw = (raw or "").strip()
    if not raw:
        return ""
    try:
        return date.fromisoformat(raw[:10]).isoformat()
    except ValueError:
        return None


def _date_value(raw: str) -> date | None:
    raw = (raw or "").strip()[:10]
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _is_due(contact: dict) -> bool:
    raw = (contact.get("next_follow_up") or "").strip()[:10]
    if not raw:
        return False
    try:
        return date.fromisoformat(raw) <= date.today()
    except ValueError:
        return False


def _follow_up_bucket(contact: dict) -> str:
    stage = normalize_status(contact.get("status") or "new")
    if normalize_deal_status(contact.get("deal_status") or "", stage=stage) != "open":
        return "closed"
    raw = (contact.get("next_follow_up") or "").strip()[:10]
    if not raw:
        return "none"
    try:
        follow_up = date.fromisoformat(raw)
    except ValueError:
        return "none"
    if follow_up <= date.today():
        return "due"
    if follow_up <= date.today() + timedelta(days=7):
        return "week"
    return "later"


def _reset_crm_filters() -> None:
    defaults = {
        "crm_search": "",
        "crm_stage_filter": "all",
        "crm_source_filter": "all",
        "crm_deal_filter": "all",
        "crm_work_filter": "all",
        "crm_sort": "recent",
        "crm_page": 1,
        "crm_view_mode": "list",
        "crm_selected_contact_id": None,
        "crm_select_mode": False,
        "crm_sel_ids": set(),
    }
    for key, value in defaults.items():
        st.session_state[key] = value


def _toggle_crm_sel(contact_id: str) -> None:
    sel: set = set(st.session_state.get("crm_sel_ids") or set())
    cid = str(contact_id)
    if cid in sel:
        sel.discard(cid)
    else:
        sel.add(cid)
    st.session_state.crm_sel_ids = sel


def _exit_crm_select_mode() -> None:
    st.session_state.crm_select_mode = False
    st.session_state.crm_sel_ids = set()


def _select_crm_ids(contact_ids: list[str]) -> None:
    st.session_state.crm_sel_ids = {str(cid) for cid in contact_ids if cid}


def _clear_crm_selection() -> None:
    st.session_state.crm_sel_ids = set()


def _bulk_delete_selected() -> None:
    sel = {str(cid) for cid in (st.session_state.get("crm_sel_ids") or set())}
    if not sel:
        return
    contacts = [
        c for c in st.session_state.crm_db.get("contacts", [])
        if str(c.get("id")) not in sel
    ]
    n = len(sel)
    st.session_state.crm_db["contacts"] = contacts
    if persist_crm(f"CRM: bulk delete {n} leads"):
        st.session_state.crm_sel_ids = set()
        st.session_state.crm_select_mode = False
        st.session_state.crm_save_toast = f"Removed {n} lead{'s' if n != 1 else ''}"


def _selected_contacts() -> list[dict]:
    sel = {str(cid) for cid in (st.session_state.get("crm_sel_ids") or set())}
    if not sel:
        return []
    return [
        c for c in st.session_state.crm_db.get("contacts", [])
        if str(c.get("id")) in sel
    ]


def _bulk_update_status(new_status: str) -> None:
    sel = {str(cid) for cid in (st.session_state.get("crm_sel_ids") or set())}
    if not sel:
        return
    stage = normalize_status(new_status)
    n = 0
    for c in st.session_state.crm_db.get("contacts", []):
        if str(c.get("id")) not in sel:
            continue
        c["status"] = stage
        if stage in {"won", "lost"}:
            c["deal_status"] = stage
        c["updated_at"] = utc_now_iso()
        n += 1
    if persist_crm(f"CRM: bulk stage → {stage} ({n})"):
        st.session_state.crm_save_toast = f"Updated stage to {_status_label(stage)} for {n} lead{'s' if n != 1 else ''}"


def _apply_status_to_contact(contact_id: str, new_status: str) -> bool:
    stage = normalize_status(new_status)
    for c in st.session_state.crm_db.get("contacts", []):
        if str(c.get("id")) != str(contact_id):
            continue
        c["status"] = stage
        if stage in {"won", "lost"}:
            c["deal_status"] = stage
        c["updated_at"] = utc_now_iso()
        label = _status_label(stage)
        name = display_name(c)
        if persist_crm(f"CRM: {name} → {stage}"):
            st.session_state.crm_save_toast = f"{name} moved to {label}"
            return True
        return False
    return False


def _log_broadcast_email(contact: dict, subject: str, body: str) -> None:
    event = crm_models.normalize_email_event({
        "direction": "sent",
        "to": contact.get("email") or "",
        "subject": subject,
        "body": body,
        "summary": "Broadcast email",
        "source": "broadcast",
    })
    contact.setdefault("email_events", []).append(event)
    if normalize_status(contact.get("status") or "new") == "new":
        contact["status"] = "contacted"
    contact["updated_at"] = utc_now_iso()


def _log_broadcast_whatsapp(
    contact: dict,
    body: str,
    *,
    message_id: str = "",
    campaign_id: str = "",
    template_name: str = "",
) -> None:
    if message_id:
        append_outbound_event(
            contact,
            message_id=message_id,
            body=body,
            campaign_id=campaign_id,
            template_name=template_name,
        )
    else:
        comment = {
            "id": new_contact_id(),
            "body": body,
            "author": "CRM broadcast",
            "source": "whatsapp",
            "created_at": utc_now_iso(),
        }
        contact.setdefault("comments", []).append(comment)
    if normalize_status(contact.get("status") or "new") == "new":
        contact["status"] = "contacted"
    contact["updated_at"] = utc_now_iso()


def _broadcast_email_selected(subject: str, body: str) -> dict[str, int]:
    selected = _selected_contacts()
    sent = skipped = failed = 0
    for c in selected:
        email = (c.get("email") or "").strip()
        if not email:
            skipped += 1
            continue
        msg_body = personalise(body, c)
        result = send_email_smtp(email, subject, msg_body)
        if result.get("ok"):
            _log_broadcast_email(c, subject, msg_body)
            sent += 1
        else:
            failed += 1
    if sent:
        persist_crm(f"CRM: broadcast email to {sent} leads")
    return {"sent": sent, "skipped": skipped, "failed": failed}


def _broadcast_whatsapp_selected(
  body: str,
  *,
  template_name: str = "",
  use_template: bool = False,
) -> dict[str, int]:
    selected = _selected_contacts()
    sent = skipped = failed = 0
    campaign_id = datetime.now().strftime("wa_%Y%m%d_%H%M%S")
    for c in selected:
        phone = (c.get("phone") or "").strip()
        if not phone:
            skipped += 1
            continue
        msg_body = personalise(body, c)
        try:
            if use_template and template_name:
                resp = send_whatsapp_template(phone, template_name, body_params=[msg_body[:1024]])
            else:
                resp = send_whatsapp_text(phone, msg_body)
            mid = extract_sent_message_id(resp)
            _log_broadcast_whatsapp(
                c,
                msg_body,
                message_id=mid,
                campaign_id=campaign_id,
                template_name=template_name if use_template else "",
            )
            sent += 1
        except Exception:
            failed += 1
    if sent:
        persist_crm(f"CRM: WhatsApp broadcast {campaign_id} to {sent} leads")
        st.session_state.crm_last_wa_campaign = campaign_id
    return {"sent": sent, "skipped": skipped, "failed": failed, "campaign_id": campaign_id}


def _render_selection_toolbar(*, filtered_ids: list[str], page_ids: list[str]) -> None:
    st.session_state.setdefault("crm_sel_ids", set())
    st.session_state.setdefault("crm_select_mode", False)
    sel_ids: set = set(st.session_state.get("crm_sel_ids") or set())
    select_mode = bool(st.session_state.crm_select_mode)
    n_sel = len(sel_ids)

    if not select_mode and n_sel == 0:
        if st.button("Select leads", key="crm_enter_select", type="secondary"):
            st.session_state.crm_select_mode = True
            st.rerun()
        return

    st.markdown('<div class="crm-select-toolbar">', unsafe_allow_html=True)
    left, right = st.columns([2.4, 1.2])
    with left:
        mode_col, page_col, all_col, clear_col = st.columns(4)
        with mode_col:
            label = "Done selecting" if select_mode else "Select leads"
            if st.button(label, key="crm_toggle_select_mode", use_container_width=True, type="primary" if select_mode else "secondary"):
                if select_mode:
                    _exit_crm_select_mode()
                else:
                    st.session_state.crm_select_mode = True
                st.rerun()
        with page_col:
            if st.button("Select page", key="crm_sel_page", use_container_width=True, disabled=not page_ids):
                merged = sel_ids | {str(cid) for cid in page_ids}
                st.session_state.crm_sel_ids = merged
                st.session_state.crm_select_mode = True
                st.rerun()
        with all_col:
            if st.button("Select all", key="crm_sel_all", use_container_width=True, disabled=not filtered_ids):
                st.session_state.crm_sel_ids = {str(cid) for cid in filtered_ids}
                st.session_state.crm_select_mode = True
                st.rerun()
        with clear_col:
            if st.button("Clear", key="crm_sel_clear", use_container_width=True, disabled=n_sel == 0):
                _clear_crm_selection()
                st.rerun()
    with right:
        if n_sel:
            st.markdown(
                f'<div class="crm-sel-count" style="text-align:right;margin-top:10px;">'
                f'{n_sel} selected</div>',
                unsafe_allow_html=True,
            )
        act_a, act_b, act_c = st.columns(3)
        with act_a:
            with st.popover("Update stage", use_container_width=True, disabled=n_sel == 0):
                bulk_stage = st.selectbox(
                    "New stage",
                    CRM_STATUSES,
                    format_func=_status_label,
                    key="crm_bulk_stage_pick",
                )
                if st.button("Apply to selected", key="crm_bulk_stage_apply", type="primary", use_container_width=True):
                    _bulk_update_status(bulk_stage)
                    st.rerun()
        with act_b:
            with st.popover("Email broadcast", use_container_width=True, disabled=n_sel == 0):
                if not smtp_configured():
                    st.warning("Add SMTP_FROM_EMAIL and SMTP_APP_PASSWORD in secrets to send.")
                st.caption("One message to all selected leads with an email on file.")
                bc_subj = st.text_input("Subject", key="crm_bc_email_subj", placeholder="Summer offer for your team")
                bc_body = st.text_area("Body", key="crm_bc_email_body", height=120, placeholder="Hi {{name}}, …")
                if st.button("AI draft", key="crm_bc_email_ai", use_container_width=True, disabled=not llm_configured()):
                    draft = compose_broadcast(
                        lead_count=n_sel,
                        industries=[c.get("industry") or "" for c in _selected_contacts()],
                        goal=st.session_state.get("crm_bc_email_subj") or "share a promotion",
                    )
                    st.session_state.crm_bc_email_subj = draft["subject"]
                    st.session_state.crm_bc_email_body = draft["email_body"]
                    st.rerun()
                if st.button("Send broadcast", key="crm_bc_email_send", type="primary", use_container_width=True, disabled=not smtp_configured()):
                    stats = _broadcast_email_selected(bc_subj, bc_body)
                    st.session_state.crm_save_toast = (
                        f"Email sent: {stats['sent']} · skipped: {stats['skipped']} · failed: {stats['failed']}"
                    )
                    st.rerun()
        with act_c:
            with st.popover("WhatsApp", use_container_width=True, disabled=n_sel == 0):
                feas = broadcast_feasibility(_selected_contacts())
                st.caption(
                    f"{feas['with_phone']}/{feas['total']} selected have phone numbers. "
                    f"{feas['whatsapp_source']} messaged via WhatsApp before."
                )
                st.info(feas["free_text_window"])
                last_cid = st.session_state.get("crm_last_wa_campaign")
                if last_cid:
                    stats = campaign_summary(st.session_state.crm_db.get("contacts", []), last_cid)
                    st.caption(
                        f"Last campaign `{last_cid}`: "
                        f"{stats['read']} read · {stats['delivered']} delivered · "
                        f"{stats['failed']} failed · {stats['total']} total"
                    )
                use_tpl = st.checkbox("Use approved template (promotions)", key="crm_bc_wa_tpl")
                tpl_name = st.text_input("Template name", key="crm_bc_wa_tpl_name", disabled=not use_tpl, placeholder="promo_offer")
                wa_body = st.text_area("Message", key="crm_bc_wa_body", height=100, placeholder="Hi {{name}}, …")
                if st.button("AI draft", key="crm_bc_wa_ai", use_container_width=True, disabled=not llm_configured()):
                    draft = compose_broadcast(
                        lead_count=n_sel,
                        industries=[c.get("industry") or "" for c in _selected_contacts()],
                    )
                    st.session_state.crm_bc_wa_body = draft["whatsapp_body"]
                    st.rerun()
                if st.button(
                    "Send WhatsApp",
                    key="crm_bc_wa_send",
                    type="primary",
                    use_container_width=True,
                    disabled=not whatsapp_configured(),
                ):
                    stats = _broadcast_whatsapp_selected(
                        wa_body,
                        template_name=tpl_name,
                        use_template=use_tpl,
                    )
                    st.session_state.crm_save_toast = (
                        f"WhatsApp campaign {stats.get('campaign_id', '')}: "
                        f"{stats['sent']} sent · {stats['skipped']} no phone · {stats['failed']} failed. "
                        f"Delivery/read updates arrive via webhook."
                    )
                    st.rerun()
        with st.popover(f"Delete {n_sel} selected", use_container_width=True, disabled=n_sel == 0):
            st.warning(f"Delete {n_sel} lead{'s' if n_sel != 1 else ''} and all related activity? This can't be undone.")
            if st.button("Yes, delete selected", key="crm_bulk_delete_confirm", type="primary", use_container_width=True):
                _bulk_delete_selected()
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def _open_lead_detail(contact_id: str) -> None:
    st.session_state.crm_selected_contact_id = str(contact_id)
    st.session_state.crm_view_mode = "detail"


def _close_lead_detail() -> None:
    st.session_state.crm_view_mode = "list"
    st.session_state.crm_selected_contact_id = None


def _safe_widget_key(raw: str) -> str:
    """Streamlit widget keys must be stable and avoid problematic characters."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", str(raw or "lead"))


def _contact_index_map(contacts: list[dict]) -> dict[str, int]:
    return {str(c.get("id")): i for i, c in enumerate(contacts) if c.get("id")}


def _resolve_contact_index(contacts: list[dict], contact_id: str | None) -> int | None:
    if not contact_id:
        return None
    idx = _contact_index_map(contacts).get(str(contact_id))
    return idx if idx is not None else None


def _sync_stage_widget(stage_key: str, deal_key: str) -> None:
    stage = st.session_state.get(stage_key, "new")
    deal_state = st.session_state.get(deal_key, "open")
    if stage in {"won", "lost"}:
        st.session_state[deal_key] = stage
    elif deal_state in {"won", "lost"}:
        st.session_state[deal_key] = "open"


def _sync_deal_widget(stage_key: str, deal_key: str) -> None:
    deal_state = st.session_state.get(deal_key, "open")
    stage = st.session_state.get(stage_key, "new")
    if deal_state in {"won", "lost"}:
        st.session_state[stage_key] = deal_state
    elif stage in {"won", "lost"}:
        st.session_state[stage_key] = "proposal"


def _contact_source(contact: dict) -> str:
    return normalize_source(contact.get("source") or "other")


def _href(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if url.startswith(("http://", "https://", "mailto:", "tel:")):
        return url
    return f"https://{url}"


def _contact_actions(contact: dict) -> str:
    links = []
    phone = (contact.get("phone") or "").strip()
    email = (contact.get("email") or "").strip()
    linkedin = (contact.get("linkedin_url") or "").strip()
    website = (contact.get("website") or "").strip()
    if phone:
        tel = "".join(ch for ch in phone if ch.isdigit() or ch == "+")
        links.append((f"tel:{tel}", "☎ Call"))
    if email:
        links.append((f"mailto:{email}", "✉ Email"))
    if linkedin:
        links.append((_href(linkedin), "in LinkedIn"))
    if website:
        links.append((_href(website), "↗ Site"))
    if not links:
        return ""
    return '<div class="crm-actions">' + "".join(
        f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noreferrer">{html.escape(label)}</a>'
        for url, label in links
    ) + "</div>"


def _upsert_contact(contact: dict) -> tuple[str, dict]:
    contacts = list(st.session_state.crm_db.get("contacts") or [])
    incoming_fp = contact_fingerprint(contact)
    for i, existing in enumerate(contacts):
        if contact_fingerprint(existing) == incoming_fp:
            merged = merge_contacts(existing, contact)
            incoming_notes = (contact.get("notes") or "").strip()
            existing_notes = (existing.get("notes") or "").strip()
            if incoming_notes and existing_notes and incoming_notes not in existing_notes:
                merged["notes"] = f"{existing_notes}\n{incoming_notes}"
            if contact.get("next_follow_up"):
                merged["next_follow_up"] = contact["next_follow_up"]
            merged["updated_at"] = utc_now_iso()
            contacts[i] = normalize_contact(merged)
            st.session_state.crm_db["contacts"] = contacts
            return "updated", contacts[i]
    contacts.append(contact)
    st.session_state.crm_db["contacts"] = contacts
    return "added", contact


def _render_quick_add() -> None:
    contacts = st.session_state.get("crm_db", {}).get("contacts") or []
    source_default = CRM_SOURCE_OPTIONS.index("other") if "other" in CRM_SOURCE_OPTIONS else 0
    with st.expander("Add a lead", expanded=not contacts):
        st.caption("Capture the minimum now; enrich the activity, contacts, and agent context later.")
        with st.form("crm_quick_add", clear_on_submit=True, border=False):
            c1, c2, c3 = st.columns([1.2, 1, 1])
            with c1:
                company = st.text_input("Company", placeholder="Prestige Group")
            with c2:
                industry = st.text_input("Industry", placeholder="Real estate")
            with c3:
                owner = st.text_input("Owner", placeholder="Sales owner")

            c4, c5, c6 = st.columns([1.1, 1, 1])
            with c4:
                name = st.text_input("Contact name", placeholder="Rajesh Kumar")
            with c5:
                email = st.text_input("Contact email", placeholder="name@company.com")
            with c6:
                phone = st.text_input("Phone", placeholder="+91 98xxx xxxxx")

            c7, c8, c9, c10 = st.columns([1, 1, 1, 1])
            with c7:
                source = st.selectbox("Source", CRM_SOURCE_OPTIONS, index=source_default, format_func=_source_label)
            with c8:
                stage = st.selectbox("Stage", CRM_STATUSES, format_func=_status_label)
            with c9:
                deal_status = st.selectbox("Deal state", DEAL_STATUSES, format_func=_deal_status_label)
            with c10:
                value = st.text_input("Value", placeholder="INR 1,00,000")

            c11, c12 = st.columns([1, 2])
            with c11:
                follow_up = st.date_input("Follow-up date", value=None, format="YYYY-MM-DD")
            with c12:
                client = st.text_input("For client", placeholder="SN Realtors")

            notes = st.text_area("Quick note", placeholder="Context, requirement, objection, or next step...")
            if st.form_submit_button("Add lead", type="primary", use_container_width=True):
                clean_follow_up = _clean_follow_up(follow_up)
                if clean_follow_up is None:
                    st.error("Use YYYY-MM-DD for follow-up date.")
                elif not company.strip() and not name.strip() and not phone.strip() and not email.strip():
                    st.error("Add at least a company, contact name, phone, or email.")
                else:
                    contact = normalize_contact(
                        {
                            "id": new_contact_id(),
                            "name": name,
                            "phone": phone,
                            "email": email,
                            "company": company,
                            "industry": industry,
                            "client": client,
                            "owner": owner,
                            "value": value,
                            "status": stage,
                            "deal_status": deal_status,
                            "notes": notes,
                            "next_follow_up": clean_follow_up,
                            "source": source,
                            "tags": ["manual", "ground"],
                        }
                    )
                    action, saved = _upsert_contact(contact)
                    if persist_crm(f"CRM: {action} {display_name(saved)}"):
                        st.toast(f"{'Updated' if action == 'updated' else 'Added'} {display_name(saved)}")
                        st.rerun()


def _render_excel_upload() -> None:
    with st.expander("Import leads from Excel / CSV", expanded=False):
        st.caption("Upload an Excel (.xlsx, .xls) or CSV file to import leads. Columns will be automatically mapped to CRM fields.")
        
        uploaded_file = st.file_uploader(
            "Upload leads file",
            type=["xlsx", "xls", "csv"],
            key="crm_excel_file_upload",
            label_visibility="collapsed"
        )
        
        if uploaded_file:
            import pandas as pd
            try:
                if uploaded_file.name.endswith(".csv"):
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file)
                
                # Column synonyms
                col_mapping = {
                    "company": ["company", "company name", "firm", "business", "organization", "organisation", "company_name"],
                    "name": ["name", "contact", "contact name", "person", "lead name", "full name", "lead", "contact_name", "primary contact"],
                    "phone": ["phone", "telephone", "mobile", "phone number", "mobile number", "tel"],
                    "email": ["email", "email address", "mail", "e-mail", "contact_email"],
                    "client": ["client", "for client", "target client"],
                    "industry": ["industry", "sector", "niche"],
                    "owner": ["owner", "assigned to", "sales rep", "lead owner"],
                    "value": ["value", "amount", "deal value", "price", "deal size", "budget", "deal_value"],
                    "status": ["status", "stage", "lead status", "lead stage", "pipeline stage"],
                    "notes": ["notes", "comments", "description", "context", "details", "requirement", "tech gap"],
                    "next_follow_up": ["next_follow_up", "follow up", "follow-up", "follow up date", "follow-up date"],
                    "source": ["source", "lead source"],
                    "title": ["title", "job title", "designation", "role", "contact_title"],
                    "linkedin_url": ["linkedin", "linkedin url", "linkedin profile", "linkedin_url"],
                    "website": ["website", "site", "domain", "web site", "url"],
                    "score": ["score", "lead score", "total score"],
                    "signal": ["signal", "buying signal", "trigger"],
                    "opening_line": ["opening line", "opener", "pitch"],
                }
                
                mapped_cols = {}
                for std_col, synonyms in col_mapping.items():
                    for col in df.columns:
                        if str(col).lower().strip() in synonyms:
                            mapped_cols[std_col] = col
                            break
                
                # Check for substring matches for essential fields if not mapped yet
                if "name" not in mapped_cols:
                    for col in df.columns:
                        col_lower = str(col).lower()
                        if "name" in col_lower or "contact" in col_lower:
                            mapped_cols["name"] = col
                            break
                if "company" not in mapped_cols:
                    for col in df.columns:
                        col_lower = str(col).lower()
                        if "company" in col_lower or "firm" in col_lower or "business" in col_lower:
                            mapped_cols["company"] = col
                            break
                
                if not mapped_cols.get("name") and not mapped_cols.get("company"):
                    st.warning("Could not identify a column for Contact Name or Company. Please ensure your file has headers like 'Name' or 'Company'.")
                else:
                    # Filter out empty rows
                    valid_rows = []
                    for idx, row in df.iterrows():
                        name_val = str(row[mapped_cols["name"]]).strip() if "name" in mapped_cols else ""
                        comp_val = str(row[mapped_cols["company"]]).strip() if "company" in mapped_cols else ""
                        email_val = str(row[mapped_cols["email"]]).strip() if "email" in mapped_cols else ""
                        
                        if (name_val and name_val.lower() != "nan" and name_val != "") or \
                           (comp_val and comp_val.lower() != "nan" and comp_val != "") or \
                           (email_val and email_val.lower() != "nan" and email_val != ""):
                            valid_rows.append(row)
                            
                    if not valid_rows:
                        st.warning("No valid rows found in the file (must have at least a Name, Company, or Email).")
                    else:
                        st.success(f"Found {len(valid_rows)} valid leads in the file. Columns mapped: {', '.join(mapped_cols.keys())}")
                        
                        # Preview
                        preview_rows = []
                        for row in valid_rows[:3]:
                            p_row = {}
                            for std_col, df_col in mapped_cols.items():
                                val = row[df_col]
                                p_row[std_col] = "" if pd.isna(val) else str(val)
                            preview_rows.append(p_row)
                        
                        st.markdown("**Preview of mapped columns:**")
                        st.dataframe(pd.DataFrame(preview_rows), use_container_width=True)
                        
                        # Import Button
                        if st.button("Import Leads & Sort CRM", type="primary", use_container_width=True, key="crm_excel_import_submit"):
                            leads = []
                            unmapped_cols = [col for col in df.columns if col not in mapped_cols.values()]
                            for row in valid_rows:
                                lead = {}
                                for std_col, df_col in mapped_cols.items():
                                    val = row[df_col]
                                    if pd.isna(val):
                                        val = ""
                                    lead[std_col] = str(val).strip()
                                
                                # Map standard keys to lead_to_contact expected keys
                                if "company" in lead:
                                    lead["company_name"] = lead["company"]
                                if "name" in lead:
                                    lead["contact_name"] = lead["name"]
                                if "title" in lead:
                                    lead["contact_title"] = lead["title"]
                                if "score" in lead:
                                    lead["total_score"] = lead["score"]
                                if "signal" in lead:
                                    lead["primary_signal"] = lead["signal"]
                                
                                # Gather unmapped columns into notes
                                lead_notes = []
                                if lead.get("notes"):
                                    lead_notes.append(lead["notes"])
                                for col in unmapped_cols:
                                    val = row[col]
                                    if not pd.isna(val) and str(val).strip() and str(val).strip().lower() != "nan":
                                        lead_notes.append(f"{col}: {str(val).strip()}")
                                if lead_notes:
                                    lead["notes"] = "\n".join(lead_notes)
                                
                                # Default fields if missing
                                lead.setdefault("source", "other")
                                lead.setdefault("status", "new")
                                lead.setdefault("deal_status", "open")
                                lead["tags"] = ["excel-import"]
                                
                                leads.append(lead)
                            
                            db = st.session_state.crm_db
                            run_id = f"excel_upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                            db, stats = import_leads_to_crm(db, leads, agent_run_id=run_id)
                            st.session_state.crm_db = db
                            
                            # Persist
                            if persist_crm(f"CRM: imported {stats.get('added', 0)} from Excel"):
                                st.session_state.crm_save_toast = f"Import complete: {stats.get('added', 0)} added, {stats.get('updated', 0)} updated."
                                # Set sort to Recent so new ones are at the top
                                st.session_state.crm_sort = "recent"
                                st.session_state.crm_page = 1
                                st.rerun()
            except Exception as e:
                st.error(f"Error parsing file: {e}")


def _open_ai_dialog() -> None:
    """Open the AI intake dialog with a fresh capture state."""
    st.session_state.crm_ai_dialog_open = True
    st.session_state.ai_intake = {
        "phase": "capture",
        "result": None,
        "existing": None,
        "last_error": "",
        "capture_text": "",
    }
    for k in ("ai_text",):
        st.session_state.pop(k, None)
    st.session_state["_ai_active_template"] = -1
    st.session_state["_ai_example_placeholder"] = ""
    st.session_state["_ai_template_source"] = ""


def _close_ai_dialog() -> None:
    st.session_state.crm_ai_dialog_open = False
    st.session_state["_ai_active_template"] = -1
    st.session_state["_ai_example_placeholder"] = ""
    st.session_state["_ai_template_source"] = ""
    for k in ("ai_intake", "ai_text"):
        st.session_state.pop(k, None)


def _reset_ai_intake() -> None:
    _close_ai_dialog()


def _render_ai_steps(*, active: str) -> None:
    on_capture = active in ("capture", "processing")
    step2_label = "Structuring…" if active == "processing" else "Review & save"
    fill_pct = 18 if on_capture else 100
    if active == "processing":
        fill_pct = 52
    st.markdown(
        f'<div class="ai-progress-wrap" style="animation:aiFadeUp .4s ease both">'
        f'<div class="ai-progress-meta">'
        f'<span class="ai-progress-step {"on" if on_capture else "done"}">'
        f'{"Structuring…" if active == "processing" else "Describe"}</span>'
        f'<span class="ai-progress-step {"on" if not on_capture else ""}">{html.escape(step2_label)}</span>'
        f"</div>"
        f'<div class="ai-progress-track"><div class="ai-progress-fill" style="width:{fill_pct}%"></div></div>'
        f"</div>",
        unsafe_allow_html=True,
    )


def _render_ai_thinking(*, mode: str = "ai") -> None:
    """Premium loader while Gemini (or basic parser) structures the lead."""
    if mode == "basic":
        title = "Parsing your notes"
        sub = "Filling contact fields without AI — quick and local."
        chips = ["Reading text", "Extracting phone", "Matching fields"]
        badge = "LOCAL"
    else:
        title = "Gemini is structuring your lead"
        sub = "Extracting name, phone, company, and meeting notes…"
        chips = ["Reading notes", "Identifying contact", "Mapping fields", "Drafting summary"]
        badge = "GEMINI"
    signal = "".join(f'<span style="--i:{i}"></span>' for i in range(7))
    chip_html = "".join(
        f'<span class="ai-thinking-chip" style="--d:{i}">{html.escape(c)}</span>'
        for i, c in enumerate(chips)
    )
    st.markdown(
        f'<div class="ai-thinking-panel">'
        f'<div class="ai-thinking-top">'
        f'<div class="ai-orbit">{html.escape(badge)}</div>'
        f'<div><p class="ai-thinking-title">{html.escape(title)}</p>'
        f'<p class="ai-thinking-sub">{html.escape(sub)}</p></div>'
        f"</div>"
        f'<div class="ai-signal-strip">{signal}</div>'
        f'<div class="ai-thinking-chips">{chip_html}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )


def _ai_preview_initials(name: str, company: str) -> str:
    src = (name or company or "?").strip()
    bits = src.split()
    if len(bits) >= 2:
        return (bits[0][0] + bits[1][0]).upper()
    return src[:2].upper()


@st.dialog("New lead", width="large")
def _ai_add_dialog() -> None:
    """Type or dictate → AI structures → save. Dialog stays open across reruns."""
    from agent.crm_intake_agent import basic_parse_from_text, friendly_ai_error, parse_contact

    state = st.session_state.setdefault(
        "ai_intake",
        {"phase": "capture", "result": None, "existing": None, "last_error": "", "capture_text": ""},
    )

    phase = state.get("phase") or "capture"
    wrap_cls = "ai-dialog-wrap"
    if phase == "review" and state.pop("review_reveal", False):
        wrap_cls += " ai-review-reveal"
    if phase == "processing":
        wrap_cls += " ai-dialog-processing"

    st.markdown(f'<div class="{wrap_cls}">', unsafe_allow_html=True)

    # ── Phase 1b: processing (animated loader, then parse) ────────────────────
    if phase == "processing":
        mode = state.get("processing_mode") or "ai"
        _render_ai_dialog_header(
            title="Structuring your lead",
            subtitle="Gemini is mapping name, company, phone, and notes.",
            step="processing",
        )
        _render_ai_steps(active="processing")
        _render_ai_thinking(mode=mode)

        if not state.get("_processing_visible"):
            state["_processing_visible"] = True
            st.markdown("</div>", unsafe_allow_html=True)
            st.rerun()

        text_value = (state.get("processing_text") or "").strip()
        existing = dict(state.get("existing") or {})
        try:
            if mode == "basic":
                res = basic_parse_from_text(text=text_value, existing=existing or None)
            else:
                res = parse_contact(text=text_value, existing=existing or None)
        except Exception as exc:  # noqa: BLE001
            state["last_error"] = friendly_ai_error(exc)
            state["capture_text"] = text_value
            state["phase"] = "capture"
            for k in ("processing_text", "processing_mode", "_processing_visible"):
                state.pop(k, None)
            st.markdown("</div>", unsafe_allow_html=True)
            st.rerun()

        state["existing"] = dict(res.get("fields") or {})
        tmpl_source = st.session_state.get("_ai_template_source") or ""
        if tmpl_source and not state["existing"].get("source"):
            state["existing"]["source"] = tmpl_source
        state["result"] = res
        state["phase"] = "review"
        state["review_reveal"] = True
        for k in ("processing_text", "processing_mode", "_processing_visible"):
            state.pop(k, None)
        st.session_state.pop("ai_text", None)
        st.markdown("</div>", unsafe_allow_html=True)
        st.rerun()

    # ── Phase 1: describe ─────────────────────────────────────────────────────
    if phase == "capture":
        existing = dict(state.get("existing") or {})
        active_template = st.session_state.get("_ai_active_template", -1)
        skip_ai = False
        review = False

        _render_ai_dialog_header(
            title="Who did you meet?",
            subtitle="Pick a source, jot a line — Gemini structures the rest.",
            step="capture",
        )
        _render_ai_steps(active="capture")

        if existing:
            _render_ai_captured_summary(existing)
            prior = state.get("result") or {}
            if prior.get("follow_up"):
                st.markdown(
                    f'<div class="ai-note warn"><span class="tag">Add next</span>'
                    f'<span>{html.escape(prior["follow_up"])}</span></div>',
                    unsafe_allow_html=True,
                )

        with st.container(border=True):
            st.markdown(
                '<span class="ai-field-label">Where did this lead come from?</span>',
                unsafe_allow_html=True,
            )
            _render_ai_template_picker(active=active_template)

            example_text = ""
            if 0 <= active_template < len(AI_INTAKE_TEMPLATES):
                example_text = AI_INTAKE_TEMPLATES[active_template]["example"]
            elif st.session_state.get("_ai_example_placeholder"):
                example_text = st.session_state["_ai_example_placeholder"]

            typed_now = (st.session_state.get("ai_text") or "").strip()
            if example_text and not typed_now:
                st.markdown(
                    f'<div class="ai-example-ghost">'
                    f'<span class="eg-tag">Example · tap Structure to use as-is</span>'
                    f'<p>{html.escape(example_text)}</p>'
                    f"</div>",
                    unsafe_allow_html=True,
                )

            if state.get("capture_text") and "ai_text" not in st.session_state:
                st.session_state["ai_text"] = state["capture_text"]
                st.session_state["_ai_active_template"] = -1
                st.session_state["_ai_example_placeholder"] = ""

            if state.get("last_error"):
                if "Gemini credits" in state["last_error"] or "Continue without AI" in state["last_error"]:
                    st.warning(state["last_error"])
                else:
                    st.error(state["last_error"])

            st.markdown(
                '<span class="ai-field-label ai-field-label--spaced">Your notes</span>',
                unsafe_allow_html=True,
            )
            with st.form("ai_capture_form", clear_on_submit=False, border=False):
                st.text_area(
                    "Lead details",
                    key="ai_text",
                    height=120,
                    placeholder="Name, company, phone, context…",
                    label_visibility="collapsed",
                )
                btn_skip, btn_ai = st.columns([1, 1.45])
                with btn_skip:
                    skip_ai = st.form_submit_button("Skip AI", use_container_width=True)
                with btn_ai:
                    review = st.form_submit_button("Structure with AI →", type="primary", use_container_width=True)

        st.markdown('<div class="ai-dialog-footer">', unsafe_allow_html=True)
        foot_l, foot_r = st.columns([1, 1.6])
        with foot_l:
            if st.button("Cancel", key="ai_capture_cancel"):
                _close_ai_dialog()
                st.rerun()
        with foot_r:
            st.markdown(
                '<span class="ai-footer-note">Gemini 2.5 Flash · Ctrl+Enter to submit</span>',
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)

        if skip_ai:
            text_value = _resolve_ai_capture_text()
            if not text_value:
                state["last_error"] = "Pick a source or type a few details first."
                st.rerun()
            state["last_error"] = ""
            state["phase"] = "processing"
            state["processing_mode"] = "basic"
            state["processing_text"] = text_value
            state.pop("_processing_visible", None)
            st.rerun()

        if review:
            text_value = _resolve_ai_capture_text()
            if not text_value:
                state["last_error"] = "Pick a source or type a few details first."
                st.rerun()
            state["last_error"] = ""
            state["phase"] = "processing"
            state["processing_mode"] = "ai"
            state["processing_text"] = text_value
            state.pop("_processing_visible", None)
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # ── Phase 2: review & save ────────────────────────────────────────────────
    _render_ai_dialog_header(
        title="Review your lead",
        subtitle="Edit anything before saving to the CRM.",
        step="review",
    )
    _render_ai_steps(active="review")

    res = state.get("result") or {}
    f = dict(res.get("fields") or {})
    preview_name = f.get("name") or f.get("company") or "New lead"
    meta_parts = [p for p in (f.get("phone"), f.get("email")) if p]
    if f.get("name") and f.get("company"):
        meta_parts.append(f["company"])
    preview_meta = " · ".join(meta_parts) or "Fill in phone or email to save"

    st.markdown(
        f'<div class="ai-preview-card">'
        f'<div class="ai-preview-avatar">{html.escape(_ai_preview_initials(f.get("name",""), f.get("company","")))}</div>'
        f'<div><p class="ai-preview-name">{html.escape(preview_name)}</p>'
        f'<p class="ai-preview-meta">{html.escape(preview_meta)}</p></div></div>',
        unsafe_allow_html=True,
    )

    if res.get("summary"):
        st.markdown(
            f'<div class="ai-note ok"><span class="tag">Summary</span>'
            f'<span>{html.escape(res["summary"])}</span></div>',
            unsafe_allow_html=True,
        )
    if res.get("follow_up"):
        st.markdown(
            f'<div class="ai-note warn"><span class="tag">Missing</span>'
            f'<span>{html.escape(res["follow_up"])}</span></div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="ai-field-section"><div class="sec-label">Contact</div>', unsafe_allow_html=True)
    r1a, r1b, r1c = st.columns(3)
    with r1a:
        f["name"] = st.text_input("Name", f.get("name", ""), key="aif_name")
    with r1b:
        f["phone"] = st.text_input("Phone", f.get("phone", ""), key="aif_phone")
    with r1c:
        f["email"] = st.text_input("Email", f.get("email", ""), key="aif_email")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="ai-field-section"><div class="sec-label">Deal</div>', unsafe_allow_html=True)
    r2a, r2b, r2c = st.columns(3)
    with r2a:
        f["company"] = st.text_input("Company", f.get("company", ""), key="aif_company")
    with r2b:
        f["client"] = st.text_input("For client", f.get("client", ""), key="aif_client")
    with r2c:
        _stg = f.get("status") or "new"
        f["status"] = st.selectbox(
            "Stage",
            CRM_STATUSES,
            index=CRM_STATUSES.index(_stg) if _stg in CRM_STATUSES else 0,
            format_func=_status_label,
            key="aif_status",
        )
    f["notes"] = st.text_area("Notes", f.get("notes", ""), key="aif_notes", height=72)
    st.markdown("</div>", unsafe_allow_html=True)

    with st.expander("More details (optional)"):
        m1, m2, m3 = st.columns(3)
        with m1:
            f["title"] = st.text_input("Title", f.get("title", ""), key="aif_title")
            f["owner"] = st.text_input("Owner", f.get("owner", ""), key="aif_owner")
        with m2:
            f["industry"] = st.text_input("Industry", f.get("industry", ""), key="aif_industry")
            f["value"] = st.text_input("Value", f.get("value", ""), key="aif_value")
        with m3:
            _src = f.get("source") or "other"
            f["source"] = st.selectbox(
                "Source", CRM_SOURCE_OPTIONS,
                index=CRM_SOURCE_OPTIONS.index(_src) if _src in CRM_SOURCE_OPTIONS else 0,
                format_func=_source_label, key="aif_source",
            )
            _deal = f.get("deal_status") or "open"
            f["deal_status"] = st.selectbox(
                "Deal state", DEAL_STATUSES,
                index=DEAL_STATUSES.index(_deal) if _deal in DEAL_STATUSES else 0,
                format_func=_deal_status_label, key="aif_deal",
            )
            follow_raw = _date_value(f.get("next_follow_up") or "")
            picked = st.date_input("Follow-up", value=follow_raw, format="YYYY-MM-DD", key="aif_follow_up")
            f["next_follow_up"] = picked.isoformat() if picked else ""

    res["fields"] = f
    state["result"] = res
    state["existing"] = f

    missing = []
    if not (f.get("company") or f.get("name")):
        missing.append("name or company")
    if not (f.get("phone") or f.get("email")):
        missing.append("phone or email")

    st.markdown('<div class="ai-save-bar">', unsafe_allow_html=True)
    if missing:
        st.markdown(
            f'<div class="missing-note"><strong>Still need</strong> '
            f'{" and ".join(missing)} before saving.</div>',
            unsafe_allow_html=True,
        )

    s1, s2, s3 = st.columns([2, 1, 1])
    with s1:
        save = st.button(
            "Save to CRM",
            type="primary",
            use_container_width=True,
            disabled=bool(missing),
        )
    with s2:
        if st.button("← Revise", use_container_width=True):
            state["phase"] = "capture"
            state["capture_text"] = ""
            state["last_error"] = ""
            state.pop("review_reveal", None)
            state.pop("_processing_visible", None)
            st.rerun()
    with s3:
        if st.button("Cancel", key="ai_review_cancel", use_container_width=True):
            _close_ai_dialog()
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    if save:
        clean_follow_up = _clean_follow_up(f.get("next_follow_up") or "")
        if clean_follow_up is None:
            st.error("Use YYYY-MM-DD for follow-up date.")
            return
        f["next_follow_up"] = clean_follow_up
        contact = _ai_fields_to_contact(f)
        action, saved = _upsert_contact(contact)
        ok = persist_crm(f"CRM: {action} {display_name(saved)} (AI intake)")
        label = display_name(saved)
        _close_ai_dialog()
        if ok:
            st.session_state.crm_save_toast = f"{'Updated' if action == 'updated' else 'Added'} {label}"
        st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)


def _render_ai_captured_summary(fields: dict) -> None:
    labels = {
        "company": "Company",
        "name": "Contact",
        "phone": "Phone",
        "email": "Email",
        "title": "Title",
        "industry": "Industry",
        "owner": "Owner",
        "client": "Client",
        "value": "Value",
        "source": "Source",
        "status": "Stage",
        "deal_status": "Deal",
        "next_follow_up": "Follow-up",
    }
    chips = []
    for key, label in labels.items():
        val = (fields.get(key) or "").strip()
        if not val:
            continue
        if key == "source":
            val = _source_label(val)
        elif key == "status":
            val = _status_label(val)
        elif key == "deal_status":
            val = _deal_status_label(val)
        chips.append(f'<span class="chip"><b>{html.escape(label)}:</b> {html.escape(val)}</span>')
    if not chips:
        return
    st.markdown(
        '<div class="ai-captured"><b>Already captured</b> '
        + " ".join(chips)
        + "</div>",
        unsafe_allow_html=True,
    )


def _render_ai_progress(fields: dict) -> None:
    from agent.crm_intake_agent import intake_completeness

    filled, total, gaps = intake_completeness(fields)
    pct = int(round((filled / total) * 100)) if total else 0
    gap_text = "Ready to save" if not gaps else "Still need " + " and ".join(gaps)
    st.markdown(
        f'<div class="ai-progress">'
        f'<div class="bar"><div class="fill" style="width:{pct}%"></div></div>'
        f'<div class="meta"><span>{filled} of {total} fields filled</span>'
        f'<span>{html.escape(gap_text)}</span></div></div>',
        unsafe_allow_html=True,
    )


def _ai_fields_to_contact(f: dict) -> dict:
    """Build a normalized CRM contact from the agent's field dict."""
    return normalize_contact(
        {
            "id": new_contact_id(),
            "name": f.get("name", ""),
            "title": f.get("title", ""),
            "phone": f.get("phone", ""),
            "email": f.get("email", ""),
            "company": f.get("company", ""),
            "industry": f.get("industry", ""),
            "client": f.get("client", ""),
            "owner": f.get("owner", ""),
            "value": f.get("value", ""),
            "status": f.get("status") or "new",
            "deal_status": f.get("deal_status") or "open",
            "notes": f.get("notes", ""),
            "next_follow_up": _clean_follow_up(f.get("next_follow_up") or "") or "",
            "source": f.get("source") or "other",
            "tags": ["ai-intake", "ground"],
        }
    )


def _render_thread_tab(contact: dict, idx: int) -> None:
    """Unified chronological thread mixing email events and comments, newest first."""
    cid = contact.get("id", f"row-{idx}")

    st.caption("Activity is searchable across the CRM. Log the decision, objection, or next step rather than every detail.")

    # Build unified thread
    email_events = [
        normalize_email_event(e)
        for e in (contact.get("email_events") or [])
        if isinstance(e, dict)
    ]
    comments = [
        normalize_comment(c)
        for c in (contact.get("comments") or [])
        if isinstance(c, dict)
    ]
    meetings = [
        normalize_comment(m)
        for m in (contact.get("meetings") or [])
        if isinstance(m, dict)
    ]

    thread: list[dict] = []
    for e in email_events:
        thread.append({**e, "_type": "email"})
    for c in comments:
        thread.append({**c, "_type": "comment"})
    for m in meetings:
        thread.append({**m, "_type": "meeting"})

    def _sort_key(item: dict) -> str:
        return item.get("sent_at") or item.get("created_at") or ""

    thread.sort(key=_sort_key, reverse=True)

    if thread:
        items = []
        for item in thread:
            if item["_type"] == "email":
                direction = item.get("direction", "sent").title()
                date_str = (item.get("sent_at") or "")[:10]
                source_str = item.get("source", "manual").title()
                meta = " / ".join(p for p in ["Email", direction, date_str, source_str] if p)
                subject = item.get("subject") or "Untitled email"
                body = item.get("summary") or item.get("body", "")
                body = f"{body[:480]}..." if len(body) > 480 else body
                items.append(
                    '<div class="crm-thread-item email">'
                    f'<div class="crm-thread-meta">{html.escape(meta)}</div>'
                    f'<div class="crm-thread-title">{html.escape(subject)}</div>'
                    f'<div class="crm-thread-body">{html.escape(body or "No summary saved.")}</div>'
                    '</div>'
                )
            elif item["_type"] == "meeting":
                date_str = (item.get("created_at") or "")[:10]
                body = item.get("body") or ""
                link = item.get("meeting_link", "")
                subject = item.get("subject") or "Google Meet"
                meta = " / ".join(p for p in ["Meeting", date_str] if p)
                link_html = ""
                if link:
                    link_html = f'<div style="margin-top:6px"><a href="{html.escape(link)}" target="_blank" rel="noreferrer" style="display:inline-flex;align-items:center;gap:6px;padding:5px 12px;border-radius:999px;border:1px solid rgba(46,139,77,.25);background:rgba(46,139,77,.08);color:var(--green);text-decoration:none;font-size:12px;font-weight:600;">▶ Join Google Meet</a></div>'
                items.append(
                    '<div class="crm-thread-item comment" style="border-left-color:rgba(46,139,77,.55);background:rgba(46,139,77,.04);">'
                    f'<div class="crm-thread-meta">{html.escape(meta)}</div>'
                    f'<div class="crm-thread-title">{html.escape(subject)}</div>'
                    f'<div class="crm-thread-body">{html.escape(body or "No meeting notes.")}</div>'
                    f'{link_html}'
                    '</div>'
                )
            else:
                author = item.get("author") or "Team"
                date_str = (item.get("created_at") or "")[:10]
                body = item.get("body") or ""
                body = f"{body[:480]}..." if len(body) > 480 else body
                kind = "WhatsApp" if (item.get("source") or "") == "whatsapp" else "Note"
                meta = " / ".join(p for p in [kind, date_str, author] if p)
                items.append(
                    '<div class="crm-thread-item comment">'
                    f'<div class="crm-thread-meta">{html.escape(meta)}</div>'
                    f'<div class="crm-thread-body">{html.escape(body or "No note text.")}</div>'
                    '</div>'
                )
        st.markdown(f'<div class="crm-thread">{"".join(items)}</div>', unsafe_allow_html=True)
    else:
        st.caption("No emails, comments, or meetings yet. Use the forms below to add the first entry.")

    note_tab, meet_tab, email_tab = st.tabs(["Add note", "Schedule Meet", "Log email"])

    with note_tab:
        with st.form(f"activity_note_{cid}", clear_on_submit=True, border=False):
            comment_body = st.text_area(
                "Note",
                placeholder="Decision, objection, update, or next step...",
                height=90,
            )
            comment_author = st.text_input("Author", placeholder="Your name or team")
            if st.form_submit_button("Add note", use_container_width=True):
                if not comment_body.strip():
                    st.error("Write a note first.")
                else:
                    new_comment = normalize_comment({"body": comment_body, "author": comment_author})
                    contacts = st.session_state.crm_db.get("contacts", [])
                    updated = normalize_contact(
                        {
                            **contact,
                            "comments": list(contact.get("comments") or []) + [new_comment],
                            "updated_at": utc_now_iso(),
                        }
                    )
                    contacts[idx] = updated
                    st.session_state.crm_db["contacts"] = contacts
                    if persist_crm(f"CRM: note on {display_name(updated)}"):
                        st.toast("Note added")
                        st.rerun()

    with meet_tab:
        from agent.crm_meet_agent import (
            build_google_calendar_url,
            format_meet_chat_script,
            generate_meet_chat_prompts,
        )

        st.markdown(
            '<div class="crm-meet-shell">'
            '<div class="meet-head">'
            '<div class="meet-icon">▶</div>'
            '<div>'
            '<p class="meet-title">Google Meet + Calendar</p>'
            '<p class="meet-sub">Generate a Meet link, add to Calendar, and get conversational chat prompts.</p>'
            '</div></div></div>',
            unsafe_allow_html=True,
        )

        meet_link = st.session_state.get(f"_meet_link_{cid}", "")
        chat_key = f"_meet_chat_{cid}"
        with st.form(f"activity_meet_{cid}", clear_on_submit=True, border=False):
            meet_col1, meet_col2 = st.columns([1, 1])
            with meet_col1:
                meet_date = st.date_input("Meeting date", value=date.today(), format="YYYY-MM-DD")
                meet_time = st.time_input("Time", value=datetime.now().replace(hour=10, minute=0).time())
            with meet_col2:
                meet_subject = st.text_input("Meeting title", placeholder="Strategy review / Demo / Follow-up")
                meet_notes = st.text_area(
                    "Conversation notes",
                    placeholder="What was discussed? Objections, decisions, next steps...",
                    height=100,
                )
            gen_link_col, prep_col = st.columns([1, 1])
            with gen_link_col:
                generate = st.form_submit_button("Generate Meet link", use_container_width=True)
            with prep_col:
                prep_chat = st.form_submit_button("Draft Meet chat →", use_container_width=True)

            if meet_link:
                cal_url = build_google_calendar_url(
                    title=meet_subject or f"Follow-up — {display_name(contact)}",
                    start_date=meet_date.isoformat(),
                    start_time=meet_time.strftime("%H:%M"),
                    meet_link=meet_link,
                    details=meet_notes or contact.get("notes") or "",
                )
                st.markdown(
                    '<div class="crm-meet-schedule-label">Quick links</div>'
                    f'<div class="crm-meet-actions">'
                    f'<a class="meet" href="{html.escape(meet_link)}" target="_blank" rel="noreferrer">Join Meet</a>'
                    f'<a class="cal" href="{html.escape(cal_url)}" target="_blank" rel="noreferrer">Add to Google Calendar</a>'
                    f'</div>'
                    '<div class="crm-meet-schedule-spacer"></div>'
                    '<div class="crm-meet-schedule-label">Save to CRM</div>',
                    unsafe_allow_html=True,
                )

            sched_col1, sched_col2 = st.columns([1, 1])
            with sched_col1:
                schedule = st.form_submit_button("Save & Schedule", type="primary", use_container_width=True)
            with sched_col2:
                join_now = st.form_submit_button("Open Meet now →", use_container_width=True)

        if generate:
            link = generate_meet_link()
            st.session_state[f"_meet_link_{cid}"] = link
            st.rerun()

        if prep_chat:
            payload = generate_meet_chat_prompts(
                contact,
                meeting_subject=meet_subject,
                meeting_notes=meet_notes,
            )
            st.session_state[chat_key] = payload
            st.rerun()

        chat_payload = st.session_state.get(chat_key)
        if chat_payload:
            script = format_meet_chat_script(chat_payload)
            st.markdown(
                f'<div class="crm-meet-chat">{html.escape(script)}</div>'
                f'<p class="ai-template-hint">Paste into Google Meet chat when you join — '
                f'questions adapt to this contact&apos;s CRM context.</p>',
                unsafe_allow_html=True,
            )

        if join_now:
            link = st.session_state.get(f"_meet_link_{cid}") or generate_meet_link()
            st.session_state[f"_meet_link_{cid}"] = link
            st.markdown(
                f'<meta http-equiv="refresh" content="0; url={html.escape(link)}">',
                unsafe_allow_html=True,
            )
            st.link_button("Open Google Meet", link, use_container_width=True)

        if schedule:
            final_link = st.session_state.get(f"_meet_link_{cid}", meet_link)
            if not final_link:
                final_link = generate_meet_link()
                st.session_state[f"_meet_link_{cid}"] = final_link
            chat_payload = st.session_state.get(chat_key) or generate_meet_chat_prompts(
                contact,
                meeting_subject=meet_subject,
                meeting_notes=meet_notes,
            )
            chat_script = format_meet_chat_script(chat_payload)
            meeting_record = normalize_comment({
                "body": (meet_notes or chat_script or "Scheduled via CRM")[:1200],
                "author": "Team",
                "subject": meet_subject or chat_payload.get("calendar_summary") or f"Google Meet — {meet_date.isoformat()} {meet_time.strftime('%H:%M')}",
                "meeting_link": final_link,
                "source": "google_meet",
                "created_at": f"{meet_date.isoformat()}T{meet_time.strftime('%H:%M:%S')}",
            })
            meeting_record["meeting_link"] = final_link
            contacts = st.session_state.crm_db.get("contacts", [])
            updated = normalize_contact({
                **contact,
                "meetings": list(contact.get("meetings") or []) + [meeting_record],
                "updated_at": utc_now_iso(),
            })
            contacts[idx] = updated
            st.session_state.crm_db["contacts"] = contacts
            if persist_crm(f"CRM: schedule meet for {display_name(updated)}"):
                st.toast(f"Meeting scheduled — {final_link}")
                st.session_state.pop(f"_meet_link_{cid}", None)
                st.session_state.pop(chat_key, None)
                st.rerun()

    with email_tab:
        with st.form(f"activity_email_{cid}", clear_on_submit=True, border=False):
            mail_col1, mail_col2 = st.columns([1, 1])
            with mail_col1:
                email_date = st.date_input("Email date", value=date.today(), format="YYYY-MM-DD")
            with mail_col2:
                direction = st.selectbox("Direction", ["sent", "received"], format_func=str.title)
            subject = st.text_input("Subject", placeholder="Proposal shared / Follow-up")
            summary = st.text_area(
                "Insight summary",
                placeholder="Client asked for pricing, timeline, decision maker, objections...",
                height=72,
            )
            body = st.text_area(
                "Email body / notes",
                placeholder="Paste only the excerpts needed for future CRM context.",
                height=110,
            )
            if st.form_submit_button("Log email", use_container_width=True):
                if not subject.strip() and not summary.strip() and not body.strip():
                    st.error("Add a subject, summary, or email body first.")
                else:
                    event = normalize_email_event(
                        {
                            "direction": direction,
                            "sent_at": email_date.isoformat(),
                            "to": contact.get("email", ""),
                            "subject": subject,
                            "summary": summary,
                            "body": body,
                            "source": "manual",
                        }
                    )
                    contacts = st.session_state.crm_db.get("contacts", [])
                    updated = normalize_contact(
                        {
                            **contact,
                            "email_events": list(contact.get("email_events") or []) + [event],
                            "updated_at": utc_now_iso(),
                        }
                    )
                    contacts[idx] = updated
                    st.session_state.crm_db["contacts"] = contacts
                    if persist_crm(f"CRM: log email for {display_name(updated)}"):
                        st.toast("Email logged")
                        st.rerun()


def _render_people_tab(contact: dict, idx: int) -> None:
    """Show additional contact people and an add form."""
    cid = contact.get("id", f"row-{idx}")
    people = [
        normalize_contact_person(person)
        for person in (contact.get("contact_people") or [])
        if isinstance(person, dict)
    ]

    if people:
        for p in people:
            pid = p.get("id", "")
            role = p.get("role") or p.get("title") or "Contact"
            subtitle = " / ".join(part for part in [p.get("title"), p.get("email"), p.get("phone")] if part)
            col_info, col_del = st.columns([4, 1])
            with col_info:
                st.markdown(
                    '<div class="crm-contact-person"><div>'
                    f'<div class="name">{html.escape(p.get("name") or "Unnamed contact")}</div>'
                    f'<div class="meta">{html.escape(subtitle or "No email or phone saved")}</div>'
                    '</div>'
                    f'<span class="crm-pill other">{html.escape(role)}</span>'
                    '</div>',
                    unsafe_allow_html=True,
                )
            with col_del:
                if st.button("Remove", key=f"del_person_{cid}_{pid}", use_container_width=True, help="Remove this secondary contact"):
                    contacts = st.session_state.crm_db.get("contacts", [])
                    updated = normalize_contact(
                        {
                            **contact,
                            "contact_people": [
                                x for x in people if x.get("id") != pid
                            ],
                            "updated_at": utc_now_iso(),
                        }
                    )
                    contacts[idx] = updated
                    st.session_state.crm_db["contacts"] = contacts
                    if persist_crm(f"CRM: remove person from {display_name(updated)}"):
                        st.toast("Person removed")
                        st.rerun()
    else:
        st.caption("No additional contacts yet. Add someone below.")

    with st.form(f"add_person_{cid}", clear_on_submit=True, border=False):
        st.markdown("**Add secondary contact**")
        pa, pb = st.columns([1, 1])
        with pa:
            p_name = st.text_input("Name", placeholder="Anita Sharma")
            p_email = st.text_input("Email", placeholder="anita@company.com")
        with pb:
            p_title = st.text_input("Title", placeholder="CFO")
            p_phone = st.text_input("Phone", placeholder="+91 98xxx xxxxx")
        p_role = st.text_input("Role in deal", placeholder="Decision maker / Influencer / Finance")
        if st.form_submit_button("Add contact", use_container_width=True):
            if not p_name.strip() and not p_email.strip() and not p_phone.strip():
                st.error("Provide at least a name, email, or phone.")
            else:
                new_person = normalize_contact_person(
                    {
                        "name": p_name,
                        "title": p_title,
                        "email": p_email,
                        "phone": p_phone,
                        "role": p_role,
                    }
                )
                contacts = st.session_state.crm_db.get("contacts", [])
                updated = normalize_contact(
                    {
                        **contact,
                        "contact_people": people + [new_person],
                        "updated_at": utc_now_iso(),
                    }
                )
                contacts[idx] = updated
                st.session_state.crm_db["contacts"] = contacts
                if persist_crm(f"CRM: add person to {display_name(updated)}"):
                    st.toast("Contact added")
                    st.rerun()


def _render_lead_details(contact: dict, idx: int, statuses: list[str]) -> None:
    cid = contact.get("id", f"row-{idx}")
    name = display_name(contact)
    company = (contact.get("company") or "").strip() or "—"
    stage = normalize_status(contact.get("status") or "new")
    deal_status = normalize_deal_status(contact.get("deal_status") or "", stage=stage)
    source = normalize_source(contact.get("source") or "other")
    
    tab_thread, tab_people, tab_edit, tab_agent = st.tabs(["Activity", "Contacts", "Details", "Agent context"])

    with tab_edit:
        st.markdown('<div class="crm-edit-wrap">', unsafe_allow_html=True)

        e1, e2, e3 = st.columns(3)
        with e1:
            v_company = st.text_input("Company", contact.get("company", ""), key=f"c_{cid}")
            v_industry = st.text_input("Industry", contact.get("industry", ""), key=f"i_{cid}")
            v_owner = st.text_input("Owner", contact.get("owner", ""), key=f"o_{cid}")
        with e2:
            v_name = st.text_input("Contact name", contact.get("name", ""), key=f"n_{cid}")
            v_title = st.text_input("Contact title", contact.get("title", ""), key=f"t_{cid}")
            v_email = st.text_input("Contact email", contact.get("email", ""), key=f"e_{cid}")
            v_phone = st.text_input("Phone", contact.get("phone", ""), key=f"p_{cid}")
        with e3:
            v_source = st.selectbox(
                "Source",
                CRM_SOURCE_OPTIONS,
                index=CRM_SOURCE_OPTIONS.index(source) if source in CRM_SOURCE_OPTIONS else 0,
                format_func=_source_label,
                key=f"src_{cid}",
            )
            v_stage = st.selectbox(
                "Stage",
                CRM_STATUSES,
                index=CRM_STATUSES.index(stage) if stage in CRM_STATUSES else 0,
                format_func=_status_label,
                key=f"s_{cid}",
                on_change=_sync_stage_widget,
                args=(f"s_{cid}", f"ds_{cid}"),
            )
            v_deal_status = st.selectbox(
                "Deal state",
                DEAL_STATUSES,
                index=DEAL_STATUSES.index(deal_status) if deal_status in DEAL_STATUSES else 0,
                format_func=_deal_status_label,
                key=f"ds_{cid}",
                on_change=_sync_deal_widget,
                args=(f"s_{cid}", f"ds_{cid}"),
            )

        e4, e5, e6 = st.columns([1, 1, 1])
        with e4:
            v_value = st.text_input("Value", contact.get("value", ""), key=f"v_{cid}")
        with e5:
            v_follow = st.date_input(
                "Follow-up date",
                value=_date_value(contact.get("next_follow_up") or ""),
                format="YYYY-MM-DD",
                key=f"f_{cid}",
            )
        with e6:
            v_client = st.text_input("For client", contact.get("client", ""), key=f"cl_{cid}")

        v_notes = st.text_area("Context and next step", contact.get("notes", ""), height=96, key=f"nt_{cid}")

        b1, b2, _ = st.columns([1, 1, 2])
        with b1:
            if st.button("Save", key=f"save_{cid}", type="primary", use_container_width=True):
                clean_follow_up = _clean_follow_up(v_follow)
                if clean_follow_up is None:
                    st.error("Use YYYY-MM-DD for follow-up date.")
                else:
                    updated = normalize_contact(
                        {
                            **contact,
                            "name": v_name,
                            "phone": v_phone,
                            "email": v_email,
                            "title": v_title,
                            "company": v_company,
                            "industry": v_industry,
                            "client": v_client,
                            "owner": v_owner,
                            "value": v_value,
                            "source": v_source,
                            "status": v_stage,
                            "deal_status": v_deal_status,
                            "notes": v_notes,
                            "next_follow_up": clean_follow_up,
                            "updated_at": utc_now_iso(),
                        }
                    )
                    contacts = st.session_state.crm_db.get("contacts", [])
                    contacts[idx] = updated
                    st.session_state.crm_db["contacts"] = contacts
                    if persist_crm(f"CRM: update {display_name(updated)}"):
                        st.toast("Saved")
                        st.rerun()
        with b2:
            with st.popover("Delete lead", use_container_width=True):
                st.warning(f"Remove {name} and its activity history?")
                if st.button("Confirm delete", key=f"del_{cid}", use_container_width=True):
                    contacts = [c for c in st.session_state.crm_db.get("contacts", []) if c.get("id") != cid]
                    st.session_state.crm_db["contacts"] = contacts
                    if persist_crm(f"CRM: delete {name}"):
                        st.toast("Lead removed")
                        st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)

    with tab_thread:
        _render_thread_tab(contact, idx)

    with tab_people:
        _render_people_tab(contact, idx)

    with tab_agent:
        if contact.get("signal") or contact.get("opening_line") or contact.get("score"):
            if contact.get("score"):
                st.caption(f"Score: {contact['score']}/100")
            if contact.get("signal"):
                st.write(contact["signal"])
            if contact.get("opening_line"):
                st.info(contact["opening_line"])
            if contact.get("linkedin_url"):
                st.markdown(f"[LinkedIn]({contact['linkedin_url']})")
            if contact.get("website"):
                st.markdown(f"[Website]({contact['website']})")
            if contact.get("agent_run_id"):
                st.caption(f"Agent run: {contact['agent_run_id']}")
        else:
            st.caption("No agent data for this lead.")


def _render_lead_detail_view(contact: dict, idx: int, statuses: list[str]) -> None:
    cid = contact.get("id", f"row-{idx}")
    name = display_name(contact)
    company = (contact.get("company") or "").strip() or "—"
    stage = normalize_status(contact.get("status") or "new")
    deal_status = normalize_deal_status(contact.get("deal_status") or "", stage=stage)
    source = normalize_source(contact.get("source") or "other")
    owner = (contact.get("owner") or "").strip() or "—"
    value = _value_display(contact.get("value") or "")
    follow = (contact.get("next_follow_up") or "").strip()[:10]
    contact_line = " · ".join(
        part for part in [(contact.get("email") or "").strip(), (contact.get("phone") or "").strip()] if part
    ) or "No email or phone"

    st.markdown('<div class="crm-detail-back-row">', unsafe_allow_html=True)
    back_col, del_col, _ = st.columns([1.1, 1, 3.3])
    with back_col:
        if st.button("← Back to list", key="crm_detail_back", use_container_width=True):
            _close_lead_detail()
            st.rerun()
    with del_col:
        with st.popover("Delete lead", use_container_width=True):
            st.warning(f"Delete {name} and all its activity? This can't be undone.")
            if st.button("Yes, delete", key=f"crm_detail_del_{cid}", type="primary", use_container_width=True):
                contacts = [c for c in st.session_state.crm_db.get("contacts", []) if c.get("id") != cid]
                st.session_state.crm_db["contacts"] = contacts
                if persist_crm(f"CRM: delete {name}"):
                    _close_lead_detail()
                    st.toast("Lead removed")
                    st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    follow_suffix = f" · Next {html.escape(follow)}" if follow else ""
    subtitle = (
        f"{html.escape(name)} · {html.escape(contact_line)} · Owner {html.escape(owner)}{follow_suffix}"
    )
    badges_html = (
        f'<span class="crm-pill {html.escape(stage)}">{html.escape(_status_label(stage))}</span>'
        f'<span class="crm-pill {html.escape(deal_status)}">{html.escape(_deal_status_label(deal_status))}</span>'
        f'<span class="crm-pill">{html.escape(_source_label(source))}</span>'
        f'<span class="crm-pill">Value {html.escape(value)}</span>'
    )

    st.markdown(
        f'<div class="crm-detail-shell">'
        f'<div class="crm-detail-top"><div>'
        f'<div class="crm-detail-kicker">Lead workspace</div>'
        f'<h2 class="crm-detail-title">{html.escape(company)}</h2>'
        f'<div class="crm-detail-sub">{subtitle}</div>'
        f'<div class="crm-detail-badges">{badges_html}</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="crm-detail-panel">', unsafe_allow_html=True)
    _render_lead_details(contact, idx, statuses)
    st.markdown("</div></div>", unsafe_allow_html=True)


def _render_contact_card(
    contact: dict,
    idx: int,
    statuses: list[str],
    *,
    select_mode: bool = False,
    is_selected: bool = False,
) -> None:
    cid = contact.get("id", f"row-{idx}")
    safe_id = _safe_widget_key(cid)
    cid_str = str(cid)
    name = display_name(contact)
    stage = normalize_status(contact.get("status") or "new")
    stage_label = _status_label(stage)
    deal_status = normalize_deal_status(contact.get("deal_status") or "", stage=stage)
    deal_label = _deal_status_label(deal_status)
    is_due = _is_due(contact) and deal_status == "open"
    due_html = '<span class="crm-pill due">Due</span>' if is_due else ""

    company = (contact.get("company") or "").strip() or "—"

    card_cls = "crm-lead-card"
    if is_due:
        card_cls += " crm-due"
    if select_mode:
        card_cls += " crm-selectable"
        if is_selected:
            card_cls += " crm-selected"

    monogram_src = (contact.get("company") or "").strip() or name
    words = [w for w in monogram_src.replace("—", " ").split() if w[:1].isalnum()]
    initials = "".join(w[0] for w in words[:2]).upper() or "•"

    industry = (contact.get("industry") or "").strip()
    source = normalize_source(contact.get("source") or "other")
    company_sub = industry or _source_label(source)
    title = (contact.get("title") or "").strip()
    owner = (contact.get("owner") or "").strip()
    name_sub = title or (f"Owner · {owner}" if owner else "")
    money = _fmt_money(contact.get("value") or "")
    follow = (contact.get("next_follow_up") or "").strip()[:10]
    if money:
        meta = money
    elif follow:
        meta = f"Follow-up {follow}"
    else:
        meta = ""

    status_html = (
        f'{due_html}'
        f'<span class="crm-pill {html.escape(stage)}">{html.escape(stage_label)}</span>'
        f'<span class="crm-pill {html.escape(deal_status)}">{html.escape(deal_label)}</span>'
    )
    co_sub_html = f'<div class="crm-lead-sub">{html.escape(company_sub)}</div>' if company_sub else ""
    name_sub_html = f'<div class="crm-lead-sub">{html.escape(name_sub)}</div>' if name_sub else ""
    meta_html = f'<div class="crm-lead-meta">{html.escape(meta)}</div>' if meta else ""
    sel_mark_html = ""
    if select_mode:
        mark = "✓" if is_selected else ""
        sel_mark_html = f'<span class="crm-sel-mark" aria-hidden="true">{mark}</span>'

    row_key = f"crm_row_{safe_id}"
    with st.container(key=row_key):
        st.markdown(
            f'<div class="crm-lead-hit">'
            f'<div class="{card_cls}">'
            f'  {sel_mark_html}'
            f'  <span class="crm-rail {html.escape(stage)}" aria-hidden="true"></span>'
            f'  <div class="crm-lead-body">'
            f'    <div class="crm-lead-co-wrap">'
            f'      <span class="crm-mono {html.escape(stage)}">{html.escape(initials)}</span>'
            f'      <div class="crm-lead-co-text">'
            f'        <div class="crm-lead-co">{html.escape(company)}</div>'
            f'        {co_sub_html}'
            f'      </div>'
            f'    </div>'
            f'    <div class="crm-lead-name-wrap">'
            f'      <div class="crm-lead-name">{html.escape(name)}</div>'
            f'      {name_sub_html}'
            f'    </div>'
            f'    <div class="crm-lead-status-wrap">'
            f'      <div class="crm-lead-status">{status_html}</div>'
            f'      {meta_html}'
            f'    </div>'
            f'  </div>'
            f'  <span class="crm-lead-chev" aria-hidden="true">›</span>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if select_mode:
            st.button(
                "Toggle select",
                key=f"crm_sel_{safe_id}",
                help=f"{'Deselect' if is_selected else 'Select'} {company}",
                use_container_width=True,
                on_click=_toggle_crm_sel,
                kwargs={"contact_id": cid_str},
            )
        else:
            st.button(
                "Open lead",
                key=f"crm_open_{safe_id}",
                help=f"Open {company}",
                use_container_width=True,
                on_click=_open_lead_detail,
                kwargs={"contact_id": cid_str},
            )


def render_crm_page() -> None:
    # --- Dialog Click-Outside / Main Page Interaction Check ---
    if st.session_state.get("crm_ai_dialog_open"):
        last_state = st.session_state.get("crm_last_main_state", {})
        interacted_with_main = False
        
        main_keys = [
            "crm_search", "crm_stage_filter", "crm_source_filter",
            "crm_deal_filter", "crm_work_filter", "crm_sort",
            "crm_page", "crm_page_size", "crm_selected_contact_id", "crm_view_mode",
        ]
        for k in main_keys:
            if k in st.session_state and last_state.get(k) != st.session_state[k]:
                interacted_with_main = True
                break
        
        if not interacted_with_main:
            for k, val in st.session_state.items():
                if any(k.startswith(prefix) for prefix in ["c_", "i_", "o_", "n_", "t_", "e_", "p_", "src_", "s_", "ds_", "v_", "f_", "cl_", "nt_"]):
                    if k in last_state and last_state[k] != val:
                        interacted_with_main = True
                        break
        
        if interacted_with_main:
            st.session_state.crm_ai_dialog_open = False

    st.session_state.setdefault("crm_view_mode", "list")
    st.session_state.setdefault("crm_selected_contact_id", None)
    st.session_state.pop("crm_expanded_contact_id", None)

    st.markdown(CRM_CSS, unsafe_allow_html=True)
    # Under auth the tenant is fixed by identity — never let users hand-switch it.
    if not auth.auth_enabled():
        tenancy.render_org_switcher()
    ensure_crm_loaded()

    db = st.session_state.crm_db
    meta = st.session_state.get("crm_meta") or {}
    contacts = list(db.get("contacts") or [])

    statuses = _available_statuses(db, contacts)
    id_to_idx = _contact_index_map(contacts)

    active = sum(1 for c in contacts if normalize_deal_status(c.get("deal_status") or "", stage=normalize_status(c.get("status") or "new")) == "open")
    due = sum(
        1
        for c in contacts
        if _is_due(c) and normalize_deal_status(c.get("deal_status") or "", stage=normalize_status(c.get("status") or "new")) == "open"
    )
    won = sum(1 for c in contacts if normalize_deal_status(c.get("deal_status") or "", stage=normalize_status(c.get("status") or "new")) == "won")
    snapshot_html = _stage_snapshot_html(statuses, contacts)
    selected_id = st.session_state.get("crm_selected_contact_id")
    detail_mode = st.session_state.get("crm_view_mode") == "detail"

    st.markdown(
        f"""
        <div class="crm-shell">
        <div class="crm-head">
          <div>
            <h2>CRM</h2>
            <p>Contacts, follow-ups, and imported lead-agent prospects in one working list.</p>
          </div>
        </div>
        <div class="crm-stats">
          <div class="crm-stat"><div class="n">{len(contacts)}</div><div class="l">Total</div></div>
          <div class="crm-stat"><div class="n">{active}</div><div class="l">Active</div></div>
          <div class="crm-stat"><div class="n">{due}</div><div class="l">Due now</div></div>
          <div class="crm-stat"><div class="n">{won}</div><div class="l">Won</div></div>
        </div>
        <div class="sec">Stage snapshot <span class="line"></span></div>
        {snapshot_html}
        </div>
        """,
        unsafe_allow_html=True,
    )

    if detail_mode and selected_id and str(selected_id) in {str(c.get("id")) for c in contacts}:
        sel_idx = id_to_idx.get(str(selected_id))
        if sel_idx is not None:
            _render_lead_detail_view(contacts[sel_idx], sel_idx, statuses)
            toast = st.session_state.pop("crm_save_toast", None)
            if toast:
                st.toast(toast)
            if st.session_state.get("crm_ai_dialog_open"):
                _ai_add_dialog()
            return
    if detail_mode:
        st.session_state.crm_view_mode = "list"
        st.session_state.crm_selected_contact_id = None

    render_usage_guide("crm")

    ai_col, hint_col = st.columns([1.1, 2])
    with ai_col:
        if st.button(
            "+ Add lead",
            type="primary", use_container_width=True, key="open_ai_add",
        ):
            _open_ai_dialog()
            st.rerun()
    with hint_col:
        st.caption("Describe a lead in one sentence — type it, or tap the box and use your keyboard's mic to dictate. The AI fills in the record and only asks for what's missing.")

    _render_quick_add()
    _render_excel_upload()

    st.markdown('<div class="sec">Find leads <span class="line"></span></div>', unsafe_allow_html=True)
    ai_hint = "AI search: try “qualified leads due this week” or “move Jewel to contacted”" if llm_configured() else ""
    st.markdown('<div class="crm-toolbar">', unsafe_allow_html=True)
    search_col, sync_col, clear_col = st.columns([5, 1, 1])
    with search_col:
        q = st.text_input(
            "Search",
            placeholder="Search name, company, notes… or ask in plain English",
            label_visibility="collapsed",
            key="crm_search",
        )
    with sync_col:
        if st.button("Sync", use_container_width=True, help="Reload from GitHub"):
            ensure_crm_loaded(force=True)
            st.rerun()
    with clear_col:
        st.button("Clear", use_container_width=True, help="Reset search, filters, and sort", on_click=_reset_crm_filters)
    if ai_hint:
        st.caption(ai_hint)

    search_spec: dict = {}
    search_results: list[dict] = []
    if q.strip():
        search_results, search_spec = search_contacts(contacts, q)
        if search_spec.get("summary"):
            st.caption(f"AI: {search_spec['summary']}")
        if search_spec.get("mode") == "status_update" and search_results:
            st.markdown('<div class="crm-quick-status">', unsafe_allow_html=True)
            pick = search_results[0] if len(search_results) == 1 else None
            if len(search_results) > 1:
                pick_id = st.selectbox(
                    "Which lead?",
                    [str(c.get("id")) for c in search_results],
                    format_func=lambda cid: display_name(next(c for c in search_results if str(c.get("id")) == cid)),
                    key="crm_quick_status_pick",
                )
                pick = next(c for c in search_results if str(c.get("id")) == pick_id)
            if pick:
                cur = normalize_status(pick.get("status") or "new")
                nxt = resolve_status_update(pick, search_spec) or next_pipeline_status(cur) or "contacted"
                st.caption(
                    f"**{display_name(pick)}** is **{_status_label(cur)}** → "
                    f"advance to **{_status_label(nxt)}**?"
                )
                qs_col1, qs_col2, qs_col3 = st.columns([1.2, 1.2, 2])
                with qs_col1:
                    if st.button("Advance status", key="crm_quick_status_go", type="primary", use_container_width=True):
                        _apply_status_to_contact(str(pick.get("id")), nxt)
                        st.rerun()
                with qs_col2:
                    manual_stage = st.selectbox(
                        "Or pick stage",
                        CRM_STATUSES,
                        index=CRM_STATUSES.index(cur) if cur in CRM_STATUSES else 0,
                        format_func=_status_label,
                        key="crm_quick_status_manual",
                        label_visibility="collapsed",
                    )
                    if st.button("Set stage", key="crm_quick_status_set", use_container_width=True):
                        _apply_status_to_contact(str(pick.get("id")), manual_stage)
                        st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

    f2, f3, f4, f5, f6 = st.columns([1, 1, 1, 1, 1])
    with f2:
        status_filter = st.selectbox(
            "Stage",
            ["all"] + statuses,
            format_func=lambda s: "All stages" if s == "all" else _status_label(s),
            label_visibility="collapsed",
            key="crm_stage_filter",
        )
    with f3:
        source_filter = st.selectbox(
            "Source",
            ["all"] + CRM_SOURCE_OPTIONS,
            format_func=lambda s: "All sources" if s == "all" else _source_label(s),
            label_visibility="collapsed",
            key="crm_source_filter",
        )
    with f4:
        deal_status_filter = st.selectbox(
            "Deal state",
            ["all"] + DEAL_STATUSES,
            format_func=lambda s: "All states" if s == "all" else _deal_status_label(s),
            label_visibility="collapsed",
            key="crm_deal_filter",
        )
    with f5:
        work_filter = st.selectbox(
            "Follow-up",
            ["all", "due", "week", "none"],
            format_func=lambda s: {
                "all": "Any date",
                "due": "Due now",
                "week": "Next 7 days",
                "none": "No follow-up",
            }[s],
            label_visibility="collapsed",
            key="crm_work_filter",
        )
    with f6:
        sort_by = st.selectbox(
            "Sort",
            ["recent", "follow_up", "name"],
            format_func=lambda s: {
                "recent": "Recent",
                "follow_up": "Follow-up",
                "name": "Name",
            }[s],
            label_visibility="collapsed",
            key="crm_sort",
        )
    st.markdown('</div>', unsafe_allow_html=True)

    filtered = contacts
    if q.strip():
        filtered = list(search_results)
    if status_filter != "all":
        filtered = [
            c for c in filtered
            if normalize_status(c.get("status") or "new") == status_filter
        ]
    if source_filter != "all":
        filtered = [c for c in filtered if _contact_source(c) == source_filter]
    if deal_status_filter != "all":
        filtered = [
            c for c in filtered
            if normalize_deal_status(c.get("deal_status") or "", stage=normalize_status(c.get("status") or "new")) == deal_status_filter
        ]
    if work_filter != "all":
        filtered = [c for c in filtered if _follow_up_bucket(c) == work_filter]

    if sort_by == "follow_up":
        filtered = sorted(
            filtered,
            key=lambda c: (
                (c.get("next_follow_up") or "9999-99-99")[:10],
                display_name(c).lower(),
            ),
        )
    elif sort_by == "name":
        filtered = sorted(filtered, key=lambda c: display_name(c).lower())
    else:
        filtered = sorted(filtered, key=lambda c: c.get("updated_at", ""), reverse=True)

    st.markdown('<div class="sec">Your list <span class="line"></span></div>', unsafe_allow_html=True)

    if not filtered:
        empty_msg = (
            "No contacts yet.<br>Add someone above, or import from a Lead Agent run."
            if not contacts else "No leads match this view. Clear the filters to return to the full list."
        )
        st.markdown(
            f'<div class="crm-empty">{empty_msg}</div>',
            unsafe_allow_html=True,
        )
        return

    # ── Pagination — never render thousands of cards at once ──────────────────
    total = len(filtered)
    page_size = st.session_state.get("crm_page_size", 25)
    page_count = max(1, (total + page_size - 1) // page_size)
    page = min(max(1, st.session_state.get("crm_page", 1)), page_count)
    start = (page - 1) * page_size
    page_slice = filtered[start:start + page_size]
    end = start + len(page_slice)
    filtered_ids = [str(c.get("id")) for c in filtered if c.get("id")]
    page_ids = [str(c.get("id")) for c in page_slice if c.get("id")]
    select_mode = bool(st.session_state.get("crm_select_mode"))
    sel_ids: set = set(st.session_state.get("crm_sel_ids") or set())

    _render_selection_toolbar(filtered_ids=filtered_ids, page_ids=page_ids)

    st.markdown(
        f'<div class="crm-filter-summary">Showing <strong>{start + 1 if total else 0}–{end}</strong> of '
        f'<strong>{total}</strong> match{"es" if total != 1 else ""} '
        f'(<strong>{len(contacts)}</strong> total).</div>',
        unsafe_allow_html=True,
    )

    if page_count > 1:
        pv, pn, ps = st.columns([1, 1, 1.4])
        with pv:
            st.button(
                "‹ Prev", use_container_width=True, disabled=page <= 1,
                key="crm_prev", on_click=lambda: st.session_state.update(crm_page=page - 1),
            )
        with pn:
            st.button(
                "Next ›", use_container_width=True, disabled=page >= page_count,
                key="crm_next", on_click=lambda: st.session_state.update(crm_page=page + 1),
            )
        with ps:
            st.selectbox(
                "Per page", [25, 50, 100], key="crm_page_size",
                label_visibility="collapsed",
                on_change=lambda: st.session_state.update(crm_page=1),
            )
        st.caption(f"Page {page} of {page_count}")

    st.markdown(
        '<div class="crm-ledger-head">'
        '<span>Company <span class="line"></span></span>'
        '<span>Contact <span class="line"></span></span>'
        '<span>Status <span class="line"></span></span>'
        '</div>',
        unsafe_allow_html=True,
    )

    st.caption(
        "Tap any lead to open its workspace. Select leads for bulk stage updates, email/WhatsApp broadcast, or delete."
        if not select_mode
        else "Tap leads to toggle selection — use the toolbar for stage updates and broadcasts."
    )

    for contact in page_slice:
        idx = id_to_idx.get(str(contact.get("id")))
        if idx is not None:
            cid = str(contact.get("id"))
            _render_contact_card(
                contact,
                idx,
                statuses,
                select_mode=select_mode,
                is_selected=cid in sel_ids,
            )

    toast = st.session_state.pop("crm_save_toast", None)
    if toast:
        st.toast(toast)

    # Save main page state at the end of the page render to detect changes in the next run
    last_state = {}
    for k, val in st.session_state.items():
        if k in ("crm_ai_dialog_open", "crm_last_main_state", "ai_text", "ai_intake") or k.startswith("aif_"):
            continue
        if isinstance(val, (str, int, float, bool, list, dict, date)) or val is None:
            last_state[k] = val
    st.session_state.crm_last_main_state = last_state

    if st.session_state.get("crm_ai_dialog_open"):
        _ai_add_dialog()


def add_leads_to_crm(leads: list[dict], *, client: str = "") -> dict[str, int]:
    ensure_crm_loaded(force=True)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    prepared = []
    for lead in leads:
        row = dict(lead)
        if client and not row.get("client"):
            row["client"] = client
        prepared.append(row)
    db, stats = import_leads_to_crm(st.session_state.crm_db, prepared, agent_run_id=run_id)
    st.session_state.crm_db = db
    persist_crm(f"CRM: import {stats.get('added', 0)} from agent")
    return stats
