"""
FocusChain LeadGen — main UI
Cream / ink / green brand · 3-stage flow · live agent pipeline.
"""

from __future__ import annotations
import os
import json
import glob
import time
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

# ── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FocusChain Labs — LeadGen",
    page_icon="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><circle cx='50' cy='50' r='38' fill='%232E8B4D'/></svg>",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Brand CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,500;12..96,600;12..96,700;12..96,800&family=JetBrains+Mono:wght@400;500;700&display=swap');

:root {
    --cream:     #F4F0E7;
    --cream-2:   #EFEADE;
    --cream-3:   #FBFAF7;
    --ink:       #0F2A33;
    --ink-soft:  #3C5158;
    --ink-mute:  #5A6E75;
    --green:     #2E8B4D;
    --green-br:  #37A85C;
    --green-bg:  rgba(46,139,77,.08);
    --green-bg2: rgba(46,139,77,.14);
    --line:      rgba(15,42,51,.16);
    --line-soft: rgba(15,42,51,.08);
    --line-mid:  rgba(15,42,51,.22);
    --amber:     #B7791F;
    --amber-bg:  rgba(183,121,31,.10);
    --red:       #A93D3D;
    --red-bg:    rgba(169,61,61,.10);
    --rs:        8px;
    --r:         12px;
    --rl:        18px;
}

/* ── Reset ── */
html, body { margin: 0; padding: 0; }

/* ── App base — cream + paper grain ── */
.stApp {
    background-color: var(--cream) !important;
    color: var(--ink) !important;
    font-family: 'Bricolage Grotesque', -apple-system, sans-serif !important;
}
.stApp::before {
    content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 0;
    background:
      radial-gradient(120% 90% at 50% 0%, rgba(255,255,255,.55), transparent 60%),
      radial-gradient(130% 110% at 50% 110%, rgba(15,42,51,.06), transparent 55%);
}
.stApp::after {
    content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 0;
    opacity: .45; mix-blend-mode: multiply;
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='140' height='140'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2'/><feColorMatrix type='saturate' values='0'/></filter><rect width='140' height='140' filter='url(%23n)' opacity='0.045'/></svg>");
}
.block-container {
    padding-top: 28px !important;
    padding-bottom: 80px !important;
    max-width: 1040px !important;
    position: relative; z-index: 1;
}

/* hide collapsed sidebar visually */
[data-testid="stSidebar"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }
header[data-testid="stHeader"] {
    background: transparent !important;
    height: 0 !important;
}

/* ── Typography ── */
h1, h2, h3, h4, h5, h6, p, div, span, label {
    font-family: 'Bricolage Grotesque', sans-serif !important;
    color: var(--ink);
}
.mono { font-family: 'JetBrains Mono', monospace !important; }

/* ── Eyebrow ── */
.eyebrow {
    display: inline-flex; align-items: center; gap: 14px;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 11px; font-weight: 500;
    letter-spacing: .42em; text-transform: uppercase;
    color: var(--green);
    animation: fadeUp .7s ease .1s both;
}
.eyebrow .dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--green);
    box-shadow: 0 0 0 4px rgba(46,139,77,.16);
}
.eyebrow .dash {
    width: 28px; height: 1.5px; background: var(--green);
}

/* ── Wordmark ── */
.wordmark {
    margin: 18px 0 8px;
    font-weight: 800;
    font-size: clamp(38px, 6vw, 64px);
    letter-spacing: -.035em;
    line-height: .96;
    color: var(--ink);
}
.wordmark .accent { color: var(--green); }
.wordmark span {
    display: inline-block; overflow: hidden; vertical-align: bottom;
}
.wordmark span i {
    font-style: normal; display: inline-block;
    transform: translateY(110%);
    animation: rise .9s cubic-bezier(.16,1,.3,1) forwards;
}
.wordmark .w2 i { animation-delay: .14s; }

.tagline {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 13px; color: var(--ink-soft);
    letter-spacing: .04em;
    animation: fadeUp .7s ease .5s both;
}

/* ── Stage rail (step indicator) ── */
.steps {
    display: flex; align-items: center; gap: 14px;
    margin: 26px 0 38px;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 11px; font-weight: 600;
    letter-spacing: .18em; text-transform: uppercase;
    color: var(--ink-mute);
}
.steps .num {
    display: inline-block; width: 22px; height: 22px;
    border-radius: 50%; border: 1.5px solid var(--line-mid);
    text-align: center; line-height: 19px;
    margin-right: 8px;
    background: var(--cream-3); color: var(--ink-soft);
}
.steps .step.active .num {
    background: var(--ink); color: var(--cream); border-color: var(--ink);
}
.steps .step.done .num {
    background: var(--green); color: #fff; border-color: var(--green);
}
.steps .step.active { color: var(--ink); }
.steps .step.done { color: var(--green); }
.steps .seg {
    flex: 1; height: 1.5px; background: var(--line-soft);
    position: relative; overflow: hidden;
}
.steps .seg.done { background: var(--green); }

