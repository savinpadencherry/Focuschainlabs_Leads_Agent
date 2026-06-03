"""FocusChain CRM — simple contact book backed by GitHub."""

from __future__ import annotations

import html
from datetime import date, datetime

import streamlit as st

from utils.crm_models import (
    CRM_STATUSES,
    STATUS_LABELS,
    contact_fingerprint,
    display_name,
    display_subtitle,
    merge_contacts,
    new_contact_id,
    normalize_contact,
    source_label,
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
.crm-list { display: flex; flex-direction: column; gap: 8px; }
.crm-card {
    background: var(--cream-3); border: 1px solid var(--line-soft);
    border-radius: var(--r); padding: 15px 16px; margin: 0 0 8px;
}
.crm-card-top {
    display: flex; align-items: center; justify-content: space-between;
    gap: 12px; flex-wrap: wrap;
}
.crm-card-name {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 17px; font-weight: 800; color: var(--ink);
}
.crm-card-title {
    font-size: 12px; color: var(--ink-mute); font-weight: 600; margin-left: 6px;
}
.crm-card-sub { font-size: 12.5px; color: var(--ink-mute); margin-top: 4px; line-height: 1.45; }
.crm-card-meta { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.crm-pill {
    display: inline-block; padding: 4px 9px; border-radius: 999px;
    font-size: 10px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase;
}
.crm-pill.new { background: rgba(46,139,77,.12); color: var(--green); }
.crm-pill.contacted { background: rgba(59,130,246,.12); color: #1D4ED8; }
.crm-pill.interested { background: rgba(168,85,247,.12); color: #7E22CE; }
.crm-pill.won { background: rgba(46,139,77,.18); color: #166534; }
.crm-pill.lost { background: rgba(169,61,61,.12); color: var(--red); }
.crm-pill.due { background: rgba(183,121,31,.12); color: var(--amber); }
.crm-src {
    font-size: 10px; color: var(--ink-mute); letter-spacing: .04em;
    text-transform: uppercase; font-weight: 600;
}
.crm-actions {
    display: flex; gap: 7px; flex-wrap: wrap; margin-top: 12px;
}
.crm-actions a {
    display: inline-flex; align-items: center; justify-content: center;
    min-height: 30px; padding: 5px 10px; border-radius: 7px;
    border: 1px solid var(--line-soft); background: rgba(15,42,51,.025);
    color: var(--ink-soft); text-decoration: none; font-size: 12px; font-weight: 700;
}
.crm-actions a:hover { border-color: rgba(46,139,77,.35); color: var(--green); background: var(--green-bg); }
.crm-next {
    margin-top: 9px;
    font-size: 12px;
    color: var(--ink-mute);
}
.crm-next strong { color: var(--ink); }
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
}
.stTextInput input,
.stTextArea textarea {
    font-size: 14px !important;
}

@media (max-width: 720px) {
    .crm-head h2 { font-size: 26px; }
    .crm-sync { width: 100%; justify-content: center; white-space: normal; text-align: center; }
    .crm-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .crm-stat { padding: 13px 12px; }
    .crm-card { padding: 14px; }
    .crm-card-top { align-items: flex-start; }
    .crm-card-meta { width: 100%; justify-content: flex-start; }
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


def _clean_follow_up(raw: str) -> str | None:
    raw = (raw or "").strip()
    if not raw:
        return ""
    try:
        return date.fromisoformat(raw[:10]).isoformat()
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
    return "agent" if source_label(contact).lower() == "agent" else "manual"


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
        links.append((f"tel:{tel}", "Call"))
    if email:
        links.append((f"mailto:{email}", "Email"))
    if linkedin:
        links.append((_href(linkedin), "LinkedIn"))
    if website:
        links.append((_href(website), "Website"))
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
        '<div class="label">Add contact</div>'
        '<div class="hint">Save a new prospect, walk-in, referral, or imported lead follow-up.</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    with st.form("crm_quick_add", clear_on_submit=True, border=False):
        c1, c2, c3 = st.columns([1.1, 1, 1])
        with c1:
            name = st.text_input("Name", placeholder="Rajesh Kumar")
        with c2:
            phone = st.text_input("Phone", placeholder="+91 98xxx xxxxx")
        with c3:
            email = st.text_input("Email", placeholder="name@company.com")

        c4, c5, c6 = st.columns([1, 1, 1])
        with c4:
            company = st.text_input("Company", placeholder="Prestige Group")
        with c5:
            client = st.text_input("For client", placeholder="SN Realtors")
        with c6:
            status = st.selectbox(
                "Status",
                CRM_STATUSES,
                index=0,
                format_func=lambda s: STATUS_LABELS[s],
            )

        follow_up = st.text_input("Follow-up date", placeholder="YYYY-MM-DD")
        notes = st.text_area("Quick note", placeholder="Met at event, looking for villa in Whitefield...")
        if st.form_submit_button("Save contact", type="primary", use_container_width=True):
            clean_follow_up = _clean_follow_up(follow_up)
            if clean_follow_up is None:
                st.error("Use YYYY-MM-DD for follow-up date.")
            elif not name.strip() and not phone.strip() and not email.strip():
                st.error("Add at least a name, phone, or email.")
            else:
                contact = normalize_contact(
                    {
                        "id": new_contact_id(),
                        "name": name,
                        "phone": phone,
                        "email": email,
                        "company": company,
                        "client": client,
                        "status": status,
                        "notes": notes,
                        "next_follow_up": clean_follow_up,
                        "source": "manual",
                        "tags": ["manual", "ground"],
                    }
                )
                action, saved = _upsert_contact(contact)
                if persist_crm(f"CRM: {action} {display_name(saved)}"):
                    st.toast(f"{'Updated' if action == 'updated' else 'Saved'} {display_name(saved)}")
                    st.rerun()


def _render_contact_card(contact: dict, idx: int) -> None:
    cid = contact.get("id", f"row-{idx}")
    name = display_name(contact)
    sub = display_subtitle(contact)
    status = contact.get("status") or "new"
    pill = STATUS_LABELS.get(status, status.title())
    src = source_label(contact)
    title = (contact.get("title") or "").strip()
    due_html = (
        '<span class="crm-pill due">Due</span>'
        if _is_due(contact) and status not in {"won", "lost"} else ""
    )
    title_html = f'<span class="crm-card-title">{html.escape(title)}</span>' if title else ""
    follow_html = ""
    if contact.get("next_follow_up"):
        follow_html = (
            f'<div class="crm-next">Next follow-up: '
            f'<strong>{html.escape((contact.get("next_follow_up") or "")[:10])}</strong></div>'
        )

    st.markdown(
        f'<div class="crm-card">'
        f'<div class="crm-card-top">'
        f'<div><div class="crm-card-name">{html.escape(name)}'
        f'{title_html}'
        f'</div><div class="crm-card-sub">{html.escape(sub)}</div></div>'
        f'<div class="crm-card-meta">'
        f'<span class="crm-src">{html.escape(src)}</span>'
        f'{due_html}'
        f'<span class="crm-pill {html.escape(status)}">{html.escape(pill)}</span>'
        f'</div></div>'
        f'{follow_html}'
        f'{_contact_actions(contact)}'
        f'</div>',
        unsafe_allow_html=True,
    )

    with st.expander(f"Edit {name}", expanded=False):
        st.markdown('<div class="crm-edit-wrap">', unsafe_allow_html=True)

        e1, e2 = st.columns(2)
        with e1:
            v_name = st.text_input("Name", contact.get("name", ""), key=f"n_{cid}")
            v_phone = st.text_input("Phone", contact.get("phone", ""), key=f"p_{cid}")
            v_email = st.text_input("Email", contact.get("email", ""), key=f"e_{cid}")
        with e2:
            v_company = st.text_input("Company", contact.get("company", ""), key=f"c_{cid}")
            v_client = st.text_input("For client", contact.get("client", ""), key=f"cl_{cid}")
            v_status = st.selectbox(
                "Status",
                CRM_STATUSES,
                index=CRM_STATUSES.index(status) if status in CRM_STATUSES else 0,
                format_func=lambda s: STATUS_LABELS[s],
                key=f"s_{cid}",
            )

        v_notes = st.text_area("Notes", contact.get("notes", ""), height=96, key=f"nt_{cid}")
        v_follow = st.text_input(
            "Follow up on (YYYY-MM-DD)",
            (contact.get("next_follow_up") or "")[:10],
            key=f"f_{cid}",
        )

        # Agent extras — only if present, tucked away
        if contact.get("signal") or contact.get("opening_line") or contact.get("score"):
            with st.expander("From agent run (read-only)", expanded=False):
                if contact.get("score"):
                    st.caption(f"Score: {contact['score']}/100")
                if contact.get("signal"):
                    st.write(contact["signal"])
                if contact.get("opening_line"):
                    st.info(contact["opening_line"])

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
                            "client": v_client,
                            "status": v_status,
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

    active = sum(1 for c in contacts if (c.get("status") or "new") in ("new", "contacted", "interested"))
    due = sum(1 for c in contacts if _is_due(c) and (c.get("status") or "new") not in {"won", "lost"})
    won = sum(1 for c in contacts if c.get("status") == "won")

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
        <div class="crm-stats">
          <div class="crm-stat"><div class="n">{len(contacts)}</div><div class="l">Total</div></div>
          <div class="crm-stat"><div class="n">{active}</div><div class="l">Active</div></div>
          <div class="crm-stat"><div class="n">{due}</div><div class="l">Due now</div></div>
          <div class="crm-stat"><div class="n">{won}</div><div class="l">Won</div></div>
        </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _render_quick_add()

    f1, f2, f3, f4, f5 = st.columns([2.1, 1.15, 1, 1.15, 0.7])
    with f1:
        q = st.text_input("Search", placeholder="Name, phone, company...", label_visibility="collapsed")
    with f2:
        status_filter = st.selectbox(
            "Status",
            ["all"] + CRM_STATUSES,
            format_func=lambda s: "All" if s == "all" else STATUS_LABELS[s],
            label_visibility="collapsed",
        )
    with f3:
        source_filter = st.selectbox(
            "Source",
            ["all", "manual", "agent"],
            format_func=lambda s: {"all": "All sources", "manual": "Manual", "agent": "Agent"}.get(s, s),
            label_visibility="collapsed",
        )
    with f4:
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
    with f5:
        if st.button("Sync", use_container_width=True, help="Reload from GitHub"):
            ensure_crm_loaded(force=True)
            st.rerun()

    filtered = contacts
    if status_filter != "all":
        filtered = [c for c in filtered if (c.get("status") or "new") == status_filter]
    if q.strip():
        needle = q.lower()
        filtered = [
            c for c in filtered
            if needle in " ".join([
                c.get("name", ""), c.get("phone", ""), c.get("email", ""),
                c.get("company", ""), c.get("client", ""), c.get("notes", ""),
            ]).lower()
        ]
    if source_filter != "all":
        filtered = [c for c in filtered if _contact_source(c) == source_filter]

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

    id_to_idx = {c.get("id"): i for i, c in enumerate(contacts)}
    for contact in filtered:
        idx = id_to_idx.get(contact.get("id"))
        if idx is not None:
            _render_contact_card(contact, idx)


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
