"""
FocusChain LeadGen — Production UI
Focus Chain Labs brand palette · Glass morphism · Zero emojis · Streamlit Cloud ready.
"""

from __future__ import annotations
import os
import json
import glob
import pandas as pd
from datetime import datetime

import streamlit as st

# ── Environment ──────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, str) and _k not in os.environ:
            os.environ[_k] = _v
except Exception:
    pass

os.makedirs("output", exist_ok=True)

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Focus Chain Labs — LeadGen",
    page_icon="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>◈</text></svg>",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    --bg:          #020b16;
    --surface:     #010d19;
    --navy:        #003B5C;
    --green:       #2EBC5D;
    --elevated:    rgba(0, 59, 92, 0.18);
    --glass:       rgba(255, 255, 255, 0.03);
    --border:      rgba(255, 255, 255, 0.07);
    --border-m:    rgba(255, 255, 255, 0.12);
    --border-h:    rgba(255, 255, 255, 0.20);
    --glow:        rgba(46, 188, 93, 0.10);
    --glow-strong: rgba(46, 188, 93, 0.18);
    --t1:          #f8fafc;
    --t2:          #94a3b8;
    --t3:          #475569;
    --amber:       #F59E0B;
    --amber-bg:    rgba(245, 158, 11, 0.08);
    --score-hi:    #2EBC5D;
    --score-mid:   #F59E0B;
    --score-lo:    #475569;
    --r:           10px;
    --rs:          7px;
}

/* ── Reset ── */
html, body { margin: 0; padding: 0; }