/* ── Card surfaces ── */
.card {
    background: var(--cream-3);
    border: 1px solid var(--line-soft);
    border-radius: var(--r);
    padding: 24px 26px;
    margin-bottom: 14px;
    transition: border-color .25s ease, transform .25s ease;
}
.card:hover { border-color: var(--line); }
.card-hd {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 10.5px; font-weight: 600;
    letter-spacing: .22em; text-transform: uppercase;
    color: var(--green); margin-bottom: 6px;
}
.card-ti {
    font-size: 16px; font-weight: 700;
    color: var(--ink); margin-bottom: 4px;
}
.card-sb {
    font-size: 13px; color: var(--ink-soft);
    line-height: 1.55;
}

/* ── Section title ── */
.sec-ti {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 11px; font-weight: 600;
    letter-spacing: .22em; text-transform: uppercase;
    color: var(--ink-soft);
    margin: 26px 0 12px;
    display: flex; align-items: center; gap: 10px;
}
.sec-ti .bar {
    flex: 1; height: 1px; background: var(--line-soft);
}

/* ── Streamlit overrides ── */
/* Primary button — ink filled */
.stButton > button {
    background: var(--ink) !important;
    color: var(--cream) !important;
    border: 1.5px solid var(--ink) !important;
    border-radius: var(--rs) !important;
    font-family: 'Bricolage Grotesque', sans-serif !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    letter-spacing: .01em !important;
    padding: 12px 24px !important;
    transition: all .2s ease !important;
    box-shadow: 0 1px 0 rgba(15,42,51,.06) !important;
}
.stButton > button:hover {
    background: var(--green) !important;
    border-color: var(--green) !important;
    transform: translateY(-1px);
    box-shadow: 0 6px 18px rgba(46,139,77,.20) !important;
}
.stButton > button:focus, .stButton > button:active {
    background: var(--green-br) !important;
    border-color: var(--green-br) !important;
    box-shadow: 0 0 0 3px rgba(46,139,77,.18) !important;
}

/* Form labels */
.stTextArea label, .stTextInput label, .stMultiSelect label,
.stSelectbox label, .stSlider label, .stRadio label {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 10.5px !important; font-weight: 600 !important;
    letter-spacing: .22em !important; text-transform: uppercase !important;
    color: var(--ink-soft) !important;
}

/* Text area — Notion / Claude style */
.stTextArea textarea {
    background: var(--cream-3) !important;
    color: var(--ink) !important;
    border: 1.5px solid var(--line-soft) !important;
    border-radius: var(--r) !important;
    padding: 18px 20px !important;
    font-family: 'Bricolage Grotesque', sans-serif !important;
    font-size: 15.5px !important;
    line-height: 1.65 !important;
    caret-color: var(--green) !important;
    transition: border-color .2s ease, box-shadow .2s ease, background .2s ease !important;
    resize: none !important;
    box-shadow: none !important;
}
.stTextArea textarea:focus {
    border-color: var(--green) !important;
    background: #fff !important;
    box-shadow: 0 0 0 4px rgba(46,139,77,.10) !important;
    outline: none !important;
}
.stTextArea textarea::placeholder {
    color: var(--ink-mute) !important;
    font-style: italic !important;
    font-weight: 300 !important;
    opacity: .75 !important;
}
.stTextArea > div { border: none !important; background: transparent !important; }

/* Text inputs */
.stTextInput input {
    background: var(--cream-3) !important;
    color: var(--ink) !important;
    border: 1.5px solid var(--line-soft) !important;
    border-radius: var(--rs) !important;
    padding: 10px 14px !important;
    font-family: 'Bricolage Grotesque', sans-serif !important;
    font-size: 14px !important;
    transition: border-color .2s, box-shadow .2s !important;
}
.stTextInput input:focus {
    border-color: var(--green) !important;
    box-shadow: 0 0 0 3px rgba(46,139,77,.10) !important;
}

/* Selectbox + Multiselect */
.stSelectbox > div > div, .stMultiSelect > div > div {
    background: var(--cream-3) !important;
    border: 1.5px solid var(--line-soft) !important;
    border-radius: var(--rs) !important;
    color: var(--ink) !important;
}
.stMultiSelect [data-baseweb="tag"] {
    background: var(--green-bg) !important;
    color: var(--green) !important;
    border: 1px solid var(--green-bg2) !important;
    border-radius: 6px !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 11px !important;
    font-weight: 600 !important;
}
.stMultiSelect [data-baseweb="tag"] span { color: var(--green) !important; }

/* Slider */
.stSlider [role="slider"] { background: var(--green) !important; }
.stSlider [data-baseweb="slider"] > div > div > div {
    background: var(--green) !important;
}

/* Radio buttons (industry pills) */
.stRadio > div { gap: 10px !important; }
.stRadio label {
    background: var(--cream-3) !important;
    border: 1.5px solid var(--line-soft) !important;
    border-radius: var(--rs) !important;
    padding: 10px 16px !important;
    transition: all .2s !important;
    cursor: pointer !important;
}
.stRadio label:hover {
    border-color: var(--green) !important;
    background: var(--green-bg) !important;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    gap: 24px !important;
    border-bottom: 1px solid var(--line-soft) !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: var(--ink-mute) !important;
    border: none !important;
    padding: 8px 0 14px !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 11.5px !important;
    font-weight: 600 !important;
    letter-spacing: .18em !important;
    text-transform: uppercase !important;
}
.stTabs [aria-selected="true"] {
    color: var(--ink) !important;
    border-bottom: 2px solid var(--green) !important;
}

