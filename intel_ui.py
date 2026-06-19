"""
Intel Agent UI — pipeline company news monitoring.

Stages: setup → running → results
Matches the Scout Agent live-streaming UX: terminal console during run,
briefing cards (reusing .lc lead-card CSS) in results.
"""

from __future__ import annotations

import html as _html
import os
import time
from typing import Any

import streamlit as st

from agent.intel_agent import (
    SIGNAL_META,
    TIMING_META,
    run_intel,
)
from utils.crm_models import normalize_comment, utc_now_iso
from utils.crm_store import load_crm, save_crm
from utils.intel_store import load_briefings, mark_pushed, upsert_briefings
from utils.usage_guide import render_usage_guide


# ── Session state ─────────────────────────────────────────────────────────────

def _init() -> None:
    defaults: dict[str, Any] = {
        "intel_stage":      "setup",   # setup | running | results
        "intel_events":     [],
        "intel_briefings":  [],
        "intel_companies":  [],
        "intel_pushed_ids": set(),
        "intel_crm_db":     None,
        "intel_crm_meta":   None,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


def _reset() -> None:
    st.session_state.intel_stage     = "setup"
    st.session_state.intel_events    = []
    st.session_state.intel_briefings = []
    st.session_state.intel_companies = []
    st.session_state.intel_crm_db    = None
    st.session_state.intel_crm_meta  = None


def _load_crm() -> tuple[list, dict]:
    if st.session_state.intel_crm_db is None:
        db, meta = load_crm()
        st.session_state.intel_crm_db   = db
        st.session_state.intel_crm_meta = meta
    return (
        st.session_state.intel_crm_db.get("contacts", []),
        st.session_state.intel_crm_meta or {},
    )


# ── HTML renderers ────────────────────────────────────────────────────────────

def _e(text: str) -> str:
    return _html.escape(str(text or ""))


def _signal_chip(signal: dict) -> str:
    meta = SIGNAL_META.get(signal.get("type", "other"), SIGNAL_META["other"])
    return (
        f'<span style="font-size:10.5px;font-weight:700;letter-spacing:.04em;'
        f'color:{meta["color"]};background:{meta["bg"]};'
        f'padding:3px 9px;border-radius:4px;border:1px solid {meta["color"]};'
        f'white-space:nowrap;">{meta["icon"]} {meta["label"]}</span>'
    )


def _timing_badge(timing: str) -> str:
    meta = TIMING_META.get(timing, TIMING_META["wait"])
    return (
        f'<span style="font-size:10px;font-weight:700;letter-spacing:.05em;'
        f'color:{meta["color"]};background:{meta["bg"]};'
        f'padding:4px 10px;border-radius:4px;border:1px solid {meta["color"]};">'
        f'{meta["label"]}</span>'
    )


def _briefing_card_html(b: dict) -> str:
    signals  = b.get("signals") or []
    timing   = b.get("outreach_timing", "wait")
    name     = _e(b.get("company", ""))
    industry = _e(b.get("industry", ""))
    cn       = _e(b.get("contact_name", ""))
    ct       = _e(b.get("contact_title", ""))
    pushed   = b.get("pushed_to_crm", False)

    # Subtitle line
    subtitle_parts = [p for p in [industry, f"{cn} ({ct})" if cn and ct else cn] if p]
    subtitle = " · ".join(subtitle_parts)

    # Signal chips row
    chip_html = "".join(_signal_chip(s) for s in signals[:6])
    chips_row = (
        f'<div style="display:flex;gap:6px;flex-wrap:wrap;margin:10px 0;">{chip_html}</div>'
        if chip_html else ""
    )

    # Timing + pushed badge
    timing_html = _timing_badge(timing)
    if pushed:
        timing_html += (
            '&nbsp;<span style="font-size:10px;font-weight:700;letter-spacing:.05em;'
            'color:#1a6b3c;background:rgba(26,107,60,.1);padding:3px 8px;'
            'border-radius:4px;border:1px solid #1a6b3c;">✓ In CRM</span>'
        )

    # Timing reason
    reason = _e(b.get("timing_reason", ""))
    reason_html = (
        f'<div style="font-size:11.5px;color:var(--ink-mute);margin-top:4px;'
        f'font-family:\'JetBrains Mono\',monospace;">{reason}</div>'
        if reason else ""
    )

    # Summary
    summary = _e(b.get("summary", ""))
    summary_html = f'<div class="lc-sig">{summary}</div>' if summary else ""

    # Opener
    opener = _e(b.get("opener", ""))
    opener_html = (
        f'<div class="lc-opener">'
        f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:9px;'
        f'font-weight:700;letter-spacing:.14em;text-transform:uppercase;'
        f'color:var(--green);display:block;margin-bottom:5px;">RECOMMENDED OPENER</span>'
        f'{opener}'
        f'</div>'
    ) if opener else ""

    # Signal detail rows
    ev_rows = ""
    for sig in signals[:4]:
        meta = SIGNAL_META.get(sig.get("type", "other"), SIGNAL_META["other"])
        headline   = _e(sig.get("headline", ""))
        relevance  = _e(sig.get("relevance", ""))
        url        = sig.get("url", "")
        url_html   = (
            f'<a href="{_e(url)}" target="_blank" '
            f'style="color:var(--ink-mute);font-size:10px;margin-left:4px;">↗</a>'
        ) if url else ""
        ev_rows += (
            f'<div class="lc-ev-item">'
            f'<span class="lc-ev-cat" style="background:{meta["bg"]};color:{meta["color"]};">'
            f'{meta["icon"]} {meta["label"]}</span>'
            f'<span><strong>{headline}</strong>{url_html}'
            + (f'<br><span style="color:var(--ink-mute);font-size:11.5px;">{relevance}</span>' if relevance else "")
            + '</span></div>'
        )
    evidence_html = (
        f'<div class="lc-evidence">'
        f'<div class="lc-ev-label">Signal details</div>'
        f'{ev_rows}'
        f'</div>'
    ) if ev_rows else ""

    # Source links
    sources  = b.get("sources") or []
    src_bits = []
    for url in sources[:3]:
        if url:
            domain = url.split("/")[2] if url.startswith("http") and "/" in url[8:] else url[:35]
            src_bits.append(
                f'<a href="{_e(url)}" target="_blank" '
                f'style="color:var(--ink-mute);font-size:11px;text-decoration:none;">'
                f'↗ {_e(domain)}</a>'
            )
    src_html = (
        f'<div style="margin-top:8px;display:flex;gap:12px;flex-wrap:wrap;">'
        f'{"".join(src_bits)}</div>'
    ) if src_bits else ""

    # Ran-at timestamp
    ran_at = b.get("ran_at", "")[:16].replace("T", " ") if b.get("ran_at") else ""
    ts_html = (
        f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:10px;'
        f'color:var(--ink-mute);margin-top:8px;">{ran_at} UTC</div>'
    ) if ran_at else ""

    return (
        f'<div class="lc">'
        f'<div class="lc-hd">'
        f'<div>'
        f'<div class="lc-name">{name}</div>'
        f'<div class="lc-meta">{subtitle}</div>'
        f'</div>'
        f'<div style="text-align:right;">{timing_html}{reason_html}</div>'
        f'</div>'
        f'{chips_row}'
        f'{summary_html}'
        f'{opener_html}'
        f'{evidence_html}'
        f'{src_html}'
        f'{ts_html}'
        f'</div>'
    )


def _render_log_html(events: list) -> str:
    rows = []
    for ev in events:
        t   = ev.get("type", "")
        co  = _e(ev.get("company", ""))
        idx = ev.get("idx", "")
        tot = ev.get("total", "")

        if t == "start":
            rows.append(
                f'<div class="il-row il-start">'
                f'Starting Intel run — {_e(str(tot))} companies queued</div>'
            )
        elif t == "checking":
            rows.append(
                f'<div class="il-row">'
                f'<span class="il-badge il-chk">CHECK {idx}/{tot}</span>'
                f'<span class="il-co">{co}</span>'
                f'<span class="il-dt">checking freshness…</span>'
                f'</div>'
            )
        elif t == "cached":
            age = ev.get("age_hrs", 0)
            rows.append(
                f'<div class="il-row">'
                f'<span class="il-badge il-cache">CACHED</span>'
                f'<span class="il-co">{co}</span>'
                f'<span class="il-dt">using result from {_e(str(age))}h ago</span>'
                f'</div>'
            )
        elif t == "searching":
            rows.append(
                f'<div class="il-row">'
                f'<span class="il-badge il-search">SEARCH</span>'
                f'<span class="il-co">{co}</span>'
                f'<span class="il-dt">querying Serper news…</span>'
                f'</div>'
            )
        elif t == "found":
            hl   = _e(ev.get("headlines", [""])[0][:75])
            cnt  = ev.get("count", 0)
            rows.append(
                f'<div class="il-row">'
                f'<span class="il-badge il-found">FOUND {cnt}</span>'
                f'<span class="il-co">{co}</span>'
                f'<span class="il-dt">{hl}</span>'
                f'</div>'
            )
        elif t == "no_news":
            rows.append(
                f'<div class="il-row">'
                f'<span class="il-badge il-skip">NO NEWS</span>'
                f'<span class="il-co">{co}</span>'
                f'<span class="il-dt">no recent signals found</span>'
                f'</div>'
            )
        elif t == "analyzing":
            rows.append(
                f'<div class="il-row">'
                f'<span class="il-badge il-analyze">GEMINI</span>'
                f'<span class="il-co">{co}</span>'
                f'<span class="il-dt">analyzing signals with AI…</span>'
                f'</div>'
            )
        elif t == "briefing":
            cnt    = ev.get("signal_count", 0)
            timing = (ev.get("briefing") or {}).get("outreach_timing", "")
            tl     = TIMING_META.get(timing, {}).get("label", timing)
            rows.append(
                f'<div class="il-row il-done">'
                f'<span class="il-badge il-brief">DONE</span>'
                f'<span class="il-co">{co}</span>'
                f'<span class="il-dt">'
                f'{cnt} signal{"s" if cnt != 1 else ""} · {_e(tl)}'
                f'</span>'
                f'</div>'
            )
        elif t in ("error", "rate_limit"):
            rows.append(
                f'<div class="il-row">'
                f'<span class="il-badge il-error">{"QUOTA" if t == "rate_limit" else "ERROR"}</span>'
                f'<span class="il-co">{co}</span>'
                f'<span class="il-dt">{_e(ev.get("error","")[:100])}</span>'
                f'</div>'
            )
        elif t == "done":
            tc = ev.get("total_companies", 0)
            ts = ev.get("total_signals", 0)
            sc = ev.get("serper_calls", 0)
            rows.append(
                f'<div class="il-row il-final">'
                f'Run complete — {tc} companies · {ts} signal{"s" if ts != 1 else ""} · '
                f'{sc} Serper call{"s" if sc != 1 else ""} used'
                f'</div>'
            )

    rows_html = "\n".join(rows) if rows else (
        '<div style="color:rgba(245,242,235,.3);font-size:12px;">Waiting…</div>'
    )

    return f"""
<div class="run-console" style="margin-bottom:16px;">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;">
    <span style="font-family:'JetBrains Mono',monospace;font-size:10px;font-weight:700;
                 letter-spacing:.2em;text-transform:uppercase;
                 color:rgba(245,242,235,.45);">INTEL AGENT</span>
    <div style="flex:1;height:1px;background:rgba(245,242,235,.1);"></div>
    <span class="il-pulse"></span>
    <span style="font-family:'JetBrains Mono',monospace;font-size:9px;
                 color:var(--green);letter-spacing:.15em;">LIVE</span>
  </div>
  <div style="display:flex;flex-direction:column;gap:3px;max-height:320px;overflow-y:auto;">
    {rows_html}
  </div>
</div>
"""


# ── Push to CRM ───────────────────────────────────────────────────────────────

def _push_to_crm(briefing: dict) -> str | None:
    """
    Add Intel briefing as a comment to the CRM contact thread.
    Returns error string on failure, None on success.
    """
    contacts, meta = _load_crm()
    cid     = briefing.get("contact_id", "")
    company = briefing.get("company", "")

    # Find by contact_id or company name
    target = None
    if cid:
        target = next((c for c in contacts if c.get("id") == cid), None)
    if not target and company:
        target = next(
            (c for c in contacts
             if (c.get("company") or "").lower() == company.lower()),
            None,
        )
    if not target:
        return f"Contact not found in CRM for '{company}'"

    signals = briefing.get("signals") or []
    sig_lines = "\n".join(
        f"  • [{s.get('type','').upper()}] {s.get('headline','')}"
        for s in signals[:6]
    )
    opener    = briefing.get("opener", "")
    summary   = briefing.get("summary", "")
    timing    = TIMING_META.get(briefing.get("outreach_timing", "wait"), {}).get("label", "")
    ran_at    = (briefing.get("ran_at") or "")[:16].replace("T", " ")

    body = (
        f"[Intel Report — {ran_at} UTC]\n\n"
        f"Summary: {summary}\n\n"
        + (f"Signals:\n{sig_lines}\n\n" if sig_lines else "")
        + (f"Recommended opener:\n{opener}\n\n" if opener else "")
        + f"Timing: {timing}"
    )

    comment = normalize_comment({
        "author": "Intel Agent",
        "body":   body,
        "type":   "intel",
    })

    db = st.session_state.intel_crm_db
    for c in db.get("contacts", []):
        if c.get("id") == target.get("id"):
            c.setdefault("comments", []).insert(0, comment)
            c["updated_at"] = utc_now_iso()
            break

    result = save_crm(
        db,
        sha=meta.get("sha"),
        message=f"Intel: briefing pushed for {company}",
    )
    if isinstance(result, dict):
        st.session_state.intel_crm_meta = {
            **meta,
            "sha": result.get("sha") or meta.get("sha"),
        }

    mark_pushed(briefing.get("id", ""))
    return None


# ── Page CSS ──────────────────────────────────────────────────────────────────

_CSS = """
<style>
/* Intel-specific styles — brand vars come from streamlit_app.py global CSS */

.ia-head {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 26px; font-weight: 800;
    letter-spacing: -.02em; margin-bottom: 2px;
    color: var(--ink);
}
.ia-sub { font-size: 13px; color: var(--ink-mute); margin-bottom: 20px; }

/* Cost pill */
.ia-cost-pill {
    display: inline-flex; align-items: center; gap: 7px;
    background: var(--green-bg); border: 1px solid rgba(46,139,77,.25);
    border-radius: 20px; padding: 4px 12px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10.5px; font-weight: 700; letter-spacing: .04em;
    color: var(--green);
}
.ia-cost-pill .dot { width:6px;height:6px;background:var(--green);border-radius:50%; }

/* Company selection card */
.co-sel-card {
    padding: 10px 13px; border-radius: 8px;
    border: 1.5px solid var(--line); background: var(--cream-3);
    margin-bottom: 6px; cursor: pointer;
}
.co-sel-card.sel {
    border-color: var(--green);
    background: var(--green-bg);
    box-shadow: 0 0 0 2px rgba(46,139,77,.12);
}
.co-sel-name { font-weight: 700; font-size: 13.5px; color: var(--ink); }
.co-sel-meta { font-size: 11.5px; color: var(--ink-mute); margin-top: 2px; }

/* Intel terminal log */
.il-row {
    display: flex; align-items: center; gap: 9px;
    padding: 3px 0;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11.5px; color: rgba(245,242,235,.6);
    line-height: 1.4;
}
.il-badge {
    font-size: 9px; font-weight: 700; letter-spacing: .1em;
    padding: 2px 7px; border-radius: 3px; white-space: nowrap; flex-shrink: 0;
}
.il-co   { color: rgba(245,242,235,.9); font-weight: 600; flex-shrink: 0; }
.il-dt   { color: rgba(245,242,235,.4); font-size: 11px; overflow: hidden;
           text-overflow: ellipsis; white-space: nowrap; }
.il-start { color: rgba(245,242,235,.4); font-style: italic; padding-bottom: 6px;
            border-bottom: 1px solid rgba(245,242,235,.07); margin-bottom: 3px; }
.il-done  { color: rgba(245,242,235,.7); }
.il-final {
    color: #37A85C; font-weight: 700;
    border-top: 1px solid rgba(245,242,235,.1);
    padding-top: 7px !important; margin-top: 5px;
}

.il-chk     { background: rgba(107,127,133,.2); color: rgba(245,242,235,.5); }
.il-cache   { background: rgba(183,121,31,.25); color: #d4a847; }
.il-search  { background: rgba(26,58,107,.35);  color: #7ba3d4; }
.il-found   { background: rgba(26,107,60,.25);  color: #6fcf97; }
.il-analyze { background: rgba(90,45,130,.3);   color: #c49ee0; }
.il-brief   { background: rgba(46,139,77,.3);   color: #37A85C; }
.il-skip    { background: rgba(107,127,133,.18); color: rgba(245,242,235,.38); }
.il-error   { background: rgba(169,61,61,.3);   color: #e07070; }

@keyframes ilPulse { 0%,100%{opacity:1;} 50%{opacity:.3;} }
.il-pulse {
    width: 6px; height: 6px; background: var(--green); border-radius: 50%;
    display: inline-block; animation: ilPulse 1.2s ease-in-out infinite;
}

/* Results summary bar */
.ia-sum {
    display: flex; gap: 20px; align-items: center;
    padding: 12px 16px; border-radius: 8px;
    background: var(--cream-3); border: 1px solid var(--line-soft);
    margin-bottom: 16px;
}
.ia-sum-num { font-size: 22px; font-weight: 800; color: var(--ink); line-height: 1; }
.ia-sum-lbl { font-size: 11px; color: var(--ink-mute); font-family: 'JetBrains Mono', monospace;
              letter-spacing: .06em; text-transform: uppercase; }
.ia-divider { width: 1px; height: 32px; background: var(--line); }

/* No signals state */
.ia-no-sig {
    padding: 10px 0;
    font-size: 13px; color: var(--ink-mute);
    font-style: italic;
}

/* Section label */
.ia-sec {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px; font-weight: 700; letter-spacing: .14em;
    text-transform: uppercase; color: var(--ink-mute);
    padding: 16px 0 8px;
    border-bottom: 1px solid var(--line-soft);
    margin-bottom: 12px;
}

@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
    }
}

@media (max-width: 720px) {
    .ia-head { font-size: 28px; line-height: 1.1; }
    .ia-sub { font-size: 12.5px; line-height: 1.55; }
    .ia-cost-pill { font-size: 10px; flex-wrap: wrap; justify-content: center; text-align: center; }
    .ia-sum-row { flex-wrap: wrap; gap: 12px; justify-content: center; }
    .ia-divider { display: none; }
    .ia-co-card { padding: 10px 12px; }
    .ia-co-card.sel { transform: none; }
    .ia-signal-card { padding: 12px 14px; }
    .ia-sec { font-size: 9px; }
}
</style>
"""


# ── Main render ───────────────────────────────────────────────────────────────

def render_intel_page() -> None:
    _init()

    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown('<div class="ia-head">Intel Agent</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="ia-sub">Monitor your pipeline for funding rounds, leadership changes, '
        'expansion moves and more — AI-distilled to a ready-to-use outreach opener.</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="ia-cost-pill"><div class="dot"></div>'
        '~$0.0004 per 10-company run &nbsp;·&nbsp; free within Serper 100/day quota</div>',
        unsafe_allow_html=True,
    )
    render_usage_guide("intel")
    st.markdown("")

    stage = st.session_state.intel_stage

    # ══════════════════════════════════ SETUP ════════════════════════════════
    if stage == "setup":
        _render_setup()

    # ══════════════════════════════════ RUNNING ═══════════════════════════════
    elif stage == "running":
        _render_running()

    # ══════════════════════════════════ RESULTS ═══════════════════════════════
    elif stage == "results":
        _render_results()


# ── Setup phase ───────────────────────────────────────────────────────────────

def _render_setup() -> None:
    contacts, _ = _load_crm()

    # Filter to active pipeline contacts
    active_stages   = {"new", "contacted", "qualified", "proposal"}
    pipeline_conts  = [c for c in contacts if (c.get("status") or "new") in active_stages]
    other_conts     = [c for c in contacts if (c.get("status") or "new") not in active_stages]

    if not contacts:
        st.info(
            "No CRM contacts yet. Run the Scout Agent first and add leads to the CRM, "
            "then come back to Intel."
        )
        return

    col_sel, col_cfg = st.columns([1.6, 1], gap="large")

    with col_sel:
        st.markdown('<div class="ia-sec">Select companies to monitor</div>', unsafe_allow_html=True)

        # Select all pipeline button
        scol1, scol2 = st.columns(2)
        with scol1:
            if st.button("Select pipeline (active)", use_container_width=True, type="primary"):
                st.session_state.intel_sel = {
                    c.get("id") for c in pipeline_conts if c.get("id")
                }
                st.rerun()
        with scol2:
            if st.button("Clear selection", use_container_width=True):
                st.session_state.intel_sel = set()
                st.rerun()

        st.session_state.setdefault("intel_sel", {
            c.get("id") for c in pipeline_conts if c.get("id")
        })
        sel_ids: set = st.session_state.intel_sel

        # Group: pipeline first, then others
        groups = [
            ("Active pipeline", pipeline_conts),
            ("Other contacts", other_conts),
        ]
        for group_label, group_contacts in groups:
            if not group_contacts:
                continue
            st.caption(group_label)
            for c in sorted(group_contacts,
                            key=lambda x: -int(x.get("score") or 0))[:40]:
                cid   = c.get("id", "")
                stage = c.get("status") or "new"
                name  = c.get("company") or c.get("name") or "Unnamed"
                sub   = " · ".join(p for p in [
                    c.get("name", "") if c.get("name") != name else "",
                    c.get("industry", ""),
                ] if p)
                is_sel = cid in sel_ids

                stage_colors = {
                    "new":       "#6B7F85",
                    "contacted": "#B7791F",
                    "qualified": "#1a6b3c",
                    "proposal":  "#1a3a6b",
                    "won":       "#2E8B4D",
                    "lost":      "#A93D3D",
                }
                sc = stage_colors.get(stage, "#6B7F85")
                card_cls = "co-sel-card sel" if is_sel else "co-sel-card"

                st.markdown(f"""
                <div class="{card_cls}">
                  <div class="co-sel-name">{_e(name)}</div>
                  <div class="co-sel-meta">
                    {_e(sub)} &nbsp;·&nbsp;
                    <span style="color:{sc};font-weight:700;font-size:10.5px;
                                 text-transform:uppercase;letter-spacing:.06em;">
                      {stage}</span>
                  </div>
                </div>
                """, unsafe_allow_html=True)

                btn_lbl  = "✓ Selected" if is_sel else "Select"
                btn_type = "primary" if is_sel else "secondary"
                if st.button(btn_lbl, key=f"isel_{cid}", use_container_width=True, type=btn_type):
                    if is_sel:
                        sel_ids.discard(cid)
                    else:
                        sel_ids.add(cid)
                    st.session_state.intel_sel = sel_ids
                    st.rerun()

        # Competitor / custom companies (not in CRM)
        st.markdown('<div class="ia-sec" style="margin-top:12px;">Add competitors or custom companies</div>',
                    unsafe_allow_html=True)
        extra_raw = st.text_area(
            "Company names (one per line)",
            key="intel_extra_companies",
            placeholder="Google\nSalesforce\nA competitor name",
            height=80,
            label_visibility="collapsed",
        )

    with col_cfg:
        st.markdown('<div class="ia-sec">Run configuration</div>', unsafe_allow_html=True)

        offering = st.text_area(
            "Your offering (shapes signal relevance)",
            key="intel_offering",
            value=os.getenv("SENDER_OFFERING", "B2B AI automation and lead generation services"),
            height=70,
        )

        freshness = st.slider(
            "Re-fetch if older than (hours)",
            min_value=1, max_value=48,
            value=12,
            key="intel_freshness",
            help="Briefings cached within this window are reused — saves Serper calls.",
        )

        st.markdown("")
        n_crm   = len(sel_ids)
        n_extra = len([l.strip() for l in (extra_raw or "").splitlines() if l.strip()])
        n_total = n_crm + n_extra
        est_cost = f"~${n_total * 0.00004:.5f}" if n_total else "$0.00"

        st.markdown(f"""
        <div style="background:var(--cream-3);border:1px solid var(--line-soft);
                    border-radius:8px;padding:14px 16px;font-size:13px;">
          <div style="margin-bottom:8px;font-weight:700;color:var(--ink);">Run estimate</div>
          <div style="color:var(--ink-soft);">
            <b>{n_crm}</b> CRM contact{"s" if n_crm != 1 else ""} +
            <b>{n_extra}</b> custom<br>
            <b>{n_total}</b> Serper calls &nbsp;·&nbsp; <b>{n_total}</b> Gemini calls<br>
            Estimated cost: <b>{est_cost}</b><br>
            Serper quota remaining: ~{max(0, 100 - n_total)} of 100/day
          </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("")

        # Validate
        can_run = n_total > 0 and os.getenv("SERPER_API_KEY") and os.getenv("GEMINI_API_KEY")

        if not os.getenv("SERPER_API_KEY"):
            st.warning("SERPER_API_KEY not configured in secrets.")
        if not os.getenv("GEMINI_API_KEY"):
            st.warning("GEMINI_API_KEY not configured in secrets.")

        if st.button(
            f"Run Intel — {n_total} company{'s' if n_total != 1 else ''}",
            use_container_width=True,
            type="primary",
            disabled=not can_run,
        ):
            # Build company list from selected CRM contacts + custom entries
            companies = []
            for c in contacts:
                if c.get("id") in sel_ids:
                    companies.append({
                        "name":          c.get("company") or c.get("name") or "",
                        "website":       c.get("website", ""),
                        "industry":      c.get("industry", ""),
                        "contact_id":    c.get("id", ""),
                        "contact_name":  c.get("name", ""),
                        "contact_title": c.get("title", "") or "",
                    })
            for line in (extra_raw or "").splitlines():
                name = line.strip()
                if name:
                    companies.append({"name": name, "website": "", "industry": "",
                                      "contact_id": "", "contact_name": "", "contact_title": ""})

            st.session_state.intel_companies = companies
            st.session_state.intel_events    = []
            st.session_state.intel_briefings = []
            st.session_state.intel_stage     = "running"
            st.session_state.intel_offering  = offering
            st.session_state.intel_freshness = freshness
            st.rerun()


# ── Running phase ─────────────────────────────────────────────────────────────

def _render_running() -> None:
    companies  = st.session_state.intel_companies
    offering   = st.session_state.get("intel_offering", "")
    freshness  = st.session_state.get("intel_freshness", 12)

    log_slot    = st.empty()
    status_slot = st.empty()
    cards_slot  = st.empty()

    # Initial render
    log_slot.markdown(
        _render_log_html([{"type": "start", "total": len(companies), "companies": []}]),
        unsafe_allow_html=True,
    )

    existing    = load_briefings()
    done_events: list = []

    for event in run_intel(
        companies,
        existing_briefings=existing,
        freshness_hours=freshness,
        offering=offering,
    ):
        done_events.append(event)
        st.session_state.intel_events = done_events

        if event.get("type") == "briefing":
            b = event.get("briefing", {})
            if b:
                st.session_state.intel_briefings.append(b)

        # Live log update
        log_slot.markdown(
            _render_log_html(done_events),
            unsafe_allow_html=True,
        )

        # Partial cards preview (HTML only — no buttons during run)
        partial = st.session_state.intel_briefings
        if partial:
            preview_html = "".join(_briefing_card_html(b) for b in partial)
            cards_slot.markdown(preview_html, unsafe_allow_html=True)

        # Small yield to allow Streamlit to flush incremental updates
        time.sleep(0.05)

    # Run complete — persist and transition to results
    upsert_briefings(st.session_state.intel_briefings)
    st.session_state.intel_stage = "results"
    st.rerun()


# ── Results phase ─────────────────────────────────────────────────────────────

def _render_results() -> None:
    briefings   = st.session_state.intel_briefings
    pushed_ids  = st.session_state.intel_pushed_ids
    events      = st.session_state.intel_events

    # Summary bar
    n_companies = len(briefings)
    n_signals   = sum(len(b.get("signals") or []) for b in briefings)
    n_immediate = sum(1 for b in briefings if b.get("outreach_timing") == "immediate")
    done_ev     = next((e for e in reversed(events) if e.get("type") == "done"), {})
    serper_used = done_ev.get("serper_calls", "—")

    st.markdown(f"""
    <div class="ia-sum">
      <div><div class="ia-sum-num">{n_companies}</div><div class="ia-sum-lbl">Companies</div></div>
      <div class="ia-divider"></div>
      <div><div class="ia-sum-num">{n_signals}</div><div class="ia-sum-lbl">Signals found</div></div>
      <div class="ia-divider"></div>
      <div><div class="ia-sum-num" style="color:var(--green);">{n_immediate}</div>
           <div class="ia-sum-lbl">Reach out now</div></div>
      <div class="ia-divider"></div>
      <div><div class="ia-sum-num">{serper_used}</div><div class="ia-sum-lbl">Serper calls</div></div>
    </div>
    """, unsafe_allow_html=True)

    # Action bar
    rcol1, rcol2 = st.columns([1, 3])
    with rcol1:
        if st.button("← Run again", key="intel_rerun", use_container_width=True):
            _reset()
            st.rerun()
    with rcol2:
        if st.button("Push all to CRM threads", key="intel_push_all", use_container_width=True):
            errors = []
            for b in briefings:
                if b.get("id") not in pushed_ids:
                    err = _push_to_crm(b)
                    if err:
                        errors.append(err)
                    else:
                        pushed_ids.add(b.get("id", ""))
                        b["pushed_to_crm"] = True
            st.session_state.intel_pushed_ids = pushed_ids
            if errors:
                st.error("\n".join(errors[:3]))
            else:
                st.success(f"Pushed {len(briefings)} briefings to CRM threads.")
            st.rerun()

    st.markdown("")

    # Sort: immediate first, then good, then wait
    timing_order = {"immediate": 0, "good": 1, "wait": 2, "skip": 3}
    sorted_briefs = sorted(
        briefings,
        key=lambda b: (timing_order.get(b.get("outreach_timing", "wait"), 2),
                       -len(b.get("signals") or [])),
    )

    # Render each briefing card with interactive buttons
    for b in sorted_briefs:
        bid    = b.get("id", "")
        is_pushed = bid in pushed_ids or b.get("pushed_to_crm", False)

        # HTML card (visual)
        if is_pushed:
            b = {**b, "pushed_to_crm": True}  # reflect pushed state in card
        st.markdown(_briefing_card_html(b), unsafe_allow_html=True)

        # Interactive action row
        ba1, ba2, ba3 = st.columns([1, 1, 1], gap="small")

        with ba1:
            push_lbl = "✓ In CRM" if is_pushed else "Push to CRM thread"
            push_disabled = is_pushed
            if st.button(push_lbl, key=f"ipush_{bid}",
                         use_container_width=True, disabled=push_disabled):
                err = _push_to_crm(b)
                if err:
                    st.error(err)
                else:
                    pushed_ids.add(bid)
                    b["pushed_to_crm"] = True
                    st.session_state.intel_pushed_ids = pushed_ids
                    st.success(f"Pushed to {b.get('company','contact')} CRM thread.")
                    st.rerun()

        with ba2:
            contact_id = b.get("contact_id", "")
            if contact_id:
                if st.button("Draft email →", key=f"idraft_{bid}", use_container_width=True):
                    st.session_state.app_view      = "reach"
                    st.session_state.reach_sel_id  = contact_id
                    st.session_state.reach_draft   = None
                    st.rerun()
            else:
                st.button("Draft email →", key=f"idraft_{bid}",
                          use_container_width=True, disabled=True,
                          help="Not linked to a CRM contact")

        with ba3:
            # Copy opener
            opener = b.get("opener", "")
            if opener:
                st.code(opener, language=None)

        st.markdown("<hr style='border:none;border-top:1px solid var(--line-soft);margin:8px 0 16px;'>",
                    unsafe_allow_html=True)

    # Compact log (collapsed)
    with st.expander("View run log", expanded=False):
        st.markdown(
            _render_log_html(st.session_state.intel_events),
            unsafe_allow_html=True,
        )
