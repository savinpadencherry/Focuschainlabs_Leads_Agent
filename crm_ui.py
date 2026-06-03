"""FocusChain CRM — simple contact book backed by GitHub."""

from __future__ import annotations

import html
from datetime import datetime

import streamlit as st

from utils.crm_models import (
    CRM_STATUSES,
    STATUS_LABELS,
    display_name,
    display_subtitle,
    new_contact_id,
    normalize_contact,
    source_label,
    utc_now_iso,
)
from utils.crm_store import github_configured, import_leads_to_crm, load_crm, save_crm


CRM_CSS = """
<style>
.crm-head {
    display: flex; align-items: flex-start; justify-content: space-between;
    gap: 16px; margin-bottom: 20px; flex-wrap: wrap;
}
.crm-head h2 {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 26px; font-weight: 700; color: var(--ink);
    margin: 0 0 4px 0; letter-spacing: -.02em;
}
.crm-head p { margin: 0; color: var(--ink-mute); font-size: 14px; max-width: 520px; }
.crm-sync {
    display: inline-flex; align-items: center; gap: 7px;
    padding: 5px 11px; border-radius: 999px; font-size: 11px; font-weight: 600;
    border: 1px solid var(--line-soft); background: var(--cream-3);
}
.crm-sync.ok { color: var(--green); background: var(--green-bg); border-color: rgba(46,139,77,.22); }
.crm-sync.warn { color: var(--amber); background: var(--amber-bg); border-color: rgba(183,121,31,.22); }
.crm-sync .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.crm-stats {
    display: flex; gap: 10px; margin-bottom: 18px; flex-wrap: wrap;
}
.crm-stat {
    flex: 1; min-width: 100px;
    background: var(--cream-3); border: 1px solid var(--line-soft);
    border-radius: var(--r); padding: 12px 14px;
}
.crm-stat .n {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 22px; font-weight: 700; color: var(--ink); line-height: 1;
}
.crm-stat .l {
    font-size: 10px; letter-spacing: .08em; text-transform: uppercase;
    color: var(--ink-mute); margin-top: 5px;
}
.crm-add-box {
    background: var(--cream-3); border: 1px solid var(--line-soft);
    border-radius: var(--rl); padding: 18px 20px; margin-bottom: 20px;
}
.crm-add-box .label {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 15px; font-weight: 700; color: var(--ink); margin-bottom: 2px;
}
.crm-add-box .hint { font-size: 12px; color: var(--ink-mute); margin-bottom: 14px; }
.crm-list { display: flex; flex-direction: column; gap: 8px; }
.crm-card {
    background: var(--cream-3); border: 1px solid var(--line-soft);
    border-radius: var(--r); padding: 14px 16px;
}
.crm-card-top {
    display: flex; align-items: center; justify-content: space-between;
    gap: 12px; flex-wrap: wrap;
}
.crm-card-name {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 16px; font-weight: 700; color: var(--ink);
}
.crm-card-sub { font-size: 12px; color: var(--ink-mute); margin-top: 3px; }
.crm-card-meta { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.crm-pill {
    display: inline-block; padding: 3px 9px; border-radius: 999px;
    font-size: 10px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase;
}
.crm-pill.new { background: rgba(46,139,77,.12); color: var(--green); }
.crm-pill.contacted { background: rgba(59,130,246,.12); color: #1D4ED8; }
.crm-pill.interested { background: rgba(168,85,247,.12); color: #7E22CE; }
.crm-pill.won { background: rgba(46,139,77,.18); color: #166534; }
.crm-pill.lost { background: rgba(169,61,61,.12); color: var(--red); }
.crm-src {
    font-size: 10px; color: var(--ink-mute); letter-spacing: .04em;
    text-transform: uppercase; font-weight: 600;
}
.crm-empty {
    text-align: center; padding: 40px 20px;
    border: 1px dashed var(--line-mid); border-radius: var(--rl);
    color: var(--ink-mute); font-size: 14px;
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


def _render_quick_add() -> None:
    st.markdown(
        '<div class="crm-add-box">'
        '<div class="label">Add a contact</div>'
        '<div class="hint">Met someone on the ground? Add name + phone — saved to your GitHub repo instantly.</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    with st.form("crm_quick_add", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns([1.2, 1.2, 1, 1])
        with c1:
            name = st.text_input("Name", placeholder="Rajesh Kumar")
        with c2:
            phone = st.text_input("Phone", placeholder="+91 98xxx xxxxx")
        with c3:
            company = st.text_input("Company", placeholder="Optional")
        with c4:
            client = st.text_input("For client", placeholder="SN Realtors")
        notes = st.text_input("Quick note", placeholder="Met at event, looking for villa in Whitefield…")
        if st.form_submit_button("Save contact", type="primary", use_container_width=True):
            if not name.strip() and not phone.strip():
                st.error("Add at least a name or phone number.")
            else:
                contact = normalize_contact(
                    {
                        "id": new_contact_id(),
                        "name": name,
                        "phone": phone,
                        "company": company,
                        "client": client,
                        "notes": notes,
                        "source": "manual",
                        "tags": ["manual", "ground"],
                    }
                )
                st.session_state.crm_db.setdefault("contacts", []).append(contact)
                if persist_crm(f"CRM: add {display_name(contact)}"):
                    st.toast(f"Saved {display_name(contact)}")
                    st.rerun()


def _render_contact_card(contact: dict, idx: int) -> None:
    cid = contact.get("id", f"row-{idx}")
    name = display_name(contact)
    sub = display_subtitle(contact)
    status = contact.get("status") or "new"
    pill = STATUS_LABELS.get(status, status.title())
    src = source_label(contact)

    label = f"{name}  ·  {contact.get('phone') or contact.get('email') or 'no contact yet'}"

    with st.expander(label, expanded=False):
        st.markdown(
            f'<div class="crm-card">'
            f'<div class="crm-card-top">'
            f'<div><div class="crm-card-name">{html.escape(name)}</div>'
            f'<div class="crm-card-sub">{html.escape(sub)}</div></div>'
            f'<div class="crm-card-meta">'
            f'<span class="crm-src">{html.escape(src)}</span>'
            f'<span class="crm-pill {html.escape(status)}">{html.escape(pill)}</span>'
            f'</div></div></div>',
            unsafe_allow_html=True,
        )

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

        v_notes = st.text_area("Notes", contact.get("notes", ""), height=72, key=f"nt_{cid}")
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
                        "next_follow_up": v_follow,
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


def render_crm_page() -> None:
    st.markdown(CRM_CSS, unsafe_allow_html=True)
    ensure_crm_loaded(force=True)  # always fresh from GitHub on CRM tab open

    db = st.session_state.crm_db
    meta = st.session_state.get("crm_meta") or {}
    contacts = list(db.get("contacts") or [])

    to_call = sum(1 for c in contacts if (c.get("status") or "new") in ("new", "contacted"))
    won = sum(1 for c in contacts if c.get("status") == "won")

    st.markdown(
        f"""
        <div class="crm-head">
          <div>
            <h2>Contacts</h2>
            <p>Your team's call list — from agent runs and contacts you add on the ground. Everything lives in GitHub.</p>
          </div>
          {_sync_badge(meta)}
        </div>
        <div class="crm-stats">
          <div class="crm-stat"><div class="n">{len(contacts)}</div><div class="l">Total</div></div>
          <div class="crm-stat"><div class="n">{to_call}</div><div class="l">To follow up</div></div>
          <div class="crm-stat"><div class="n">{won}</div><div class="l">Won</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _render_quick_add()

    f1, f2, f3 = st.columns([2.2, 1.2, 0.6])
    with f1:
        q = st.text_input("Search", placeholder="Name, phone, company…", label_visibility="collapsed")
    with f2:
        status_filter = st.selectbox(
            "Filter",
            ["all"] + CRM_STATUSES,
            format_func=lambda s: "All" if s == "all" else STATUS_LABELS[s],
            label_visibility="collapsed",
        )
    with f3:
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

    st.markdown('<div class="sec">Your list <span class="line"></span></div>', unsafe_allow_html=True)

    if not filtered:
        st.markdown(
            '<div class="crm-empty">No contacts yet.<br>Add someone above, or import from a Lead Agent run.</div>',
            unsafe_allow_html=True,
        )
        return

    st.caption(f"{len(filtered)} contact{'s' if len(filtered) != 1 else ''}")

    id_to_idx = {c.get("id"): i for i, c in enumerate(contacts)}
    for contact in sorted(filtered, key=lambda c: c.get("updated_at", ""), reverse=True):
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