/* ── App base — dark + hexagon pattern ── */
.stApp {
    background-color: #020b16 !important;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='48' height='84' viewBox='0 0 48 84'%3E%3Cpath d='M24 0L48 14L48 42L24 56L0 42L0 14L24 0Z' fill='%23003B5C' fill-opacity='0.04'/%3E%3C/svg%3E") !important;
    font-family: 'Inter', -apple-system, sans-serif !important;
    color: var(--t1) !important;
}
.block-container {
    padding-top: 20px !important;
    max-width: 900px !important;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: var(--surface) !important;
    border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"] > div:first-child { padding-top: 20px !important; }

/* ── Primary button — brand gradient ── */
.stButton > button {
    background: linear-gradient(135deg, #003B5C 0%, #2EBC5D 100%) !important;
    color: #fff !important;
    border: none !important;
    border-radius: var(--rs) !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    letter-spacing: 0.01em !important;
    padding: 10px 18px !important;
    transition: opacity 0.15s, transform 0.1s, box-shadow 0.2s !important;
}
.stButton > button:hover {
    opacity: 0.88 !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 8px 32px rgba(46, 188, 93, 0.22) !important;
}
.stButton > button:active  { transform: translateY(0) !important; }
.stButton > button:disabled { opacity: 0.35 !important; cursor: not-allowed !important; }

/* ── Select / Multiselect ── */
[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
[data-testid="stMultiSelect"] div[data-baseweb="select"] > div {
    background: var(--elevated) !important;
    border-color: var(--border-m) !important;
    border-radius: var(--rs) !important;
    color: var(--t1) !important;
}
span[data-baseweb="tag"] {
    background: rgba(0,59,92,0.35) !important;
    border: 1px solid rgba(46,188,93,0.25) !important;
    border-radius: 99px !important;
}

/* ── Text inputs ── */
.stTextInput input {
    background: var(--elevated) !important;
    border-color: var(--border-m) !important;
    color: var(--t1) !important;
    border-radius: var(--rs) !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 13px !important;
}
.stTextInput input:focus {
    border-color: var(--green) !important;
    box-shadow: 0 0 0 3px var(--glow) !important;
}

/* ── Prompt textarea — Notion / Claude style ── */
.stTextArea textarea {
    background: rgba(255, 255, 255, 0.02) !important;
    border: 1px solid rgba(255, 255, 255, 0.07) !important;
    color: var(--t1) !important;
    border-radius: var(--r) !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 14px !important;
    line-height: 1.75 !important;
    padding: 14px 16px !important;
    caret-color: var(--green) !important;
    transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease !important;
    resize: none !important;
}
.stTextArea textarea:focus {
    border-color: rgba(46, 188, 93, 0.45) !important;
    box-shadow: 0 0 0 3px rgba(46, 188, 93, 0.07) !important;
    background: rgba(255, 255, 255, 0.03) !important;
}
.stTextArea textarea::placeholder {
    color: var(--t3) !important;
    font-style: italic !important;
    font-weight: 300 !important;
}

/* ── Slider ── */
[data-testid="stSlider"] [role="slider"] {
    background: var(--green) !important;
    border: 2px solid #fff !important;
}
[data-testid="stSlider"] div[data-testid="stSliderTrackFill"] {
    background: linear-gradient(90deg, var(--navy), var(--green)) !important;
}

/* ── Progress bar ── */
[data-testid="stProgress"] > div {
    background: rgba(0, 59, 92, 0.3) !important;
    border-radius: 99px !important;
    height: 5px !important;
}
[data-testid="stProgress"] > div > div {
    background: linear-gradient(90deg, var(--navy), var(--green)) !important;
    border-radius: 99px !important;
}

/* ── Metrics ── */
[data-testid="stMetric"] {
    background: var(--glass) !important;
    border: 1px solid var(--border) !important;
    backdrop-filter: blur(12px) !important;
    border-radius: var(--r) !important;
    padding: 14px 18px !important;
}
[data-testid="stMetricLabel"] p {
    color: var(--t3) !important;
    font-size: 10px !important;
    letter-spacing: 0.09em !important;
    text-transform: uppercase !important;
    font-weight: 700 !important;
}
[data-testid="stMetricValue"] { color: var(--t1) !important; font-weight: 700 !important; }

/* ── Expander ── */
[data-testid="stExpander"] {
    background: var(--glass) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--rs) !important;
    backdrop-filter: blur(8px) !important;
}

/* ── File uploader ── */
[data-testid="stFileUploader"] {
    background: var(--glass) !important;
    border: 1px dashed var(--border-m) !important;
    border-radius: var(--r) !important;
}

/* ── Number input ── */
[data-testid="stNumberInput"] input {
    background: var(--elevated) !important;
    border-color: var(--border-m) !important;
    color: var(--t1) !important;
    border-radius: var(--rs) !important;
}

/* ── Tabs ── */
[data-testid="stTabs"] [role="tablist"] {
    border-bottom: 1px solid var(--border) !important;
    gap: 0 !important;
}
button[role="tab"] {
    color: var(--t3) !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    padding: 8px 18px !important;
    border-radius: 0 !important;
    border-bottom: 2px solid transparent !important;
    transition: color 0.15s, border-color 0.15s !important;
}
button[role="tab"][aria-selected="true"] {
    color: var(--t1) !important;
    border-bottom-color: var(--green) !important;
    background: transparent !important;
}

/* ── Divider ── */
hr { border-color: var(--border) !important; margin: 12px 0 !important; }

/* ── Animations ── */
@keyframes pulse    { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.35;transform:scale(.8)} }
@keyframes fade-up  { from{opacity:0;transform:translateY(10px)} to{opacity:1;transform:translateY(0)} }
@keyframes scan     { 0%{left:-40%} 100%{left:120%} }
@keyframes glow-ani { 0%,100%{box-shadow:0 0 0 0 var(--glow)} 50%{box-shadow:0 0 0 6px transparent} }

/* ── Sidebar helpers ── */
.sb-lbl {
    display: block;
    font-size: 10px; font-weight: 700;
    letter-spacing: .1em; color: var(--t3);
    text-transform: uppercase; margin: 14px 0 5px;
}
.sb-meta {
    background: var(--glass); border: 1px solid var(--border);
    backdrop-filter: blur(8px); border-radius: var(--rs);
    padding: 10px 13px; margin: 6px 0;
    font-size: 12px; color: var(--t2);
}
.api-row { display:flex; align-items:center; gap:8px; padding:5px 0; }
.api-dot { width:6px; height:6px; border-radius:50%; flex-shrink:0; }
.api-name { font-size:12px; flex:1; color:var(--t2); }
.api-tag  { font-size:10px; color:var(--t3); }

/* ── Radio (ICP selector) ── */
[data-testid="stRadio"] > div { flex-direction:column; gap:4px; }
[data-testid="stRadio"] label {
    background: var(--glass);
    border: 1px solid var(--border);
    border-radius: var(--rs);
    padding: 10px 14px !important;
    cursor: pointer;
    transition: border-color .15s, background .15s;
    font-size: 13px !important;
    backdrop-filter: blur(8px);
}
[data-testid="stRadio"] label:has(input:checked) {
    border-color: rgba(46,188,93,0.45) !important;
    background: rgba(46,188,93,0.06) !important;
}

/* ── Hero ── */
.hero {
    text-align: center;
    padding: 56px 20px 44px;
    animation: fade-up .45s ease;
}
.hero-badge {
    display: inline-block;
    padding: 4px 16px;
    margin-bottom: 24px;
    font-size: 10px; font-weight: 700;
    letter-spacing: .18em; text-transform: uppercase;
    color: var(--green);
    background: rgba(46,188,93,0.08);
    border: 1px solid rgba(46,188,93,0.20);
    border-radius: 4px;
}
.hero-title {
    font-size: clamp(28px,4vw,46px);
    font-weight: 700; line-height: 1.12;
    letter-spacing: -.03em; color: var(--t1);
    margin: 0 0 16px;
}
.hero-title span {
    background: linear-gradient(90deg, #ffffff, #2EBC5D);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
.hero-sub {
    font-size: 15px; color: var(--t2);
    line-height: 1.7; font-weight: 300;
    max-width: 480px; margin: 0 auto 48px;
}

/* ── Feature grid ── */
.feat-grid {
    display: grid;
    grid-template-columns: repeat(4,1fr);
    gap: 10px;
    max-width: 820px;
    margin: 0 auto 40px;
}
@media(max-width:680px){ .feat-grid { grid-template-columns: repeat(2,1fr); } }
.feat {
    background: var(--glass);
    border: 1px solid var(--border);
    backdrop-filter: blur(16px);
    border-radius: var(--r);
    padding: 20px 16px;
    text-align: left;
    transition: border-color .2s, transform .2s;
}
.feat:hover { border-color: var(--border-h); transform: translateY(-2px); }
.feat-num {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px; font-weight: 500;
    color: var(--green); letter-spacing: .06em;
    margin-bottom: 12px;
}
.feat-name { font-size: 12px; font-weight: 600; color: var(--t1); margin-bottom: 4px; }
.feat-desc { font-size: 11px; color: var(--t3); line-height: 1.55; }

/* ── Tip ── */
.tip {
    display: inline-block;
    background: var(--glass);
    border: 1px solid var(--border);
    backdrop-filter: blur(12px);
    border-radius: var(--r);
    padding: 12px 20px;
    font-size: 13px; color: var(--t3);
    max-width: 560px;
}

/* ── Pipeline ── */
.pl-header {
    display: flex; align-items: center; gap: 12px;
    padding: 13px 18px;
    background: var(--glass);
    border: 1px solid var(--border-m);
    backdrop-filter: blur(12px);
    border-radius: var(--r);
    margin-bottom: 14px;
    animation: fade-up .3s ease;
}
.live-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--green);
    animation: pulse 1.4s infinite;
    flex-shrink: 0;
}
.pl-stage { font-size: 14px; font-weight: 600; flex: 1; }
.pl-meta  { font-size: 11px; color: var(--t3); }

/* ── Source cards ── */
.sources { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
.src {
    display: flex; align-items: center; gap: 12px;
    background: var(--glass);
    border: 1px solid var(--border);
    backdrop-filter: blur(12px);
    border-radius: var(--rs); padding: 11px 16px;
    transition: border-color .3s;
    position: relative; overflow: hidden;
}
.src.running { border-color: rgba(46,188,93,0.35); animation: glow-ani 2s infinite; }
.src.done    { border-color: rgba(46,188,93,0.25); }
.src.skip    { opacity: .4; }
.src.warn    { border-color: rgba(245,158,11,0.25); }
.scan-line {
    position: absolute; top: 0; left: 0; width: 38%; height: 100%;
    background: linear-gradient(90deg, transparent, rgba(46,188,93,0.06), transparent);
    animation: scan 2s linear infinite;
}
.src-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.src-dot.pending { background: var(--t3); }
.src-dot.running { background: var(--green); animation: pulse .9s infinite; }
.src-dot.done    { background: var(--green); }
.src-dot.skip    { background: var(--t3); }
.src-dot.warn    { background: var(--amber); }
.src-lbl  { font-size: 13px; font-weight: 500; flex: 1; }
.src-badge { font-size: 10px; font-weight: 700; padding: 2px 9px; border-radius: 99px; }
.src-badge.done { background: rgba(46,188,93,0.10); color: var(--green); }
.src-badge.warn { background: var(--amber-bg); color: var(--amber); }
.src-note  { font-size: 11px; color: var(--t3); }

/* ── Progress block ── */
.prog-block {
    background: var(--glass);
    border: 1px solid var(--border);
    backdrop-filter: blur(12px);
    border-radius: var(--r);
    padding: 15px 18px; margin-bottom: 12px;
}
.prog-lbl {
    font-size: 10px; font-weight: 700;
    letter-spacing: .09em; color: var(--t3);
    text-transform: uppercase; margin-bottom: 8px;
}
.prog-company {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px; color: var(--t3);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    margin-top: 8px;
}

/* ── Score feed ── */
.feed-hdr {
    font-size: 10px; font-weight: 700;
    letter-spacing: .09em; color: var(--t3);
    text-transform: uppercase; margin: 14px 0 7px;
}
.feed-item {
    display: flex; align-items: center; gap: 10px;
    padding: 7px 0; border-bottom: 1px solid var(--border);
    animation: fade-up .25s ease;
}
.feed-co  { font-size: 12px; color: var(--t2); flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.feed-bar-bg { width: 68px; height: 3px; background: var(--border); border-radius: 99px; overflow: hidden; }
.feed-bar    { height: 100%; border-radius: 99px; }
.feed-num    { font-size: 11px; font-weight: 700; width: 24px; text-align: right; }
.feed-q      { font-size: 9px; font-weight: 700; padding: 2px 7px; border-radius: 99px; letter-spacing: .04em; }
.feed-q.yes  { background: rgba(46,188,93,0.10); color: var(--green); }
.feed-q.no   { background: rgba(71,85,105,.18); color: var(--t3); }

/* ── Results header ── */
.res-header {
    display: flex; align-items: center; gap: 14px;
    padding: 16px 22px;
    background: rgba(46,188,93,0.06);
    border: 1px solid rgba(46,188,93,0.18);
    backdrop-filter: blur(12px);
    border-radius: var(--r);
    margin-bottom: 24px;
    animation: fade-up .3s ease;
}
.res-check {
    width: 32px; height: 32px; border-radius: 8px;
    background: rgba(46,188,93,0.12);
    border: 1px solid rgba(46,188,93,0.25);
    flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
}
.res-check-inner {
    width: 14px; height: 10px;
    border-left: 2px solid var(--green);
    border-bottom: 2px solid var(--green);
    transform: rotate(-45deg) translate(1px, -2px);
}
.res-title { font-size: 15px; font-weight: 700; }
.res-sub   { font-size: 12px; color: var(--t2); margin-top: 2px; }

/* ── Lead cards ── */
.lead-card {
    background: var(--glass);
    border: 1px solid var(--border);
    backdrop-filter: blur(16px);
    border-radius: var(--r); overflow: hidden;
    margin: 10px 0; animation: fade-up .3s ease;
    transition: border-color .2s;
}
.lead-card:hover { border-color: var(--border-h); }
.lead-stripe { height: 3px; }
.lead-body   { padding: 18px 22px; }
.lead-top    { display: flex; align-items: flex-start; gap: 12px; margin-bottom: 12px; }
.lead-rank   { font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 500; color: var(--t3); width: 22px; flex-shrink: 0; padding-top: 3px; }
.lead-info   { flex: 1; }
.lead-name   { font-size: 15px; font-weight: 600; color: var(--t1); margin: 0 0 3px; }
.lead-sub    { font-size: 12px; color: var(--t3); }
.lead-score-num   { font-size: 22px; font-weight: 700; line-height: 1; }
.lead-score-label { font-size: 9px; color: var(--t3); text-align: right; letter-spacing: .06em; text-transform: uppercase; margin-top: 2px; }
.lead-bar-bg { height: 3px; background: var(--border); border-radius: 99px; overflow: hidden; margin: 10px 0 14px; }
.lead-bar    { height: 100%; border-radius: 99px; }
.chips       { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.chip {
    display: inline-flex; align-items: center; gap: 5px;
    background: var(--elevated);
    border: 1px solid var(--border);
    border-radius: 99px; padding: 4px 12px;
    font-size: 11px; color: var(--t2);
}
.chip a { color: var(--green) !important; text-decoration: none !important; }
.chip a:hover { text-decoration: underline !important; }
.chip-label { font-size: 9px; font-weight: 700; letter-spacing: .07em; color: var(--t3); text-transform: uppercase; }
.signal-row  { display: flex; align-items: flex-start; gap: 8px; font-size: 12px; color: var(--t2); margin-bottom: 10px; }
.sig-line    { width: 2px; height: 14px; background: var(--green); flex-shrink: 0; border-radius: 1px; margin-top: 2px; }
.sig-line.amber { background: var(--amber); }
.pitch-box {
    background: rgba(0, 59, 92, 0.20);
    border: 1px solid rgba(46,188,93,0.18);
    border-left: 2px solid var(--green);
    padding: 12px 16px;
    border-radius: 0 var(--rs) var(--rs) 0;
    font-size: 13px; color: var(--t2);
    font-style: italic; line-height: 1.7;
}

/* ── Hide Streamlit chrome ── */
#MainMenu, footer,
[data-testid="stToolbar"],
[data-testid="stDecoration"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────
def _init_state():
    for k, v in {
        "app_state": "idle",
        "run_config": {},
        "final_leads": [],
        "output_path": None,
        "stats": {},
        "pipeline_error": None,
    }.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# ── Score helpers ─────────────────────────────────────────────────────────────

def _score_color(score: int) -> str:
    if score >= 80: return "#2EBC5D"
    if score >= 60: return "#F59E0B"
    return "#475569"


def _src_card_html(label: str, status: str, count: int = 0, reason: str = "") -> str:
    scan = '<div class="scan-line"></div>' if status == "running" else ""
    status_text = {
        "pending": "waiting",
        "running": "scanning",
        "done":    f"{count:,} signals",
        "skip":    reason or "no key — skipped",
        "warn":    reason or "limited results",
    }.get(status, status)
    badge = ""
    if status == "done" and count:
        badge = f'<span class="src-badge done">{count}</span>'
    elif status == "warn" and count:
        badge = f'<span class="src-badge warn">{count}</span>'
    return f"""
    <div class="src {status}">
        {scan}
        <div class="src-dot {status}"></div>
        <span class="src-lbl">{label}</span>
        {badge}
        <span class="src-note">{status_text}</span>
    </div>"""


def _score_bar_html(score: int) -> str:
    color = _score_color(score)
    return f"""
    <div class="lead-bar-bg">
        <div class="lead-bar" style="width:{score}%;background:{color};"></div>
    </div>"""


def _lead_card_html(rank: int, lead: dict) -> str:
    score  = lead.get("total_score", 0)
    color  = _score_color(score)
    name   = lead.get("company_name", "—")
    web    = lead.get("website", "")
    src    = lead.get("source", "")
    vrt    = lead.get("vertical", "")
    signal = lead.get("primary_signal", "")
    pain   = lead.get("pain_point", "")
    pitch  = lead.get("opening_line", "")
    cname  = lead.get("contact_name", "")
    ctitle = lead.get("contact_title", "")
    email  = lead.get("email", "")
    li_url = lead.get("linkedin_url", "")

    chips = ""
    if cname and "Manual" not in cname:
        label = f'{cname}{"  ·  " + ctitle if ctitle and "Manual" not in ctitle else ""}'
        chips += f'<span class="chip"><span class="chip-label">contact</span>{label}</span>'
    if email and "Manual" not in email:
        chips += f'<span class="chip"><span class="chip-label">email</span>{email}</span>'
    if li_url and "Manual" not in li_url:
        chips += f'<span class="chip"><a href="{li_url}" target="_blank">LinkedIn profile</a></span>'
    if web and web.startswith("http"):
        domain = web.split("//")[-1].split("/")[0].replace("www.", "")
        chips += f'<span class="chip"><a href="{web}" target="_blank">{domain}</a></span>'
    if src:
        chips += f'<span class="chip"><span class="chip-label">via</span>{src}</span>'

    signal_html = f'<div class="signal-row"><div class="sig-line amber"></div><span><b>Signal — </b>{signal}</span></div>' if signal else ""
    pain_html   = f'<div class="signal-row"><div class="sig-line"></div><span><b>Pain point — </b>{pain}</span></div>' if pain else ""
    pitch_html  = f'<div class="pitch-box">{pitch}</div>' if pitch else ""

    return f"""
    <div class="lead-card">
        <div class="lead-stripe" style="background:{color};"></div>
        <div class="lead-body">
            <div class="lead-top">
                <div class="lead-rank">0{rank}</div>
                <div class="lead-info">
                    <div class="lead-name">{name}</div>
                    <div class="lead-sub">{vrt}</div>
                </div>
                <div style="text-align:right;">
                    <div class="lead-score-num" style="color:{color};">{score}</div>
                    <div class="lead-score-label">/ 100</div>
                </div>
            </div>
            {_score_bar_html(score)}
            <div class="chips">{chips}</div>
            {signal_html}
            {pain_html}
            {pitch_html}
        </div>
    </div>"""


# ── Sidebar ───────────────────────────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        # Brand mark
        st.markdown("""
        <div style="padding:0 4px 16px;">
            <div style="font-size:15px;font-weight:700;color:#f8fafc;letter-spacing:-.01em;">
                Focus Chain Labs
            </div>
            <div style="font-size:10px;color:#475569;letter-spacing:.12em;text-transform:uppercase;margin-top:2px;">
                Lead Generation Agent
            </div>
        </div>""", unsafe_allow_html=True)
        st.divider()

        # ICP selector
        st.markdown('<span class="sb-lbl">Client ICP</span>', unsafe_allow_html=True)
        config_files = sorted(glob.glob("config/*.json"))
        if not config_files:
            st.error("No config files found in /config/")
            return None

        config_labels = {
            f.split("/")[-1].replace(".json", "").replace("_", " ").title(): f
            for f in config_files
        }
        selected_label = st.radio("ICP", list(config_labels.keys()), label_visibility="collapsed")
        selected_config_path = config_labels[selected_label]

        with open(selected_config_path) as _f:
            icp_preview = json.load(_f)

        st.markdown(f"""
        <div class="sb-meta">
            <span style="color:#f8fafc;font-weight:600;">{icp_preview.get('client','')}</span>
            <span style="color:#475569;"> · {icp_preview.get('vertical','')}</span><br>
            <span style="color:#475569;font-size:11px;">{', '.join(icp_preview.get('locations',[]))}</span>
        </div>""", unsafe_allow_html=True)

        st.divider()

        # Prompt field — Notion / Claude style
        st.markdown("""
        <div style="font-size:12px;font-weight:500;color:#94a3b8;margin-bottom:6px;letter-spacing:.01em;">
            Describe what you are looking for
        </div>""", unsafe_allow_html=True)
        custom_focus = st.text_area(
            "focus",
            placeholder="Manufacturing companies in Bangalore that recently hired a new CTO and are upgrading their ERP infrastructure...",
            height=110,
            label_visibility="collapsed",
            help="Plain language context — Gemini weighs this heavily when scoring each lead.",
        )

        # Industry filter
        st.markdown('<span class="sb-lbl">Target industries</span>', unsafe_allow_html=True)
        all_industries = icp_preview.get("target_industries", [])
        selected_industries = st.multiselect(
            "Industries", options=all_industries,
            default=all_industries, label_visibility="collapsed"
        )

        # Location
        st.markdown('<span class="sb-lbl">Location</span>', unsafe_allow_html=True)
        location_val = st.text_input(
            "Location",
            value=", ".join(icp_preview.get("locations", ["Bangalore"])),
            label_visibility="collapsed"
        )

        st.divider()

        col1, col2 = st.columns(2)
        with col1:
            st.markdown('<span class="sb-lbl">Max leads</span>', unsafe_allow_html=True)
            max_leads = st.number_input("Max Leads", min_value=1, max_value=50,
                                        value=10, label_visibility="collapsed")
        with col2:
            st.markdown('<span class="sb-lbl">Min score</span>', unsafe_allow_html=True)
            min_score = st.number_input("Min Score", min_value=0, max_value=99,
                                        value=int(os.getenv("MIN_SCORE_THRESHOLD", 60)),
                                        label_visibility="collapsed")

        with st.expander("Advanced"):
            exclusion_file = st.file_uploader(
                "Exclusion list (Excel)",
                type=["xlsx"],
                help="Companies already contacted — skipped automatically."
            )

        with st.expander("API status"):
            for name, key, required in [
                ("Gemini",    "GEMINI_API_KEY",    True),
                ("Serper",    "SERPER_API_KEY",    True),
                ("Apollo",    "APOLLO_API_KEY",    True),
                ("ProxyCurl", "PROXYCURL_API_KEY", False),
                ("Tracxn",    "TRACXN_API_KEY",    False),
            ]:
                has_key   = bool(os.getenv(key))
                dot_color = "#2EBC5D" if has_key else "#EF4444" if required else "#F59E0B"
                tag       = "" if has_key else ("required" if required else "optional")
                st.markdown(f"""
                <div class="api-row">
                    <div class="api-dot" style="background:{dot_color};"></div>
                    <span class="api-name">{name}</span>
                    <span class="api-tag">{tag}</span>
                </div>""", unsafe_allow_html=True)

        st.divider()

        is_running  = st.session_state.app_state == "running"
        run_label   = "Running..." if is_running else "Run Agent"
        run_clicked = st.button(run_label, use_container_width=True,
                                disabled=is_running, type="primary")

        if run_clicked and not is_running:
            exclusion_path = None
            if exclusion_file:
                exclusion_path = "output/exclusion_upload.xlsx"
                with open(exclusion_path, "wb") as _ef:
                    _ef.write(exclusion_file.read())

            os.environ["MIN_SCORE_THRESHOLD"] = str(int(min_score))

            st.session_state.run_config = {
                "icp_config_path":    selected_config_path,
                "exclusion_list_path": exclusion_path,
                "max_leads":          int(max_leads),
                "override_industries": selected_industries or all_industries,
                "custom_focus":       custom_focus.strip() if custom_focus else None,
            }
            st.session_state.app_state    = "running"
            st.session_state.pipeline_error = None
            st.rerun()

        if st.session_state.app_state == "done":
            if st.button("New Run", use_container_width=True):
                st.session_state.app_state    = "idle"
                st.session_state.final_leads  = []
                st.session_state.output_path  = None
                st.session_state.stats        = {}
                st.rerun()

    return selected_config_path


# ── Idle view ─────────────────────────────────────────────────────────────────

def render_idle():
    st.markdown("""
    <div class="hero">
        <div class="hero-badge">Connected Intelligence</div>
        <h1 class="hero-title">Find companies<br><span>ready to move now</span></h1>
        <p class="hero-sub">
            Signal detection across four live sources. AI scoring across four dimensions.
            One ranked file with the right person and the right opening line.
        </p>
        <div class="feat-grid">
            <div class="feat">
                <div class="feat-num">01 — Signal detection</div>
                <div class="feat-name">Four live sources</div>
                <div class="feat-desc">Google, Tracxn, LinkedIn jobs, and Naukri scanned in sequence for buying signals</div>
            </div>
            <div class="feat">
                <div class="feat-num">02 — AI scoring</div>
                <div class="feat-name">Gemini 3.5 Flash</div>
                <div class="feat-desc">Fit, trigger, reachability, and recency scored independently per company</div>
            </div>
            <div class="feat">
                <div class="feat-num">03 — Contact enrichment</div>
                <div class="feat-name">Apollo lookup</div>
                <div class="feat-desc">Verified email and title for the most senior reachable decision maker</div>
            </div>
            <div class="feat">
                <div class="feat-num">04 — Outreach</div>
                <div class="feat-name">Personalised lines</div>
                <div class="feat-desc">One specific opening line per lead — written from your company's voice, not a template</div>
            </div>
        </div>
        <div class="tip">
            Select a client ICP in the sidebar, describe what you are looking for, and click Run Agent
        </div>
    </div>
    """, unsafe_allow_html=True)


# ── Pipeline view (live) ──────────────────────────────────────────────────────

def render_pipeline_live():
    from main import run_pipeline_streaming

    cfg = st.session_state.run_config

    header_ph   = st.empty()
    sources_ph  = st.empty()
    progress_ph = st.empty()
    feed_ph     = st.empty()

    ps = {
        "stage": "search",
        "sources": {
            "serper":    {"label": "Google Search (Serper)",     "status": "pending", "count": 0, "reason": ""},
            "tracxn":    {"label": "Tracxn — Funded Startups",   "status": "pending", "count": 0, "reason": ""},
            "proxycurl": {"label": "LinkedIn Jobs (ProxyCurl)",  "status": "pending", "count": 0, "reason": ""},
            "naukri":    {"label": "Naukri Job Board",           "status": "pending", "count": 0, "reason": ""},
        },
        "research_idx": 0, "research_total": 0,
        "score_idx":    0, "score_total":    0,
        "enrich_idx":   0, "enrich_total":   0,
        "pitch_idx":    0, "pitch_total":    0,
        "current_company": "",
        "feed_items": [],
    }

    STAGE_LABELS = {
        "search":   "01 — Scanning signal sources",
        "research": "02 — Researching companies",
        "score":    "03 — Scoring with Gemini 3.5 Flash",
        "enrich":   "04 — Finding decision makers",
        "pitch":    "05 — Writing personalised opening lines",
    }

    pilot = os.getenv("PILOT_MODE", "true").lower() == "true"
    pilot_tag = '<span class="pl-meta">pilot mode</span>' if pilot else ""

    def _header():
        header_ph.markdown(f"""
        <div class="pl-header">
            <div class="live-dot"></div>
            <span class="pl-stage">{STAGE_LABELS.get(ps["stage"], ps["stage"])}</span>
            {pilot_tag}
        </div>""", unsafe_allow_html=True)

    def _sources():
        html = '<div class="sources">'
        for sid, src in ps["sources"].items():
            html += _src_card_html(src["label"], src["status"], src["count"], src["reason"])
        html += "</div>"
        sources_ph.markdown(html, unsafe_allow_html=True)

    def _progress():
        stage = ps["stage"]
        idx_map = {
            "research": (ps["research_idx"], ps["research_total"], "Researching"),
            "score":    (ps["score_idx"],    ps["score_total"],    "Scoring"),
            "enrich":   (ps["enrich_idx"],   ps["enrich_total"],   "Enriching contacts"),
            "pitch":    (ps["pitch_idx"],    ps["pitch_total"],    "Writing opening lines"),
        }
        if stage not in idx_map:
            progress_ph.empty()
            return
        idx, total, lbl = idx_map[stage]
        with progress_ph.container():
            st.markdown(f'<div class="prog-block"><div class="prog-lbl">{lbl}</div>', unsafe_allow_html=True)
            st.progress(idx / max(total, 1))
            st.markdown(
                f'<div class="prog-company">{ps["current_company"]}'
                f'<span style="float:right;">{idx} / {total}</span></div></div>',
                unsafe_allow_html=True
            )

    def _feed():
        items = ps["feed_items"]
        if not items:
            feed_ph.empty()
            return
        html = '<div class="feed-hdr">Scoring feed</div>'
        for item in items[-8:]:
            sc = item.get("score", 0)
            cl = _score_color(sc)
            qc = "yes" if item.get("qualify") else "no"
            qt = "QF" if item.get("qualify") else "NQ"
            html += f"""
            <div class="feed-item">
                <span class="feed-co">{item["company"]}</span>
                <div class="feed-bar-bg"><div class="feed-bar" style="width:{sc}%;background:{cl};"></div></div>
                <span class="feed-num" style="color:{cl};">{sc}</span>
                <span class="feed-q {qc}">{qt}</span>
            </div>"""
        feed_ph.markdown(html, unsafe_allow_html=True)

    _header()
    _sources()

    try:
        for event in run_pipeline_streaming(**cfg):
            t = event.get("type", "")

            if t == "source_start":
                src = event.get("source", "")
                if src in ps["sources"]:
                    ps["sources"][src]["status"] = "running"
                _sources()

            elif t == "source_done":
                src = event.get("source", "")
                if src in ps["sources"]:
                    ps["sources"][src].update({
                        "status": event.get("status", "done"),
                        "count":  event.get("count", 0),
                        "reason": event.get("reason", ""),
                    })
                _sources()

            elif t == "stage_start":
                stage = event.get("stage", "")
                ps["stage"] = stage
                total = event.get("total", 0)
                if stage == "research": ps["research_total"] = total
                if stage == "score":    ps["score_total"]    = total
                if stage == "enrich":   ps["enrich_total"]   = total
                if stage == "pitch":    ps["pitch_total"]    = total
                _header()
                _progress()

            elif t == "research_progress":
                ps["research_idx"]    = event.get("idx", 0)
                ps["current_company"] = event.get("company", "")
                _progress()

            elif t == "score_progress":
                ps["score_idx"]       = event.get("idx", 0)
                ps["current_company"] = event.get("company", "")
                _progress()

            elif t == "score_result":
                ps["feed_items"].append(event)
                _feed()

            elif t == "enrich_progress":
                ps["enrich_idx"]      = event.get("idx", 0)
                ps["current_company"] = event.get("company", "")
                _progress()

            elif t == "pitch_progress":
                ps["pitch_idx"]       = event.get("idx", 0)
                ps["current_company"] = event.get("company", "")
                _progress()

            elif t == "final":
                st.session_state.final_leads   = event.get("leads", [])
                st.session_state.output_path   = event.get("output_path")
                st.session_state.stats         = event.get("stats", {})
                err = event.get("error")
                if err:
                    st.session_state.pipeline_error = err
                break

    except Exception as exc:
        st.session_state.pipeline_error = str(exc)

    st.session_state.app_state = "done"
    header_ph.empty()
    sources_ph.empty()
    progress_ph.empty()
    feed_ph.empty()
    st.rerun()


# ── Results view ──────────────────────────────────────────────────────────────

def render_results():
    leads = st.session_state.final_leads
    path  = st.session_state.output_path
    stats = st.session_state.stats
    error = st.session_state.pipeline_error

    if error:
        st.error(f"Pipeline error: {error}")
        return

    if not leads:
        st.warning("No qualified leads found. Lower the Min Score threshold or add API keys.")
        return

    n     = stats.get("total_leads", len(leads))
    avg   = stats.get("avg_score", 0)
    top   = stats.get("top_score", 0)
    qrate = stats.get("qualification_rate", "—")

    st.markdown(f"""
    <div class="res-header">
        <div class="res-check"><div class="res-check-inner"></div></div>
        <div>
            <div class="res-title">Pipeline complete — {n} lead{'s' if n != 1 else ''} ready</div>
            <div class="res-sub">Avg score {avg} &nbsp;·&nbsp; Top score {top} &nbsp;·&nbsp; Qualification rate {qrate}</div>
        </div>
    </div>""", unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Leads found",      n)
    c2.metric("Avg score",        avg)
    c3.metric("Top score",        top)
    c4.metric("Qualification rate", qrate)

    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

    tab_cards, tab_table, tab_dl = st.tabs(["Lead Cards", "Table View", "Download"])

    with tab_cards:
        for i, lead in enumerate(leads, 1):
            st.markdown(_lead_card_html(i, lead), unsafe_allow_html=True)

    with tab_table:
        if leads:
            df = pd.read_excel(path) if path and os.path.exists(path) else pd.DataFrame(leads)
            view_cols = [c for c in [
                "Rank", "Company", "Total Score", "Contact Name",
                "Contact Title", "Email", "Primary Signal", "Opening Line"
            ] if c in df.columns]
            st.dataframe(df[view_cols] if view_cols else df, use_container_width=True)

    with tab_dl:
        if path and os.path.exists(path):
            with open(path, "rb") as _f:
                data = _f.read()
            st.download_button(
                label="Download Excel",
                data=data,
                file_name=os.path.basename(path),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
            st.markdown(
                f'<div style="font-size:11px;color:var(--t3);margin-top:8px;">'
                f'{path} &nbsp;·&nbsp; {round(len(data)/1024, 1)} KB</div>',
                unsafe_allow_html=True
            )


# ── Router ────────────────────────────────────────────────────────────────────

def main():
    render_sidebar()
    state = st.session_state.app_state
    if state == "idle":
        render_idle()
    elif state == "running":
        render_pipeline_live()
    elif state == "done":
        render_results()


main()
