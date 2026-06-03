"""FocusChain CRM — simple contact book backed by GitHub."""

from __future__ import annotations

import html
from datetime import date, datetime

import streamlit as st

from utils.crm_models import (
    CRM_SOURCE_OPTIONS,
    CRM_STATUSES,
    DEAL_STATUS_LABELS,
    DEAL_STATUSES,
    SOURCE_LABELS,
    STATUS_LABELS,
    contact_fingerprint,
    display_name,
    merge_contacts,
    new_contact_id,
    normalize_contact,
    normalize_deal_status,
    normalize_source,
    normalize_status,
    utc_now_iso,
)
from utils.crm_store import github_configured, import_leads_to_crm, load_crm, save_crm


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

/* Ledger header (table-like) */
.crm-ledger-head {
    display: grid;
    grid-template-columns: 92px minmax(0, 1.35fr) minmax(0, 1.45fr) minmax(0, .9fr) minmax(0, .9fr) minmax(0, 1fr);
    gap: 12px;
    padding: 10px 14px;
    border: 1px solid var(--line-soft);
    border-radius: var(--rs);
    background: rgba(255,255,255,.55);
    color: var(--ink-mute);
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    letter-spacing: .18em;
    text-transform: uppercase;
}
.crm-ledger-head span { display: inline-flex; align-items: center; gap: 8px; }
.crm-ledger-head .line {
    height: 1px;
    flex: 1;
    background: linear-gradient(90deg, rgba(15,42,51,.12), transparent);
}

/* Contact row (book-in-table feel) */
.crm-row {
    border: 1px solid var(--line-soft);
    border-radius: var(--r);
    background: rgba(255,255,255,.65);
    padding: 12px 14px;
    display: grid;
    grid-template-columns: 92px minmax(0, 1.35fr) minmax(0, 1.45fr) minmax(0, .9fr) minmax(0, .9fr) minmax(0, 1fr);
    gap: 12px;
    align-items: center;
    transition: border-color .18s ease, box-shadow .18s ease, transform .18s ease, background .18s ease;
    box-shadow: 0 10px 24px rgba(15,42,51,.06);
}
.crm-row:hover {
    background: #fff;
    border-color: rgba(46,139,77,.28);
    transform: translateY(-1px);
    box-shadow: 0 14px 32px rgba(15,42,51,.10);
}
.crm-row.crm-due {
    border-color: rgba(183,121,31,.24);
    box-shadow: 0 12px 28px rgba(183,121,31,.08);
}
.crm-row.crm-due:hover {
    border-color: rgba(183,121,31,.36);
    box-shadow: 0 16px 34px rgba(183,121,31,.12);
}
.crm-row.crm-due .crm-book::before { background: rgba(183,121,31,.42); }
.crm-book {
    width: 34px;
    height: 26px;
    border-radius: 7px;
    position: relative;
    background: rgba(15,42,51,.06);
    border: 1px solid rgba(15,42,51,.08);
    box-shadow: inset 0 1px 0 rgba(255,255,255,.7);
}
.crm-book::before {
    content: "";
    position: absolute;
    left: 5px;
    top: 4px;
    bottom: 4px;
    width: 6px;
    border-radius: 5px;
    background: rgba(15,42,51,.18);
}
.crm-book::after {
    content: "";
    position: absolute;
    left: 13px;
    top: 6px;
    right: 6px;
    height: 1px;
    background: rgba(15,42,51,.12);
    box-shadow: 0 5px 0 rgba(15,42,51,.10), 0 10px 0 rgba(15,42,51,.08);
    opacity: .9;
}
.crm-book.new { background: rgba(46,139,77,.14); border-color: rgba(46,139,77,.18); }
.crm-book.contacted { background: rgba(59,130,246,.12); border-color: rgba(59,130,246,.18); }
.crm-book.qualified { background: rgba(168,85,247,.12); border-color: rgba(168,85,247,.20); }
.crm-book.meeting { background: rgba(59,130,246,.12); border-color: rgba(59,130,246,.20); }
.crm-book.proposal { background: rgba(183,121,31,.12); border-color: rgba(183,121,31,.24); }
.crm-book.nurture { background: rgba(15,42,51,.06); border-color: rgba(15,42,51,.12); }
.crm-book.won { background: rgba(46,139,77,.18); border-color: rgba(46,139,77,.22); }
.crm-book.lost { background: rgba(169,61,61,.12); border-color: rgba(169,61,61,.20); }