/* Progress bar */
.stProgress > div > div > div {
    background: var(--green) !important;
}
.stProgress > div > div {
    background: var(--line-soft) !important;
    height: 3px !important;
}

/* Expander */
.streamlit-expanderHeader {
    background: var(--cream-3) !important;
    border: 1px solid var(--line-soft) !important;
    border-radius: var(--rs) !important;
    font-family: 'Bricolage Grotesque', sans-serif !important;
    font-size: 14px !important;
    font-weight: 600 !important;
    color: var(--ink) !important;
}
.streamlit-expanderContent {
    background: var(--cream-3) !important;
    border: 1px solid var(--line-soft) !important;
    border-top: none !important;
    border-radius: 0 0 var(--rs) var(--rs) !important;
}

/* Download button is also a stButton */
.stDownloadButton > button { background: var(--green) !important; border-color: var(--green) !important; color: #fff !important; }
.stDownloadButton > button:hover { background: var(--green-br) !important; border-color: var(--green-br) !important; }

/* DataFrame */
.stDataFrame, .stDataFrame [data-testid="stDataFrameResizable"] {
    background: var(--cream-3) !important;
    border-radius: var(--rs) !important;
    border: 1px solid var(--line-soft) !important;
}

/* ── Industry chips (rendered as raw HTML, not Streamlit) ── */
.chip-grid {
    display: flex; flex-wrap: wrap; gap: 8px;
    margin: 8px 0 4px;
}
.chip {
    padding: 8px 14px;
    background: var(--cream-3);
    border: 1.5px solid var(--line-soft);
    border-radius: 999px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11.5px;
    font-weight: 500;
    letter-spacing: .04em;
    color: var(--ink-soft);
    transition: all .2s;
}

/* ── Pipeline (animated SVG-style nodes via CSS) ── */
.pipe-wrap {
    background: var(--cream-3);
    border: 1px solid var(--line-soft);
    border-radius: var(--rl);
    padding: 38px 32px 28px;
    margin: 16px 0 22px;
}
.pipe {
    display: flex; align-items: center; justify-content: space-between;
    position: relative; margin-bottom: 14px;
}
.pipe-track {
    position: absolute; top: 18px; left: 6%; right: 6%; height: 2px;
    background: var(--line-soft); border-radius: 2px;
}
.pipe-flow {
    position: absolute; top: 18px; left: 6%; height: 2px;
    background: var(--green); border-radius: 2px;
    transition: width 1s cubic-bezier(.65,0,.35,1);
}
.pipe-node {
    position: relative; z-index: 2;
    display: flex; flex-direction: column; align-items: center;
    gap: 10px;
    flex: 1; min-width: 0;
}
.pipe-dot {
    width: 38px; height: 38px;
    border-radius: 50%;
    background: var(--cream);
    border: 2px solid var(--line);
    display: flex; align-items: center; justify-content: center;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px; font-weight: 700;
    color: var(--ink-mute);
    transition: all .35s cubic-bezier(.34,1.56,.64,1);
}
.pipe-node.active .pipe-dot {
    background: var(--cream);
    border-color: var(--green);
    color: var(--green);
    transform: scale(1.12);
    box-shadow: 0 0 0 6px rgba(46,139,77,.10);
    animation: pulse 1.4s ease-in-out infinite;
}
.pipe-node.done .pipe-dot {
    background: var(--green); border-color: var(--green); color: #fff;
}
.pipe-lbl {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9.5px; font-weight: 600;
    letter-spacing: .18em; text-transform: uppercase;
    color: var(--ink-mute);
    text-align: center;
}
.pipe-node.active .pipe-lbl { color: var(--green); }
.pipe-node.done .pipe-lbl { color: var(--green); }

/* ── Source feed (live) ── */
.feed {
    background: var(--cream-3);
    border: 1px solid var(--line-soft);
    border-radius: var(--r);
    padding: 14px 18px;
    margin-bottom: 12px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
}
.feed-row {
    display: flex; align-items: center; gap: 12px;
    padding: 6px 0;
    border-bottom: 1px dashed var(--line-soft);
}
.feed-row:last-child { border-bottom: none; }
.feed-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--line); flex-shrink: 0;
}
.feed-dot.run {
    background: var(--green);
    animation: blink 1s ease-in-out infinite;
}
.feed-dot.done { background: var(--green); }
.feed-dot.warn { background: var(--amber); }
.feed-dot.skip { background: var(--line-mid); }
.feed-name {
    flex: 1; color: var(--ink); font-weight: 500;
}
.feed-status {
    color: var(--ink-mute);
    font-size: 11px;
    letter-spacing: .04em;
}
.feed-count {
    font-weight: 700; color: var(--ink);
    background: var(--green-bg);
    padding: 2px 8px; border-radius: 4px;
}