.crm-row-main { min-width: 0; }
.crm-row-name {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 16px;
    font-weight: 800;
    color: var(--ink);
    line-height: 1.15;
    display: flex;
    gap: 8px;
    align-items: baseline;
    flex-wrap: wrap;
}
.crm-row-title {
    font-size: 12px;
    color: var(--ink-mute);
    font-weight: 650;
}
.crm-row-sub {
    font-size: 12.5px;
    color: var(--ink-mute);
    margin-top: 4px;
    line-height: 1.4;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.crm-row-k {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    letter-spacing: .12em;
    text-transform: uppercase;
    color: var(--ink-mute);
    margin-bottom: 2px;
}
.crm-row-v {
    font-size: 13px;
    color: var(--ink);
    font-weight: 650;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.crm-row-v.mute { color: var(--ink-mute); font-weight: 600; }
.crm-row-meta { justify-self: end; width: 100%; min-width: 0; }
.crm-row-meta-top { display: flex; align-items: center; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }
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
.crm-pill.won { background: rgba(46,139,77,.18); color: #166534; }
.crm-pill.lost { background: rgba(169,61,61,.12); color: var(--red); }
.crm-pill.due { background: rgba(183,121,31,.12); color: var(--amber); }
.crm-pill.open { background: rgba(59,130,246,.10); color: #1D4ED8; }
.crm-stage-snap {
    margin: 10px 0 2px;
}
.crm-snapshot-card {
    grid-column: 1 / -1;
    background:
      linear-gradient(135deg, rgba(255,255,255,.78), rgba(255,255,255,.46)),
      radial-gradient(90% 140% at 100% 0%, rgba(46,139,77,.12), transparent 48%);
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
    margin-bottom: 13px;
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
    background: rgba(255,255,255,.58);
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
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 10px;
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
    background: rgba(255,255,255,.62);
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
    gap: 10px;
    min-height: 94px;
    position: relative;
    overflow: hidden;
}
.crm-stage::before {
    content: "";
    position: absolute;
    inset: 0 auto 0 0;
    width: 3px;
    background: rgba(15,42,51,.16);
}
.crm-stage.open::before { background: var(--green); }
.crm-stage.close::before { background: var(--ink-mute); }
.crm-stage.win::before { background: var(--green-br); }
.crm-stage.loss::before { background: var(--red); }
.crm-stage .crm-stage-row {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    align-items: flex-start;
}
.crm-stage .n {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 24px; font-weight: 850; color: var(--ink); line-height: 1;
}
.crm-stage .pct {
    color: var(--ink-mute);
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: .04em;
    padding-top: 3px;
}
.crm-stage .l { display: inline-flex; align-items: center; gap: 8px; min-width: 0; }
.crm-stage-bar {
    height: 6px;
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
    .crm-stage-snap { grid-template-columns: 1fr; }
    .crm-stage-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .crm-snapshot-totals { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .crm-stat { padding: 13px 12px; }
    .crm-ledger-head { display: none; }
    .crm-row { grid-template-columns: 1fr; padding: 12px; }
    .crm-row-sub { white-space: normal; }
    .crm-row-meta { justify-self: start; width: auto; }
    .crm-row-meta-top { justify-content: flex-start; }
    .crm-actions { justify-content: flex-start; }
    [data-testid="stHorizontalBlock"] {
        display: flex !important;
        flex-direction: column !important;
        gap: 10px !important;
    }
    [data-testid="stHorizontalBlock"] > [data-testid="column"] {
        width: 100% !important;
        flex: 1 1 auto !important;
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
}
</style>
"""


def ensure_crm_loaded(*, force: bool = False) -> None:
    if force or "crm_db" not in st.session_state:
        db, meta = load_crm()
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
    result = save_crm(db, sha=st.session_state.get("crm_sha"), message=message)
    st.session_state.crm_meta = result
    if result.get("committed") or result.get("source") == "local":
        st.session_state.crm_sha = result.get("sha")
        return True
    if result.get("conflict"):
        st.warning("Someone else updated the CRM — click Sync, then try again.")
        return False
    if result.get("error"):
        st.error(result.get("error"))
        return False
    st.session_state.crm_sha = result.get("sha")
    return True


def _sync_badge(meta: dict) -> str:
    if github_configured() and meta.get("source") == "github" and not meta.get("error"):
        return (
            '<span class="crm-sync ok"><span class="dot"></span>'
            'Saved in GitHub · loads on every visit</span>'
        )
    return (
        '<span class="crm-sync warn"><span class="dot"></span>'
        'Add GITHUB_TOKEN in Secrets to persist on Cloud</span>'
    )


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
        if _is_due(c) and normalize_status(c.get("status") or "new") not in {"won", "lost"}
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
        cards.append(
            f'<div class="crm-stage {tone}">'
            '<div class="crm-stage-row">'
            f'<div class="n">{count}</div>'
            f'<div class="pct">{pct}%</div>'
            '</div>'
            f'<div class="l"><span class="crm-pill {html.escape(s)}">{html.escape(label)}</span></div>'
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

    empty_hint = (
        "Add contacts or import a lead-agent run to see stage counts here."
        if not contacts else
        "Counts update as contacts move through each stage."
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
    st.markdown(
        '<div class="crm-add-box">'
        '<div class="label">Add lead</div>'
        '<div class="hint">Track company, contact, source, stage, owner, value, and overall status.</div>'
        '</div>',
        unsafe_allow_html=True,
    )
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
            source = st.selectbox("Source", CRM_SOURCE_OPTIONS, format_func=_source_label)
        with c8:
            stage = st.selectbox("Stage", CRM_STATUSES, format_func=_status_label)
        with c9:
            deal_status = st.selectbox("Status", DEAL_STATUSES, format_func=_deal_status_label)
        with c10:
            value = st.text_input("Value", placeholder="₹1,00,000")

        c11, c12 = st.columns([1, 2])
        with c11:
            follow_up = st.text_input("Follow-up date", placeholder="YYYY-MM-DD")
        with c12:
            client = st.text_input("For client", placeholder="SN Realtors")

        notes = st.text_area("Quick note", placeholder="Context, requirements, or next step...")
        if st.form_submit_button("Save lead", type="primary", use_container_width=True):
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
                    st.toast(f"{'Updated' if action == 'updated' else 'Saved'} {display_name(saved)}")
                    st.rerun()


def _email_events_html(contact: dict) -> str:
    events = [
        normalize_email_event(e)
        for e in (contact.get("email_events") or [])
        if isinstance(e, dict)
    ]
    if not events:
        return '<div class="crm-stage-note">No emails logged yet. Add sent-email notes below to make this lead LLM-ready.</div>'

    events = sorted(events, key=lambda e: e.get("sent_at", ""), reverse=True)[:5]
    items = []
    for event in events:
        meta = " · ".join(
            part for part in [
                event.get("direction", "sent").title(),
                event.get("sent_at", "")[:10],
                event.get("source", "manual").title(),
            ] if part
        )
        subject = event.get("subject") or "Untitled email"
        summary = event.get("summary") or event.get("body", "")[:220]
        items.append(
            '<div class="crm-email-item">'
            f'<div class="meta">{html.escape(meta)}</div>'
            f'<div class="subject">{html.escape(subject)}</div>'
            f'<div class="summary">{html.escape(summary)}</div>'
            '</div>'
        )
    return '<div class="crm-email-list">' + "".join(items) + '</div>'


def _render_email_insights(contact: dict, idx: int) -> None:
    cid = contact.get("id", f"row-{idx}")
    st.markdown(
        '<div class="crm-email-insights">'
        '<div class="title">Email insights</div>'
        '<div class="hint">Free path: log sent emails here manually, or later import Gmail/Outlook exports. '
        'They are stored as structured <code>email_events</code> under the lead so chat can summarize objections, intent, and next steps.</div>'
        f'{_email_events_html(contact)}'
        '</div>',
        unsafe_allow_html=True,
    )

    with st.expander("Log sent email / client reply", expanded=False):
        c1, c2 = st.columns([1, 1])
        with c1:
            email_date = st.date_input("Email date", value=date.today(), format="YYYY-MM-DD", key=f"mail_date_{cid}")
        with c2:
            direction = st.selectbox("Direction", ["sent", "received"], format_func=str.title, key=f"mail_dir_{cid}")
        subject = st.text_input("Subject", placeholder="Proposal shared / Follow-up", key=f"mail_sub_{cid}")
        summary = st.text_area(
            "Insight summary",
            placeholder="Client asked for pricing, timeline, decision maker, objections...",
            height=72,
            key=f"mail_sum_{cid}",
        )
        body = st.text_area(
            "Email body / notes",
            placeholder="Paste the sent email or important excerpts. Avoid sensitive data you do not need for CRM insights.",
            height=110,
            key=f"mail_body_{cid}",
        )
        if st.button("Add email insight", key=f"mail_add_{cid}", use_container_width=True):
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
                    st.toast("Email insight added")
                    st.rerun()


def _render_contact_card(contact: dict, idx: int, statuses: list[str]) -> None:
    cid = contact.get("id", f"row-{idx}")
    lead_id = str(cid)[:8]
    name = display_name(contact)
    stage = normalize_status(contact.get("status") or "new")
    stage_label = _status_label(stage)
    deal_status = normalize_deal_status(contact.get("deal_status") or "", stage=stage)
    deal_label = _deal_status_label(deal_status)
    source = normalize_source(contact.get("source") or "other")
    source_disp = _source_label(source)
    title = (contact.get("title") or "").strip()
    is_due = _is_due(contact) and deal_status == "open"
    due_html = '<span class="crm-pill due">Due</span>' if is_due else ""
    title_html = f'<span class="crm-row-title">{html.escape(title)}</span>' if title else ""

    company = (contact.get("company") or "").strip() or "—"
    industry = (contact.get("industry") or "").strip()
    industry_html = f'<div class="crm-row-v mute">{html.escape(industry)}</div>' if industry else ""
    email = (contact.get("email") or "").strip() or "—"
    owner = (contact.get("owner") or "").strip() or "—"
    value = _value_display(contact.get("value") or "")
    client = (contact.get("client") or "").strip()
    client_html = f'<div class="crm-row-sub">{html.escape(client)}</div>' if client else ""
    follow = (contact.get("next_follow_up") or "").strip()[:10]
    follow_html = f'<div class="crm-row-sub">Next: {html.escape(follow)}</div>' if follow else ""
    row_cls = "crm-row crm-due" if is_due else "crm-row"

    st.markdown(
        f'<div class="{row_cls}">'
        f'<div>'
        f'  <div class="crm-row-k">Lead ID</div>'
        f'  <div class="crm-row-v">{html.escape(lead_id)}</div>'
        f'</div>'
        f'<div>'
        f'  <div class="crm-row-k">Company</div>'
        f'  <div class="crm-row-v">{html.escape(company)}</div>'
        f'  {industry_html}'
        f'</div>'
        f'<div class="crm-row-main">'
        f'  <div class="crm-row-k">Contact</div>'
        f'  <div class="crm-row-name">{html.escape(name)}{title_html}</div>'
        f'  <div class="crm-row-sub">{html.escape(email)}</div>'
        f'  {client_html}'
        f'</div>'
        f'<div>'
        f'  <div class="crm-row-k">Source</div>'
        f'  <div class="crm-row-v">{html.escape(source_disp)}</div>'
        f'  {follow_html}'
        f'</div>'
        f'<div>'
        f'  <div class="crm-row-k">Stage</div>'
        f'  <span class="crm-pill {html.escape(stage)}">{html.escape(stage_label)}</span>'
        f'</div>'
        f'<div class="crm-row-meta">'
        f'  <div class="crm-row-meta-top">'
        f'    {due_html}'
        f'    <span class="crm-pill {html.escape(deal_status)}">{html.escape(deal_label)}</span>'
        f'  </div>'
        f'  <div class="crm-row-sub">Owner: {html.escape(owner)} · Value: {html.escape(value)}</div>'
        f'  {_contact_actions(contact)}'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    with st.expander(f"Open {name}", expanded=False):
        st.markdown('<div class="crm-edit-wrap">', unsafe_allow_html=True)

        e1, e2, e3 = st.columns(3)
        with e1:
            v_company = st.text_input("Company", contact.get("company", ""), key=f"c_{cid}")
            v_industry = st.text_input("Industry", contact.get("industry", ""), key=f"i_{cid}")
            v_owner = st.text_input("Owner", contact.get("owner", ""), key=f"o_{cid}")
        with e2:
            v_name = st.text_input("Contact name", contact.get("name", ""), key=f"n_{cid}")
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
            )
            v_deal_status = st.selectbox(
                "Status",
                DEAL_STATUSES,
                index=DEAL_STATUSES.index(deal_status) if deal_status in DEAL_STATUSES else 0,
                format_func=_deal_status_label,
                key=f"ds_{cid}",
            )

        e4, e5, e6 = st.columns([1, 1, 1])
        with e4:
            v_value = st.text_input("Value", contact.get("value", ""), key=f"v_{cid}")
        with e5:
            v_follow = st.text_input(
                "Follow up on (YYYY-MM-DD)",
                (contact.get("next_follow_up") or "")[:10],
                key=f"f_{cid}",
            )
        with e6:
            v_client = st.text_input("For client", contact.get("client", ""), key=f"cl_{cid}")

        v_notes = st.text_area("Notes", contact.get("notes", ""), height=96, key=f"nt_{cid}")

        # Agent extras — only if present, tucked away
        if contact.get("signal") or contact.get("opening_line") or contact.get("score"):
            with st.expander("From agent run (read-only)", expanded=False):
                if contact.get("score"):
                    st.caption(f"Score: {contact['score']}/100")
                if contact.get("signal"):
                    st.write(contact["signal"])
                if contact.get("opening_line"):
                    st.info(contact["opening_line"])

        _render_email_insights(contact, idx)

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
            if st.button("Delete", key=f"del_{cid}", use_container_width=True):
                contacts = [c for c in st.session_state.crm_db.get("contacts", []) if c.get("id") != cid]
                st.session_state.crm_db["contacts"] = contacts
                if persist_crm(f"CRM: delete {name}"):
                    st.toast("Removed")
                    st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)


def render_crm_page() -> None:
    st.markdown(CRM_CSS, unsafe_allow_html=True)
    ensure_crm_loaded(force=True)  # always fresh from GitHub on CRM tab open

    db = st.session_state.crm_db
    meta = st.session_state.get("crm_meta") or {}
    contacts = list(db.get("contacts") or [])

    statuses = _available_statuses(db, contacts)

    active = sum(1 for c in contacts if normalize_deal_status(c.get("deal_status") or "", stage=normalize_status(c.get("status") or "new")) == "open")
    due = sum(
        1
        for c in contacts
        if _is_due(c) and normalize_deal_status(c.get("deal_status") or "", stage=normalize_status(c.get("status") or "new")) == "open"
    )
    won = sum(1 for c in contacts if normalize_deal_status(c.get("deal_status") or "", stage=normalize_status(c.get("status") or "new")) == "won")
    setup_hint_html = "" if github_configured() else _github_setup_hint_html()
    snapshot_html = _stage_snapshot_html(statuses, contacts)

    st.markdown(
        f"""
        <div class="crm-shell">
        <div class="crm-head">
          <div>
            <h2>CRM</h2>
            <p>Contacts, follow-ups, and imported lead-agent prospects in one working list.</p>
          </div>
          {_sync_badge(meta)}
        </div>
        {setup_hint_html}
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

    _render_pipeline_stage_controls(statuses)
    _render_quick_add()

    f1, f2, f3, f4, f5, f6 = st.columns([1.8, 1, 1, 1, 1, 0.7])
    with f1:
        q = st.text_input("Search", placeholder="Lead ID, company, contact, owner...", label_visibility="collapsed")
    with f2:
        status_filter = st.selectbox(
            "Stage",
            ["all"] + statuses,
            format_func=lambda s: "All" if s == "all" else _status_label(s),
            label_visibility="collapsed",
        )
    with f3:
        source_filter = st.selectbox(
            "Source",
            ["all"] + CRM_SOURCE_OPTIONS,
            format_func=lambda s: "All sources" if s == "all" else _source_label(s),
            label_visibility="collapsed",
        )
    with f4:
        deal_status_filter = st.selectbox(
            "Status",
            ["all"] + DEAL_STATUSES,
            format_func=lambda s: "All statuses" if s == "all" else _deal_status_label(s),
            label_visibility="collapsed",
        )
    with f5:
        sort_by = st.selectbox(
            "Sort",
            ["recent", "follow_up", "name"],
            format_func=lambda s: {
                "recent": "Recent",
                "follow_up": "Follow-up",
                "name": "Name",
            }[s],
            label_visibility="collapsed",
        )
    with f6:
        if st.button("Sync", use_container_width=True, help="Reload from GitHub"):
            ensure_crm_loaded(force=True)
            st.rerun()

    filtered = contacts
    if status_filter != "all":
        filtered = [
            c for c in filtered
            if normalize_status(c.get("status") or "new") == status_filter
        ]
    if q.strip():
        needle = q.lower()
        filtered = [
            c for c in filtered
            if needle in " ".join([
                c.get("id", ""), c.get("name", ""), c.get("phone", ""), c.get("email", ""),
                c.get("company", ""), c.get("industry", ""), c.get("owner", ""),
                c.get("value", ""), c.get("client", ""), c.get("notes", ""),
            ]).lower()
        ]
    if source_filter != "all":
        filtered = [c for c in filtered if _contact_source(c) == source_filter]
    if deal_status_filter != "all":
        filtered = [
            c for c in filtered
            if normalize_deal_status(c.get("deal_status") or "", stage=normalize_status(c.get("status") or "new")) == deal_status_filter
        ]

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
            if not contacts else "No contacts match those filters."
        )
        st.markdown(
            f'<div class="crm-empty">{empty_msg}</div>',
            unsafe_allow_html=True,
        )
        return

    st.caption(f"{len(filtered)} contact{'s' if len(filtered) != 1 else ''}")

    st.markdown(
        '<div class="crm-ledger-head">'
        '<span>Lead ID <span class="line"></span></span>'
        '<span>Company <span class="line"></span></span>'
        '<span>Contact <span class="line"></span></span>'
        '<span>Source <span class="line"></span></span>'
        '<span>Stage <span class="line"></span></span>'
        '<span>Status <span class="line"></span></span>'
        '</div>',
        unsafe_allow_html=True,
    )

    id_to_idx = {c.get("id"): i for i, c in enumerate(contacts)}
    for contact in filtered:
        idx = id_to_idx.get(contact.get("id"))
        if idx is not None:
            _render_contact_card(contact, idx, statuses)


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