/* ── Score chips ── */
.score-chip {
    display: inline-flex; align-items: center;
    padding: 4px 10px; border-radius: 6px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px; font-weight: 700;
    letter-spacing: .04em;
}
.score-hi { background: var(--green-bg2); color: var(--green); }
.score-mid { background: var(--amber-bg); color: var(--amber); }
.score-lo { background: var(--red-bg); color: var(--red); }

/* ── Lead card ── */
.lead-card {
    background: var(--cream-3);
    border: 1px solid var(--line-soft);
    border-radius: var(--r);
    padding: 22px 24px;
    margin-bottom: 14px;
    transition: all .2s;
}
.lead-card:hover {
    border-color: var(--line);
    transform: translateY(-1px);
    box-shadow: 0 6px 18px rgba(15,42,51,.05);
}
.lead-hd {
    display: flex; align-items: flex-start; justify-content: space-between;
    margin-bottom: 14px; gap: 16px;
}
.lead-name {
    font-size: 18px; font-weight: 700; color: var(--ink);
    margin-bottom: 4px;
}
.lead-meta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px; color: var(--ink-mute);
    letter-spacing: .04em;
}
.lead-signal {
    border-left: 2px solid var(--green);
    padding: 4px 0 4px 14px;
    margin: 10px 0;
    font-size: 13.5px; color: var(--ink); line-height: 1.55;
}
.lead-line {
    background: var(--green-bg);
    border-radius: var(--rs);
    padding: 12px 16px;
    margin-top: 12px;
    font-size: 13.5px;
    font-style: italic;
    color: var(--ink);
    line-height: 1.6;
}
.lead-chips {
    display: flex; flex-wrap: wrap; gap: 8px;
    margin-top: 12px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10.5px;
    color: var(--ink-soft);
}
.lead-chips .k {
    color: var(--ink-mute);
    letter-spacing: .14em;
    text-transform: uppercase;
    margin-right: 4px;
}

/* ── Keyframes ── */
@keyframes fadeUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
@keyframes rise   { to   { transform: translateY(0); } }
@keyframes pulse  { 0%, 100% { box-shadow: 0 0 0 6px rgba(46,139,77,.10); } 50% { box-shadow: 0 0 0 10px rgba(46,139,77,.04); } }
@keyframes blink  { 0%, 100% { opacity: 1; } 50% { opacity: .35; } }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: .01ms !important;
        transition-duration: .01ms !important;
    }
}

/* ── Misc Streamlit cleanups ── */
.stApp [data-testid="stToolbar"] { display: none !important; }
footer { display: none !important; }
#MainMenu { display: none !important; }
hr { border-color: var(--line-soft) !important; margin: 32px 0 !important; }
.element-container { animation: fadeIn .5s ease both; }

/* ── Plan summary chips ── */
.plan-grid {
    display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px;
    margin-top: 14px;
}
.plan-cell {
    background: var(--cream-3);
    border: 1px solid var(--line-soft);
    border-radius: var(--rs);
    padding: 14px 16px;
}
.plan-cell .k {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px; font-weight: 600;
    letter-spacing: .22em; text-transform: uppercase;
    color: var(--green); margin-bottom: 6px;
}
.plan-cell .v {
    font-size: 13px; color: var(--ink); line-height: 1.55;
}
@media (max-width: 720px) { .plan-grid { grid-template-columns: 1fr; } }

/* ── Stats row ── */
.stats {
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
    margin: 10px 0 24px;
}
.stat {
    background: var(--cream-3);
    border: 1px solid var(--line-soft);
    border-radius: var(--r);
    padding: 18px 16px;
    text-align: center;
}
.stat .num {
    font-size: 28px; font-weight: 800; color: var(--ink);
    letter-spacing: -.02em; line-height: 1;
}
.stat .lbl {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9.5px; font-weight: 600;
    letter-spacing: .22em; text-transform: uppercase;
    color: var(--ink-mute);
    margin-top: 8px;
}
@media (max-width: 720px) { .stats { grid-template-columns: repeat(2, 1fr); } }
</style>
""", unsafe_allow_html=True)

# ── Session state ────────────────────────────────────────────────────────────
def _init_state():
    defaults = {
        "stage":         "setup",      # setup → running → results
        "icp_path":      None,
        "industries":    [],
        "locations":     ["Bangalore"],
        "titles":        [],
        "prompt":        "",
        "max_leads":     10,
        "events":        [],
        "leads":         [],
        "output_path":   None,
        "stats":         {},
        "plan":          {},
        "sources":       {},
        "current_stage": None,
        "stage_status":  {},   # stage_name → "running"/"done"
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# ── ICP discovery ────────────────────────────────────────────────────────────
def discover_icps() -> dict:
    icps = {}
    for path in sorted(glob.glob("config/*.json")):
        try:
            with open(path) as f:
                data = json.load(f)
            label = data.get("client") or data.get("vertical") or path
            icps[label] = {"path": path, "data": data}
        except Exception:
            continue
    return icps


ICPS = discover_icps()


# ─────────────────────────────────────────────────────────────────────────────
#                                  HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="eyebrow">
  <span class="dot"></span>
  <span class="dash"></span>
  FOCUSCHAIN LABS · LEAD AGENT
  <span class="dash"></span>
  <span class="dot"></span>
</div>

<h1 class="wordmark">
  <span class="w1"><i>Find companies</i></span><br>
  <span class="w2"><i class="accent">ready to buy</i></span>
</h1>

<p class="tagline">prompt.intake()&nbsp;&nbsp;→&nbsp;&nbsp;signals.scan&nbsp;&nbsp;→&nbsp;&nbsp;outreach.deploy</p>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
#                                STEP RAIL
# ─────────────────────────────────────────────────────────────────────────────
def render_steps(current: str):
    def cls(step_name, order):
        order_map = {"setup": 0, "running": 1, "results": 2}
        cur = order_map.get(current, 0)
        if order < cur: return "step done"
        if order == cur: return "step active"
        return "step"
    st.markdown(f"""
    <div class="steps">
      <div class="{cls('setup', 0)}"><span class="num">1</span>Brief</div>
      <div class="seg {'done' if current != 'setup' else ''}"></div>
      <div class="{cls('running', 1)}"><span class="num">2</span>Agent</div>
      <div class="seg {'done' if current == 'results' else ''}"></div>
      <div class="{cls('results', 2)}"><span class="num">3</span>Leads</div>
    </div>
    """, unsafe_allow_html=True)


render_steps(st.session_state.stage)


# ─────────────────────────────────────────────────────────────────────────────
#                               STAGE 1 · SETUP
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.stage == "setup":

    if not ICPS:
        st.error("No ICP config files found in /config. Add a JSON file there.")
        st.stop()

    # Pick client
    st.markdown('<div class="sec-ti">Client <span class="bar"></span></div>',
                unsafe_allow_html=True)
    client_choice = st.selectbox(
        "client",
        list(ICPS.keys()),
        label_visibility="collapsed",
    )
    base_icp = ICPS[client_choice]["data"]
    st.session_state.icp_path = ICPS[client_choice]["path"]

    # Industries
    all_industries = base_icp.get("target_industries", [])
    st.markdown('<div class="sec-ti">Industries · pick what to target <span class="bar"></span></div>',
                unsafe_allow_html=True)
    industries = st.multiselect(
        "industries",
        options=all_industries,
        default=all_industries,
        label_visibility="collapsed",
    )

    # Demographics row
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown('<div class="sec-ti">Location <span class="bar"></span></div>',
                    unsafe_allow_html=True)
        loc_default = (base_icp.get("locations") or ["Bangalore"])[0]
        location = st.text_input("location",
                                 value=loc_default,
                                 label_visibility="collapsed")
    with col2:
        st.markdown('<div class="sec-ti">Max Leads <span class="bar"></span></div>',
                    unsafe_allow_html=True)
        max_leads = st.slider(
            "max_leads",
            min_value=3, max_value=25, value=10, step=1,
            label_visibility="collapsed",
        )
    with col3:
        st.markdown('<div class="sec-ti">Score Floor <span class="bar"></span></div>',
                    unsafe_allow_html=True)
        threshold = st.slider(
            "threshold",
            min_value=40, max_value=85,
            value=int(os.getenv("MIN_SCORE_THRESHOLD", 60)),
            step=5,
            label_visibility="collapsed",
        )

    # Target titles
    st.markdown('<div class="sec-ti">Decision-maker titles <span class="bar"></span></div>',
                unsafe_allow_html=True)
    titles = st.multiselect(
        "titles",
        options=base_icp.get("target_titles", []),
        default=base_icp.get("target_titles", [])[:6],
        label_visibility="collapsed",
    )

    # Prompt — the Notion/Claude textarea
    st.markdown('<div class="sec-ti">Your brief · what should the agent hunt for? <span class="bar"></span></div>',
                unsafe_allow_html=True)
    prompt = st.text_area(
        "prompt",
        height=160,
        placeholder=(
            "Describe in plain English. The LLM will translate this into the "
            "actual searches.\n\n"
            "e.g. Find Bangalore-based mid-market manufacturers (500-2000 "
            "employees) that hired a new CTO or CIO in the last 90 days and "
            "are publicly discussing legacy ERP pain or cloud migration. "
            "Skip anyone partnered with Infosys, TCS, or Wipro."
        ),
        label_visibility="collapsed",
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # CTA
    cta1, cta2 = st.columns([1, 4])
    with cta1:
        run = st.button("Run Agent", use_container_width=True, type="primary")
    with cta2:
        missing = []
        if not os.getenv("GEMINI_API_KEY"): missing.append("GEMINI_API_KEY")
        if not os.getenv("SERPER_API_KEY"): missing.append("SERPER_API_KEY")
        if missing:
            st.markdown(
                f'<div class="tagline" style="padding-top:10px;color:var(--amber)">'
                f'set {", ".join(missing)} in .env or Streamlit secrets'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="tagline" style="padding-top:10px">'
                'keys detected · ready to run'
                '</div>',
                unsafe_allow_html=True,
            )

    if run:
        if not prompt.strip():
            st.warning("Add a brief — even one sentence — so the planner has something to work with.")
            st.stop()
        os.environ["MAX_LEADS_PER_RUN"] = str(max_leads)
        os.environ["MIN_SCORE_THRESHOLD"] = str(threshold)
        st.session_state.industries = industries
        st.session_state.locations = [location]
        st.session_state.titles = titles
        st.session_state.prompt = prompt.strip()
        st.session_state.max_leads = max_leads
        st.session_state.events = []
        st.session_state.sources = {}
        st.session_state.stage = "running"
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
#                              STAGE 2 · RUNNING
# ─────────────────────────────────────────────────────────────────────────────
elif st.session_state.stage == "running":
    from main import run_pipeline_streaming

    PIPE_STAGES = [
        ("plan",     "Plan"),
        ("search",   "Search"),
        ("research", "Research"),
        ("score",    "Score"),
        ("enrich",   "Enrich"),
        ("pitch",    "Pitch"),
    ]

    def render_pipe(status: dict):
        active_idx = -1
        for i, (k, _) in enumerate(PIPE_STAGES):
            s = status.get(k)
            if s == "running":
                active_idx = i; break
            if s == "done":
                active_idx = i + 1
        active_idx = max(active_idx, 0)
        pct = min(100, int((active_idx / max(len(PIPE_STAGES) - 1, 1)) * 100))

        nodes = ""
        for i, (k, lbl) in enumerate(PIPE_STAGES):
            s = status.get(k)
            klass = ""
            if s == "done": klass = "done"
            elif s == "running": klass = "active"
            nodes += (
                f'<div class="pipe-node {klass}">'
                f'  <div class="pipe-dot">{i+1:02d}</div>'
                f'  <div class="pipe-lbl">{lbl}</div>'
                f'</div>'
            )

        return f"""
        <div class="pipe-wrap">
          <div class="pipe">
            <div class="pipe-track"></div>
            <div class="pipe-flow" style="width:{pct}%"></div>
            {nodes}
          </div>
        </div>
        """

    def render_sources(sources: dict) -> str:
        if not sources:
            return ""
        rows = ""
        for name, info in sources.items():
            status = info.get("status", "run")
            label  = info.get("label", name)
            count  = info.get("count", 0)
            reason = info.get("reason", "")
            ddot = "run"
            if status == "done": ddot = "done"
            elif status == "warn": ddot = "warn"
            elif status == "skip": ddot = "skip"
            status_text = {
                "run":  "scanning…",
                "done": "complete",
                "warn": "warning",
                "skip": "skipped",
            }.get(status, status)
            right = (f'<span class="feed-count">{count}</span>'
                     if status == "done" and count
                     else f'<span class="feed-status">{reason or status_text}</span>')
            rows += (
                f'<div class="feed-row">'
                f'  <span class="feed-dot {ddot}"></span>'
                f'  <span class="feed-name">{label}</span>'
                f'  {right}'
                f'</div>'
            )
        return f'<div class="feed">{rows}</div>'

    def render_progress(events: list) -> str:
        # show last 6 progress events
        progress_types = {"research_progress", "score_progress",
                          "enrich_progress", "pitch_progress",
                          "score_result", "enrich_result"}
        recent = [e for e in events if e.get("type") in progress_types][-6:]
        if not recent:
            return ""
        rows = ""
        for ev in recent:
            t = ev.get("type", "")
            if t == "score_result":
                q = ev.get("qualify", False)
                score = ev.get("score", 0)
                cls = "score-hi" if score >= 80 else "score-mid" if score >= 60 else "score-lo"
                tag = "QUALIFIED" if q else "skipped"
                line = (f'<span class="feed-name">{ev.get("company", "")}</span>'
                        f'<span class="score-chip {cls}">{score}</span>'
                        f'<span class="feed-status">{tag}</span>')
            elif t == "enrich_result":
                line = (f'<span class="feed-name">{ev.get("company", "")}</span>'
                        f'<span class="feed-status">contact {ev.get("status", "")}</span>')
            else:
                idx = ev.get("idx", "?"); total = ev.get("total", "?")
                stage_lbl = t.replace("_progress", "")
                line = (f'<span class="feed-name">{ev.get("company", "")}</span>'
                        f'<span class="feed-status">{stage_lbl} · {idx}/{total}</span>')
            rows += (f'<div class="feed-row">'
                     f'<span class="feed-dot run"></span>{line}</div>')
        return f'<div class="feed" style="margin-top:8px">{rows}</div>'

    # ── Render scaffolding ──
    pipe_slot     = st.empty()
    sources_slot  = st.empty()
    progress_slot = st.empty()
    plan_slot     = st.empty()

    pipe_slot.markdown(render_pipe(st.session_state.stage_status),
                       unsafe_allow_html=True)

    st.markdown('<div class="sec-ti">Live · what the agent is doing <span class="bar"></span></div>',
                unsafe_allow_html=True)

    # Initialise sources with all known so they render in order
    KNOWN_SOURCES = [
        ("serper",    "Google · Serper"),
        ("reddit",    "Reddit · pain signals"),
        ("tracxn",    "Tracxn · funded startups"),
        ("proxycurl", "LinkedIn jobs · ProxyCurl"),
        ("naukri",    "Naukri job board"),
    ]
    for k, lbl in KNOWN_SOURCES:
        if k not in st.session_state.sources:
            st.session_state.sources[k] = {"label": lbl, "status": "pending",
                                           "count": 0, "reason": "queued"}

    sources_slot.markdown(render_sources(st.session_state.sources),
                          unsafe_allow_html=True)

    # ── Run pipeline ──
    try:
        gen = run_pipeline_streaming(
            icp_config_path=st.session_state.icp_path,
            exclusion_list_path=None,
            max_leads=st.session_state.max_leads,
            override_industries=st.session_state.industries or None,
            override_locations=st.session_state.locations or None,
            override_titles=st.session_state.titles or None,
            custom_focus=st.session_state.prompt,
            user_prompt=st.session_state.prompt,
        )

        for ev in gen:
            st.session_state.events.append(ev)
            t = ev.get("type", "")

            if t == "stage_start":
                stage = ev.get("stage")
                # mark previous running as done
                for k, v in st.session_state.stage_status.items():
                    if v == "running":
                        st.session_state.stage_status[k] = "done"
                if stage in [s for s, _ in PIPE_STAGES]:
                    st.session_state.stage_status[stage] = "running"
                # treat the search source phase as the "search" stage too
                pipe_slot.markdown(render_pipe(st.session_state.stage_status),
                                   unsafe_allow_html=True)

            elif t == "stage_done":
                stage = ev.get("stage")
                if stage in [s for s, _ in PIPE_STAGES]:
                    st.session_state.stage_status[stage] = "done"
                pipe_slot.markdown(render_pipe(st.session_state.stage_status),
                                   unsafe_allow_html=True)

            elif t == "source_start":
                # search stage = aggregate of sources
                if st.session_state.stage_status.get("search") != "done":
                    st.session_state.stage_status["search"] = "running"
                k = ev.get("source")
                st.session_state.sources[k] = {
                    **st.session_state.sources.get(k, {}),
                    "label": ev.get("label", k),
                    "status": "run",
                }
                sources_slot.markdown(render_sources(st.session_state.sources),
                                      unsafe_allow_html=True)
                pipe_slot.markdown(render_pipe(st.session_state.stage_status),
                                   unsafe_allow_html=True)

            elif t == "source_done":
                k = ev.get("source")
                st.session_state.sources[k] = {
                    **st.session_state.sources.get(k, {}),
                    "status": ev.get("status", "done"),
                    "count":  ev.get("count", 0),
                    "reason": ev.get("reason", ""),
                }
                sources_slot.markdown(render_sources(st.session_state.sources),
                                      unsafe_allow_html=True)

            elif t == "search_done":
                st.session_state.stage_status["search"] = "done"
                pipe_slot.markdown(render_pipe(st.session_state.stage_status),
                                   unsafe_allow_html=True)

            elif t == "plan_ready":
                st.session_state.plan = ev.get("plan", {})
                plan = ev["plan"]
                plan_slot.markdown(f"""
                <div class="plan-grid">
                  <div class="plan-cell">
                    <div class="k">Industries</div>
                    <div class="v">{", ".join(plan.get("industries", [])[:6])}</div>
                  </div>
                  <div class="plan-cell">
                    <div class="k">Titles</div>
                    <div class="v">{", ".join(plan.get("target_titles", [])[:6])}</div>
                  </div>
                  <div class="plan-cell">
                    <div class="k">Pain hypothesis</div>
                    <div class="v">{plan.get("pain_hypothesis", "") or "—"}</div>
                  </div>
                  <div class="plan-cell">
                    <div class="k">Gap hypothesis</div>
                    <div class="v">{plan.get("gap_hypothesis", "") or "—"}</div>
                  </div>
                </div>
                """, unsafe_allow_html=True)

            elif t in {"research_progress", "score_progress",
                       "enrich_progress", "pitch_progress",
                       "score_result", "enrich_result"}:
                progress_slot.markdown(render_progress(st.session_state.events),
                                       unsafe_allow_html=True)

            elif t == "final":
                st.session_state.leads = ev.get("leads", [])
                st.session_state.output_path = ev.get("output_path")
                st.session_state.stats = ev.get("stats", {})
                st.session_state.plan  = ev.get("plan", st.session_state.plan)
                # mark all done
                for k, _ in PIPE_STAGES:
                    st.session_state.stage_status[k] = "done"
                pipe_slot.markdown(render_pipe(st.session_state.stage_status),
                                   unsafe_allow_html=True)
                st.session_state.stage = "results"
                time.sleep(0.4)
                st.rerun()

    except Exception as e:
        st.error(f"Pipeline error: {e}")
        if st.button("← Back to brief"):
            st.session_state.stage = "setup"
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
#                              STAGE 3 · RESULTS
# ─────────────────────────────────────────────────────────────────────────────
elif st.session_state.stage == "results":

    stats = st.session_state.stats or {}
    leads = st.session_state.leads or []

    st.markdown(f"""
    <div class="stats">
      <div class="stat"><div class="num">{stats.get('total_leads', 0)}</div>
        <div class="lbl">Ranked leads</div></div>
      <div class="stat"><div class="num">{stats.get('qualified_count', 0)}</div>
        <div class="lbl">Qualified</div></div>
      <div class="stat"><div class="num">{stats.get('avg_score', 0)}</div>
        <div class="lbl">Avg score</div></div>
      <div class="stat"><div class="num">{stats.get('qualification_rate', '0%')}</div>
        <div class="lbl">Hit rate</div></div>
    </div>
    """, unsafe_allow_html=True)

    if not leads:
        st.warning("No leads produced. The most common cause is no Serper key, "
                   "or all candidates scored below the threshold. Try lowering "
                   "the floor or refining the brief.")
        if st.button("← New brief"):
            st.session_state.stage = "setup"
            st.session_state.events = []
            st.session_state.sources = {}
            st.session_state.stage_status = {}
            st.rerun()
        st.stop()

    leads_sorted = sorted(leads, key=lambda x: x.get("total_score", 0), reverse=True)

    # ── Download bar ──
    col_a, col_b = st.columns([3, 1])
    with col_a:
        if st.session_state.plan:
            p = st.session_state.plan
            st.markdown(f"""
            <div class="plan-grid">
              <div class="plan-cell">
                <div class="k">Pain hypothesis</div>
                <div class="v">{p.get("pain_hypothesis", "") or "—"}</div>
              </div>
              <div class="plan-cell">
                <div class="k">Gap hypothesis</div>
                <div class="v">{p.get("gap_hypothesis", "") or "—"}</div>
              </div>
            </div>
            """, unsafe_allow_html=True)
    with col_b:
        if st.session_state.output_path and os.path.exists(st.session_state.output_path):
            with open(st.session_state.output_path, "rb") as f:
                st.download_button(
                    label="Download Excel",
                    data=f.read(),
                    file_name=os.path.basename(st.session_state.output_path),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

    # ── Tabs ──
    tab_cards, tab_table = st.tabs(["Lead cards", "Table view"])

    with tab_cards:
        for lead in leads_sorted:
            score = lead.get("total_score", 0)
            cls = "score-hi" if score >= 80 else "score-mid" if score >= 60 else "score-lo"
            opening = lead.get("opening_line", "").strip()
            signal  = lead.get("primary_signal", "").strip()
            pain    = lead.get("pain_point", "").strip()

            chips = []
            cn = lead.get("contact_name", "")
            ct = lead.get("contact_title", "")
            em = lead.get("email", "")
            li = lead.get("linkedin_url", "")
            src = lead.get("source", "")
            if cn and "Manual" not in cn:
                chips.append(f'<span><span class="k">contact</span>{cn}{" · " + ct if ct else ""}</span>')
            if em and "Manual" not in em:
                chips.append(f'<span><span class="k">email</span>{em}</span>')
            if li and "Manual" not in li:
                chips.append(f'<span><span class="k">linkedin</span>{li}</span>')
            if src:
                chips.append(f'<span><span class="k">via</span>{src}</span>')

            st.markdown(f"""
            <div class="lead-card">
              <div class="lead-hd">
                <div>
                  <div class="lead-name">{lead.get("company_name", "")}</div>
                  <div class="lead-meta">{lead.get("website", "") or "—"}</div>
                </div>
                <span class="score-chip {cls}">{score}/100</span>
              </div>
              {f'<div class="lead-signal">{signal}</div>' if signal else ''}
              {f'<div class="lead-meta" style="margin-top:6px">Pain: {pain}</div>' if pain else ''}
              {f'<div class="lead-line">{opening}</div>' if opening else ''}
              <div class="lead-chips">{"".join(chips)}</div>
            </div>
            """, unsafe_allow_html=True)

    with tab_table:
        df = pd.DataFrame([
            {
                "Rank":      i + 1,
                "Company":   l.get("company_name", ""),
                "Score":     l.get("total_score", 0),
                "Contact":   l.get("contact_name", ""),
                "Title":     l.get("contact_title", ""),
                "Email":     l.get("email", ""),
                "Signal":    l.get("primary_signal", ""),
                "Opening":   l.get("opening_line", ""),
                "Website":   l.get("website", ""),
            }
            for i, l in enumerate(leads_sorted)
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2, _ = st.columns([1, 1, 4])
    with col1:
        if st.button("New brief", use_container_width=True):
            st.session_state.stage = "setup"
            st.session_state.events = []
            st.session_state.sources = {}
            st.session_state.stage_status = {}
            st.session_state.leads = []
            st.session_state.plan = {}
            st.rerun()
    with col2:
        if st.button("Re-run same brief", use_container_width=True):
            st.session_state.stage = "running"
            st.session_state.events = []
            st.session_state.sources = {}
            st.session_state.stage_status = {}
            st.session_state.leads = []
            st.rerun()
