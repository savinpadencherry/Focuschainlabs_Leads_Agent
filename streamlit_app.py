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
    --cream-3:   #FDFCF9;
    --ink:       #0F2A33;
    --ink-soft:  #3C5158;
    --ink-mute:  #6B7F85;
    --green:     #2E8B4D;
    --green-br:  #37A85C;
    --green-bg:  rgba(46,139,77,.09);
    --green-bg2: rgba(46,139,77,.16);
    --line:      rgba(15,42,51,.16);
    --line-soft: rgba(15,42,51,.09);
    --line-mid:  rgba(15,42,51,.22);
    --amber:     #B7791F;
    --amber-bg:  rgba(183,121,31,.10);
    --red:       #A93D3D;
    --red-bg:    rgba(169,61,61,.10);
    --rs:        8px;
    --r:         12px;
    --rl:        18px;
}

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
    opacity: .4; mix-blend-mode: multiply;
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='140' height='140'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2'/><feColorMatrix type='saturate' values='0'/></filter><rect width='140' height='140' filter='url(%23n)' opacity='0.045'/></svg>");
}
.block-container {
    padding-top: 32px !important;
    padding-bottom: 80px !important;
    max-width: 960px !important;
    position: relative; z-index: 1;
}

/* hide sidebar and header chrome */
[data-testid="stSidebar"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }
header[data-testid="stHeader"] { background: transparent !important; height: 0 !important; }

/* ── Typography base ── */
h1, h2, h3, h4, p, div, span, label {
    font-family: 'Bricolage Grotesque', sans-serif !important;
    color: var(--ink);
}

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
    flex-shrink: 0;
}
.eyebrow .dash { width: 28px; height: 1.5px; background: var(--green); flex-shrink: 0; }

/* ── Wordmark ── */
.wordmark {
    margin: 18px 0 6px;
    font-weight: 800;
    font-size: clamp(36px, 5.5vw, 60px);
    letter-spacing: -.035em; line-height: .96;
    color: var(--ink);
}
.wordmark .accent { color: var(--green); }
.wordmark span { display: inline-block; overflow: hidden; vertical-align: bottom; }
.wordmark span i {
    font-style: normal; display: inline-block;
    transform: translateY(110%);
    animation: rise .9s cubic-bezier(.16,1,.3,1) forwards;
}
.wordmark .w2 i { animation-delay: .14s; }

.tagline {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 12.5px; color: var(--ink-mute);
    letter-spacing: .04em;
    animation: fadeUp .7s ease .5s both;
    margin-bottom: 28px;
}

/* ── Step rail ── */
.steps {
    display: flex; align-items: center;
    gap: 0; margin: 0 0 40px;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 10px; font-weight: 600;
    letter-spacing: .22em; text-transform: uppercase;
}
.steps .step {
    display: flex; align-items: center; gap: 10px;
    color: var(--ink-mute); flex-shrink: 0;
}
.steps .step .num {
    width: 24px; height: 24px; border-radius: 50%;
    border: 1.5px solid var(--line-mid);
    display: flex; align-items: center; justify-content: center;
    font-size: 10px; font-weight: 700;
    background: var(--cream-3); color: var(--ink-mute);
    flex-shrink: 0;
    transition: all .3s;
}
.steps .step.active { color: var(--ink); }
.steps .step.active .num { background: var(--ink); color: var(--cream); border-color: var(--ink); }
.steps .step.done { color: var(--green); }
.steps .step.done .num { background: var(--green); color: #fff; border-color: var(--green); }
.steps .seg {
    flex: 1; height: 1.5px; background: var(--line-soft);
    margin: 0 12px; transition: background .4s;
}
.steps .seg.done { background: var(--green); }

/* ── Section label ── */
.sec {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 10px; font-weight: 600;
    letter-spacing: .28em; text-transform: uppercase;
    color: var(--ink-mute);
    margin: 28px 0 10px;
    display: flex; align-items: center; gap: 12px;
}
.sec .line { flex: 1; height: 1px; background: var(--line-soft); }

/* ── Client cards ── */
.client-card {
    background: var(--cream-3);
    border: 1.5px solid var(--line-soft);
    border-radius: var(--r);
    padding: 18px 20px 14px;
    cursor: pointer;
    transition: all .2s;
    height: 100%;
    position: relative;
}
.client-card.selected {
    border-color: var(--green);
    background: rgba(46,139,77,.06);
}
.client-card .name { font-size: 16px; font-weight: 700; color: var(--ink); margin-bottom: 3px; }
.client-card .vert {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px; font-weight: 600; letter-spacing: .16em; text-transform: uppercase;
    color: var(--green); margin-bottom: 10px;
}
.client-card .tags {
    display: flex; flex-wrap: wrap; gap: 4px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px; color: var(--ink-mute);
}
.client-card .tag {
    background: var(--line-soft);
    border-radius: 4px;
    padding: 2px 7px;
    border: 1px solid var(--line-soft);
}
.client-card.selected .tag {
    background: rgba(46,139,77,.10);
    border-color: rgba(46,139,77,.20);
    color: var(--green);
}
.client-card .sel-badge {
    position: absolute; top: 14px; right: 14px;
    width: 18px; height: 18px; border-radius: 50%;
    background: var(--green); display: none;
    align-items: center; justify-content: center;
}
.client-card.selected .sel-badge { display: flex; }
.client-card .sel-badge::after {
    content: ""; display: block;
    width: 5px; height: 9px;
    border-right: 2px solid #fff; border-bottom: 2px solid #fff;
    transform: rotate(40deg) translate(-1px, -1px);
}

/* ── Primary button — green ── */
[data-testid="stBaseButton-primary"],
.stButton > button[kind="primary"] {
    background: var(--green) !important;
    color: #fff !important;
    border: 1.5px solid var(--green) !important;
    border-radius: var(--rs) !important;
    font-family: 'Bricolage Grotesque', sans-serif !important;
    font-weight: 600 !important;
    font-size: 15px !important;
    letter-spacing: .005em !important;
    padding: 13px 26px !important;
    transition: all .2s ease !important;
    box-shadow: 0 2px 8px rgba(46,139,77,.18) !important;
}
[data-testid="stBaseButton-primary"]:hover,
.stButton > button[kind="primary"]:hover {
    background: var(--green-br) !important;
    border-color: var(--green-br) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 18px rgba(46,139,77,.24) !important;
}

/* ── Secondary button — outlined ── */
[data-testid="stBaseButton-secondary"],
.stButton > button {
    background: transparent !important;
    color: var(--ink) !important;
    border: 1.5px solid var(--line) !important;
    border-radius: var(--rs) !important;
    font-family: 'Bricolage Grotesque', sans-serif !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    padding: 10px 20px !important;
    transition: all .2s ease !important;
    box-shadow: none !important;
}
[data-testid="stBaseButton-secondary"]:hover,
.stButton > button:hover {
    background: var(--cream-2) !important;
    border-color: var(--line-mid) !important;
    transform: translateY(-1px) !important;
}

/* Download button */
.stDownloadButton > button {
    background: var(--green) !important;
    color: #fff !important;
    border: 1.5px solid var(--green) !important;
    border-radius: var(--rs) !important;
    font-family: 'Bricolage Grotesque', sans-serif !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    padding: 10px 20px !important;
    box-shadow: 0 2px 8px rgba(46,139,77,.18) !important;
}
.stDownloadButton > button:hover {
    background: var(--green-br) !important;
    border-color: var(--green-br) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 18px rgba(46,139,77,.24) !important;
}

/* ── Pills (industry selector) ── */
[data-testid="stPills"] {
    gap: 7px !important;
}
[data-testid="stPills"] button {
    background: var(--cream-3) !important;
    border: 1.5px solid var(--line-soft) !important;
    border-radius: 999px !important;
    color: var(--ink-soft) !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 11.5px !important;
    font-weight: 500 !important;
    padding: 6px 14px !important;
    transition: all .2s !important;
    box-shadow: none !important;
    cursor: pointer !important;
}
[data-testid="stPills"] button:hover {
    border-color: var(--green) !important;
    color: var(--green) !important;
    background: var(--green-bg) !important;
}
[data-testid="stPills"] button[aria-checked="true"],
[data-testid="stPills"] button[data-active="true"] {
    background: var(--green-bg2) !important;
    border-color: var(--green) !important;
    color: var(--green) !important;
    font-weight: 700 !important;
}

/* ── Form labels ── */
.stTextArea label, .stTextInput label, .stMultiSelect label,
.stSelectbox label, .stSlider label, .stRadio > label {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 10px !important; font-weight: 600 !important;
    letter-spacing: .28em !important; text-transform: uppercase !important;
    color: var(--ink-mute) !important;
}

/* ── Text area — Notion/Claude ── */
.stTextArea textarea {
    background: var(--cream-3) !important;
    color: var(--ink) !important;
    border: 1.5px solid var(--line-soft) !important;
    border-radius: var(--r) !important;
    padding: 20px 22px !important;
    font-family: 'Bricolage Grotesque', sans-serif !important;
    font-size: 15px !important;
    line-height: 1.68 !important;
    caret-color: var(--green) !important;
    transition: border-color .2s, box-shadow .2s, background .2s !important;
    resize: none !important;
    box-shadow: none !important;
}
.stTextArea textarea:focus {
    border-color: var(--green) !important;
    background: #fff !important;
    box-shadow: 0 0 0 4px rgba(46,139,77,.09) !important;
    outline: none !important;
}
.stTextArea textarea::placeholder {
    color: var(--ink-mute) !important;
    font-style: italic !important;
    font-weight: 300 !important;
    opacity: .7 !important;
}
.stTextArea > div { border: none !important; background: transparent !important; }

/* ── Text input ── */
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
.stTextInput > div { border: none !important; background: transparent !important; }

/* ── Slider ── */
.stSlider [role="slider"] { background: var(--green) !important; }
.stSlider > div > div > div:first-child { background: var(--line-soft) !important; }
.stSlider > div > div > div:last-child { background: var(--green) !important; }

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    gap: 24px !important;
    border-bottom: 1px solid var(--line-soft) !important;
    background: transparent !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: var(--ink-mute) !important;
    border: none !important;
    padding: 8px 0 14px !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    letter-spacing: .18em !important;
    text-transform: uppercase !important;
}
.stTabs [aria-selected="true"] {
    color: var(--ink) !important;
    border-bottom: 2px solid var(--green) !important;
}
.stTabs [data-baseweb="tab-panel"] { padding-top: 22px !important; }

/* ── Progress ── */
.stProgress > div > div > div { background: var(--green) !important; }
.stProgress > div > div { background: var(--line-soft) !important; height: 3px !important; }

/* ── Expander ── */
.streamlit-expanderHeader {
    background: var(--cream-3) !important;
    border: 1px solid var(--line-soft) !important;
    border-radius: var(--rs) !important;
    color: var(--ink) !important;
    font-family: 'Bricolage Grotesque', sans-serif !important;
    font-size: 14px !important; font-weight: 600 !important;
}
.streamlit-expanderContent {
    background: var(--cream-3) !important;
    border: 1px solid var(--line-soft) !important;
    border-top: none !important;
    border-radius: 0 0 var(--rs) var(--rs) !important;
}

/* ── DataFrame ── */
.stDataFrame {
    background: var(--cream-3) !important;
    border-radius: var(--rs) !important;
    border: 1px solid var(--line-soft) !important;
}

/* ── Pipeline animation ── */
.pipe-wrap {
    background: var(--cream-3);
    border: 1px solid var(--line-soft);
    border-radius: var(--rl);
    padding: 36px 32px 26px;
    margin: 12px 0 18px;
}
.pipe {
    display: flex; align-items: flex-start;
    justify-content: space-between;
    position: relative; gap: 0;
}
.pipe-track {
    position: absolute; top: 18px; left: 6%; right: 6%; height: 2px;
    background: var(--line-soft); border-radius: 2px; z-index: 0;
}
.pipe-flow {
    position: absolute; top: 18px; left: 6%; height: 2px;
    background: var(--green); border-radius: 2px;
    transition: width 1.2s cubic-bezier(.65,0,.35,1); z-index: 1;
}
.pipe-node {
    position: relative; z-index: 2;
    display: flex; flex-direction: column; align-items: center;
    gap: 10px; flex: 1; min-width: 0;
}
.pipe-dot {
    width: 36px; height: 36px; border-radius: 50%;
    background: var(--cream); border: 2px solid var(--line);
    display: flex; align-items: center; justify-content: center;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px; font-weight: 700; color: var(--ink-mute);
    transition: all .4s cubic-bezier(.34,1.56,.64,1);
}
.pipe-node.active .pipe-dot {
    background: var(--cream); border-color: var(--green); color: var(--green);
    transform: scale(1.15);
    box-shadow: 0 0 0 7px rgba(46,139,77,.10);
    animation: pulse 1.5s ease-in-out infinite;
}
.pipe-node.done .pipe-dot {
    background: var(--green); border-color: var(--green); color: #fff;
    transform: scale(1.05);
}
.pipe-lbl {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px; font-weight: 600;
    letter-spacing: .18em; text-transform: uppercase;
    color: var(--ink-mute); text-align: center;
}
.pipe-node.active .pipe-lbl { color: var(--green); }
.pipe-node.done .pipe-lbl { color: var(--green); }

/* ── Live feed ── */
.feed {
    background: var(--cream-3);
    border: 1px solid var(--line-soft);
    border-radius: var(--r);
    padding: 12px 16px;
    margin-bottom: 12px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
}
.feed-row {
    display: flex; align-items: center; gap: 12px;
    padding: 7px 0;
    border-bottom: 1px solid var(--line-soft);
}
.feed-row:last-child { border-bottom: none; }
.feed-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--line-mid); flex-shrink: 0;
}
.feed-dot.run { background: var(--green); animation: blink 1s ease-in-out infinite; }
.feed-dot.done { background: var(--green); }
.feed-dot.warn { background: var(--amber); }
.feed-dot.skip { background: var(--line-mid); }
.feed-dot.pending { background: var(--line-soft); }
.feed-name { flex: 1; color: var(--ink); font-weight: 500; }
.feed-status { color: var(--ink-mute); font-size: 11px; letter-spacing: .04em; }
.feed-count {
    font-weight: 700; color: var(--green);
    background: var(--green-bg);
    padding: 2px 8px; border-radius: 4px;
    font-size: 11px;
}

/* ── Score chips ── */
.sc { display: inline-flex; align-items: center; padding: 4px 10px; border-radius: 6px;
      font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 700; }
.sc-hi  { background: var(--green-bg2); color: var(--green); }
.sc-mid { background: var(--amber-bg); color: var(--amber); }
.sc-lo  { background: var(--red-bg); color: var(--red); }

/* ── Lead cards ── */
.lc {
    background: var(--cream-3);
    border: 1px solid var(--line-soft);
    border-radius: var(--r);
    padding: 22px 24px;
    margin-bottom: 14px;
    transition: all .2s;
}
.lc:hover { border-color: var(--line); transform: translateY(-1px);
            box-shadow: 0 6px 20px rgba(15,42,51,.05); }
.lc-hd { display: flex; align-items: flex-start; justify-content: space-between;
         margin-bottom: 12px; gap: 16px; }
.lc-name { font-size: 18px; font-weight: 700; color: var(--ink); margin-bottom: 3px; }
.lc-meta { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--ink-mute); }
.lc-sig {
    border-left: 2.5px solid var(--green);
    padding: 3px 0 3px 14px;
    margin: 10px 0;
    font-size: 14px; color: var(--ink); line-height: 1.55;
}
.lc-opener {
    background: var(--green-bg);
    border-radius: var(--rs);
    padding: 12px 16px;
    margin-top: 12px;
    font-size: 14px; font-style: italic;
    color: var(--ink); line-height: 1.6;
}
.lc-chips {
    display: flex; flex-wrap: wrap; gap: 8px;
    margin-top: 12px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10.5px; color: var(--ink-soft);
}
.lc-chips .k {
    color: var(--ink-mute); letter-spacing: .14em;
    text-transform: uppercase; margin-right: 3px;
}

/* ── Stats row ── */
.stats-row {
    display: grid; grid-template-columns: repeat(4, 1fr);
    gap: 12px; margin: 6px 0 28px;
}
.stat-box {
    background: var(--cream-3); border: 1px solid var(--line-soft);
    border-radius: var(--r); padding: 18px 16px; text-align: center;
}
.stat-box .num { font-size: 30px; font-weight: 800; color: var(--ink);
                 letter-spacing: -.02em; line-height: 1; }
.stat-box .lbl {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9.5px; font-weight: 600; letter-spacing: .22em;
    text-transform: uppercase; color: var(--ink-mute); margin-top: 7px;
}
@media (max-width: 720px) { .stats-row { grid-template-columns: repeat(2, 1fr); } }

/* ── Plan grid ── */
.plan-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 12px; }
.plan-cell { background: var(--cream-3); border: 1px solid var(--line-soft);
             border-radius: var(--rs); padding: 14px 16px; }
.plan-cell .k { font-family: 'JetBrains Mono', monospace;
                font-size: 9.5px; font-weight: 600; letter-spacing: .22em;
                text-transform: uppercase; color: var(--green); margin-bottom: 5px; }
.plan-cell .v { font-size: 13px; color: var(--ink); line-height: 1.55; }
@media (max-width: 720px) { .plan-grid { grid-template-columns: 1fr; } }

/* ── Notice box ── */
.notice {
    padding: 12px 16px;
    border-radius: var(--rs);
    font-family: 'JetBrains Mono', monospace;
    font-size: 11.5px;
    margin-top: 8px;
    border: 1px solid;
}
.notice.warn {
    background: var(--amber-bg); border-color: rgba(183,121,31,.25); color: var(--amber);
}
.notice.ok {
    background: var(--green-bg); border-color: rgba(46,139,77,.20); color: var(--green);
}

/* ── Keyframes ── */
@keyframes fadeUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
@keyframes rise   { to { transform: translateY(0); } }
@keyframes pulse  { 0%, 100% { box-shadow: 0 0 0 7px rgba(46,139,77,.10); }
                    50%       { box-shadow: 0 0 0 12px rgba(46,139,77,.04); } }
@keyframes blink  { 0%, 100% { opacity: 1; } 50% { opacity: .3; } }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

/* ── Misc ── */
.stApp [data-testid="stToolbar"] { display: none !important; }
footer { display: none !important; }
#MainMenu { display: none !important; }
hr { border-color: var(--line-soft) !important; margin: 28px 0 !important; }
.element-container { animation: fadeIn .45s ease both; }
</style>
""", unsafe_allow_html=True)

# ── Session state ────────────────────────────────────────────────────────────
def _init():
    defaults = {
        "stage":          "setup",
        "selected_client": None,
        "icp_path":       None,
        "industries":     [],
        "locations":      ["Bangalore"],
        "titles":         [],
        "prompt":         "",
        "max_leads":      10,
        "events":         [],
        "leads":          [],
        "output_path":    None,
        "stats":          {},
        "plan":           {},
        "sources":        {},
        "stage_status":   {},
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init()

# ── ICP discovery ─────────────────────────────────────────────────────────────
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

# Initialise selected_client to first key on first load
if st.session_state.selected_client is None and ICPS:
    st.session_state.selected_client = list(ICPS.keys())[0]


# ── Header ────────────────────────────────────────────────────────────────────
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

# ── Step rail ─────────────────────────────────────────────────────────────────
def render_steps(cur: str):
    order = {"setup": 0, "running": 1, "results": 2}
    def c(name, pos):
        n = order.get(cur, 0)
        if pos < n: return "step done"
        if pos == n: return "step active"
        return "step"
    st.markdown(f"""
    <div class="steps">
      <div class="{c('setup',0)}"><span class="num">1</span>&nbsp;Brief</div>
      <div class="seg {'done' if cur != 'setup' else ''}"></div>
      <div class="{c('running',1)}"><span class="num">2</span>&nbsp;Agent</div>
      <div class="seg {'done' if cur == 'results' else ''}"></div>
      <div class="{c('results',2)}"><span class="num">3</span>&nbsp;Leads</div>
    </div>""", unsafe_allow_html=True)

render_steps(st.session_state.stage)


# ═══════════════════════════════════════════════════════════════════════════════
#  STAGE 1 — SETUP
# ═══════════════════════════════════════════════════════════════════════════════
if st.session_state.stage == "setup":

    if not ICPS:
        st.error("No ICP config files found in /config. Add a JSON file there.")
        st.stop()

    # ── CLIENT SELECTION ──────────────────────────────────────────────────────
    st.markdown('<div class="sec">Client <span class="line"></span></div>',
                unsafe_allow_html=True)

    client_keys = list(ICPS.keys())
    n_clients = len(client_keys)
    client_cols = st.columns(n_clients, gap="medium")

    for i, name in enumerate(client_keys):
        data = ICPS[name]["data"]
        is_sel = (st.session_state.selected_client == name)
        ind_tags = "".join(
            f'<span class="tag">{ind}</span>'
            for ind in data.get("target_industries", [])[:5]
        )
        sel_cls = "client-card selected" if is_sel else "client-card"

        with client_cols[i]:
            st.markdown(f"""
            <div class="{sel_cls}">
              <div class="sel-badge"></div>
              <div class="name">{name}</div>
              <div class="vert">{data.get("vertical", "")}</div>
              <div class="tags">{ind_tags}
                {"<span class='tag'>+more</span>" if len(data.get("target_industries", [])) > 5 else ""}
              </div>
            </div>
            """, unsafe_allow_html=True)
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            btn_label = "Selected" if is_sel else "Select"
            if st.button(btn_label, key=f"client_{i}",
                         use_container_width=True,
                         type="primary" if is_sel else "secondary"):
                if not is_sel:
                    st.session_state.selected_client = name
                    # reset dependent state
                    st.session_state.industries = []
                    st.session_state.titles = []
                    st.rerun()

    client_choice = st.session_state.selected_client
    base_icp = ICPS[client_choice]["data"]
    st.session_state.icp_path = ICPS[client_choice]["path"]
    all_industries = base_icp.get("target_industries", [])

    # ── INDUSTRIES ────────────────────────────────────────────────────────────
    st.markdown('<div class="sec">Industries · toggle to refine <span class="line"></span></div>',
                unsafe_allow_html=True)

    # Use st.pills for multi-select chip toggle
    default_industries = (
        st.session_state.industries
        if st.session_state.industries
        else all_industries
    )
    industries = st.pills(
        "industries",
        options=all_industries,
        selection_mode="multi",
        default=default_industries,
        label_visibility="collapsed",
    )

    # ── DEMOGRAPHICS ROW ──────────────────────────────────────────────────────
    st.markdown('<div class="sec">Search parameters <span class="line"></span></div>',
                unsafe_allow_html=True)

    d_col1, d_col2, d_col3 = st.columns([1.2, 1, 1])
    with d_col1:
        st.caption("LOCATION")
        loc_default = (base_icp.get("locations") or ["Bangalore"])[0]
        location = st.text_input("location", value=loc_default,
                                 label_visibility="collapsed")
    with d_col2:
        st.caption("MAX LEADS")
        max_leads = st.slider("max_leads", min_value=3, max_value=25,
                              value=10, step=1, label_visibility="collapsed")
    with d_col3:
        st.caption("SCORE FLOOR (0–100)")
        threshold = st.slider("threshold", min_value=40, max_value=85,
                              value=int(os.getenv("MIN_SCORE_THRESHOLD", 60)),
                              step=5, label_visibility="collapsed")

    # ── TITLES ────────────────────────────────────────────────────────────────
    st.markdown('<div class="sec">Decision-maker titles <span class="line"></span></div>',
                unsafe_allow_html=True)
    all_titles = base_icp.get("target_titles", [])
    default_titles = (
        st.session_state.titles if st.session_state.titles else all_titles[:6]
    )
    titles = st.pills(
        "titles",
        options=all_titles,
        selection_mode="multi",
        default=default_titles,
        label_visibility="collapsed",
    )

    # ── PROMPT ────────────────────────────────────────────────────────────────
    st.markdown('<div class="sec">Your brief <span class="line"></span></div>',
                unsafe_allow_html=True)
    prompt = st.text_area(
        "prompt",
        height=150,
        placeholder=(
            "Describe in plain English — the LLM turns this into the actual searches.\n\n"
            "e.g. Find Bangalore-based mid-market IT firms or SaaS companies that hired "
            "a new CTO or CDO in the last 90 days and are publicly discussing legacy "
            "infrastructure pain. Skip anyone partnered with Infosys or TCS."
        ),
        label_visibility="collapsed",
    )

    # ── KEY STATUS + RUN ──────────────────────────────────────────────────────
    missing_keys = []
    if not os.getenv("GEMINI_API_KEY"): missing_keys.append("GEMINI_API_KEY")
    if not os.getenv("SERPER_API_KEY"): missing_keys.append("SERPER_API_KEY")

    if missing_keys:
        st.markdown(
            f'<div class="notice warn">Missing API keys: {", ".join(missing_keys)} '
            f'— add them to .env or Streamlit secrets</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    run_col, _ = st.columns([1, 3])
    with run_col:
        run = st.button("Run Agent", use_container_width=True, type="primary")

    if run:
        if not prompt.strip():
            st.warning("Add a brief — even one sentence — so the planner can build a search plan.")
            st.stop()
        os.environ["MAX_LEADS_PER_RUN"] = str(max_leads)
        os.environ["MIN_SCORE_THRESHOLD"] = str(threshold)
        st.session_state.industries = list(industries) if industries else all_industries
        st.session_state.locations  = [location]
        st.session_state.titles     = list(titles) if titles else all_titles
        st.session_state.prompt     = prompt.strip()
        st.session_state.max_leads  = max_leads
        st.session_state.events     = []
        st.session_state.sources    = {}
        st.session_state.stage_status = {}
        st.session_state.stage      = "running"
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
#  STAGE 2 — RUNNING
# ═══════════════════════════════════════════════════════════════════════════════
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

    def render_pipe(status: dict) -> str:
        active_idx = 0
        for i, (k, _) in enumerate(PIPE_STAGES):
            s = status.get(k)
            if s == "running":   active_idx = i; break
            if s == "done":      active_idx = i + 1
        pct = min(100, int((active_idx / max(len(PIPE_STAGES) - 1, 1)) * 100))
        nodes = ""
        for i, (k, lbl) in enumerate(PIPE_STAGES):
            s = status.get(k, "")
            klass = "done" if s == "done" else ("active" if s == "running" else "")
            nodes += (
                f'<div class="pipe-node {klass}">'
                f'<div class="pipe-dot">{i+1:02d}</div>'
                f'<div class="pipe-lbl">{lbl}</div></div>'
            )
        return (
            f'<div class="pipe-wrap"><div class="pipe">'
            f'<div class="pipe-track"></div>'
            f'<div class="pipe-flow" style="width:{pct}%"></div>'
            f'{nodes}</div></div>'
        )

    def render_sources(sources: dict) -> str:
        if not sources: return ""
        rows = ""
        ORDER = ["serper", "reddit", "tracxn", "proxycurl", "naukri"]
        for k in ORDER:
            if k not in sources: continue
            info   = sources[k]
            status = info.get("status", "pending")
            label  = info.get("label", k)
            count  = info.get("count", 0)
            reason = info.get("reason", "")
            ddot_cls = {"run": "run", "done": "done", "warn": "warn",
                        "skip": "skip", "pending": "pending"}.get(status, "pending")
            status_text = {"run": "scanning…", "done": "done",
                           "warn": "warning", "skip": "skipped",
                           "pending": "queued"}.get(status, status)
            right = (f'<span class="feed-count">{count}</span>'
                     if status == "done" and count
                     else f'<span class="feed-status">{reason or status_text}</span>')
            rows += (f'<div class="feed-row">'
                     f'<span class="feed-dot {ddot_cls}"></span>'
                     f'<span class="feed-name">{label}</span>{right}</div>')
        return f'<div class="feed">{rows}</div>'

    def render_activity(events: list) -> str:
        track = {"research_progress", "score_progress", "enrich_progress",
                 "pitch_progress", "score_result", "enrich_result"}
        recent = [e for e in events if e.get("type") in track][-7:]
        if not recent: return ""
        rows = ""
        for ev in recent:
            t = ev.get("type", "")
            if t == "score_result":
                score = ev.get("score", 0)
                cls = "sc-hi" if score >= 80 else ("sc-mid" if score >= 60 else "sc-lo")
                tag = "QUALIFIED" if ev.get("qualify") else "skipped"
                rows += (
                    f'<div class="feed-row">'
                    f'<span class="feed-dot {"run" if ev.get("qualify") else "skip"}"></span>'
                    f'<span class="feed-name">{ev.get("company","")}</span>'
                    f'<span class="sc {cls}">{score}</span>'
                    f'<span class="feed-status">{tag}</span></div>'
                )
            elif t == "enrich_result":
                st_txt = ev.get("status", "")
                rows += (
                    f'<div class="feed-row">'
                    f'<span class="feed-dot {"done" if st_txt=="found" else "skip"}"></span>'
                    f'<span class="feed-name">{ev.get("company","")}</span>'
                    f'<span class="feed-status">contact {st_txt}</span></div>'
                )
            else:
                stage_lbl = t.replace("_progress", "")
                rows += (
                    f'<div class="feed-row">'
                    f'<span class="feed-dot run"></span>'
                    f'<span class="feed-name">{ev.get("company","")}</span>'
                    f'<span class="feed-status">{stage_lbl} · {ev.get("idx","?")} / {ev.get("total","?")}</span>'
                    f'</div>'
                )
        return f'<div class="feed">{rows}</div>'

    # Slots
    pipe_slot     = st.empty()
    st.markdown('<div class="sec">Sources <span class="line"></span></div>',
                unsafe_allow_html=True)
    sources_slot  = st.empty()
    st.markdown('<div class="sec">Activity <span class="line"></span></div>',
                unsafe_allow_html=True)
    activity_slot = st.empty()
    plan_slot     = st.empty()

    pipe_slot.markdown(render_pipe(st.session_state.stage_status), unsafe_allow_html=True)

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
    sources_slot.markdown(render_sources(st.session_state.sources), unsafe_allow_html=True)

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
                for k, v in st.session_state.stage_status.items():
                    if v == "running":
                        st.session_state.stage_status[k] = "done"
                if stage in [s for s, _ in PIPE_STAGES]:
                    st.session_state.stage_status[stage] = "running"
                pipe_slot.markdown(render_pipe(st.session_state.stage_status),
                                   unsafe_allow_html=True)

            elif t == "stage_done":
                stage = ev.get("stage")
                if stage in [s for s, _ in PIPE_STAGES]:
                    st.session_state.stage_status[stage] = "done"
                pipe_slot.markdown(render_pipe(st.session_state.stage_status),
                                   unsafe_allow_html=True)

            elif t == "source_start":
                if st.session_state.stage_status.get("search") != "done":
                    st.session_state.stage_status["search"] = "running"
                k = ev.get("source")
                st.session_state.sources[k] = {
                    **st.session_state.sources.get(k, {}),
                    "label": ev.get("label", k), "status": "run",
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
                p = ev["plan"]
                plan_slot.markdown(f"""
                <div class="sec" style="margin-top:18px">Search plan generated <span class="line"></span></div>
                <div class="plan-grid">
                  <div class="plan-cell">
                    <div class="k">Industries</div>
                    <div class="v">{", ".join(p.get("industries", [])[:6]) or "—"}</div>
                  </div>
                  <div class="plan-cell">
                    <div class="k">Keywords generated</div>
                    <div class="v">{len(p.get("trigger_keywords", []))} queries</div>
                  </div>
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

            elif t in {"research_progress", "score_progress", "enrich_progress",
                       "pitch_progress", "score_result", "enrich_result"}:
                activity_slot.markdown(render_activity(st.session_state.events),
                                       unsafe_allow_html=True)

            elif t == "final":
                st.session_state.leads       = ev.get("leads", [])
                st.session_state.output_path = ev.get("output_path")
                st.session_state.stats       = ev.get("stats", {})
                st.session_state.plan        = ev.get("plan", st.session_state.plan)
                for k, _ in PIPE_STAGES:
                    st.session_state.stage_status[k] = "done"
                pipe_slot.markdown(render_pipe(st.session_state.stage_status),
                                   unsafe_allow_html=True)
                st.session_state.stage = "results"
                time.sleep(0.35)
                st.rerun()

    except Exception as e:
        st.error(f"Pipeline error: {e}")
        if st.button("← Back to brief"):
            st.session_state.stage = "setup"
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
#  STAGE 3 — RESULTS
# ═══════════════════════════════════════════════════════════════════════════════
elif st.session_state.stage == "results":

    stats  = st.session_state.stats or {}
    leads  = st.session_state.leads or []

    # Stats
    st.markdown(f"""
    <div class="stats-row">
      <div class="stat-box"><div class="num">{stats.get('total_leads', 0)}</div>
        <div class="lbl">Ranked leads</div></div>
      <div class="stat-box"><div class="num">{stats.get('qualified_count', 0)}</div>
        <div class="lbl">Qualified</div></div>
      <div class="stat-box"><div class="num">{stats.get('avg_score', 0)}</div>
        <div class="lbl">Avg score</div></div>
      <div class="stat-box"><div class="num">{stats.get('qualification_rate', '0%')}</div>
        <div class="lbl">Hit rate</div></div>
    </div>
    """, unsafe_allow_html=True)

    if not leads:
        st.warning(
            "No leads produced. Common causes: no API keys configured, "
            "all companies scored below the threshold, or the brief was too narrow. "
            "Try lowering the score floor or broadening the brief."
        )
        if st.button("← New brief"):
            for k in ["stage", "events", "sources", "stage_status", "leads", "plan"]:
                st.session_state[k] = {"stage": "setup", "events": [], "sources": {},
                                        "stage_status": {}, "leads": [], "plan": {}}.get(k)
            st.session_state.stage = "setup"
            st.rerun()
        st.stop()

    leads_sorted = sorted(leads, key=lambda x: x.get("total_score", 0), reverse=True)

    # Download + plan context
    dl_col, plan_col = st.columns([1, 2])
    with dl_col:
        if st.session_state.output_path and os.path.exists(st.session_state.output_path):
            with open(st.session_state.output_path, "rb") as f:
                st.download_button(
                    label="Download Excel",
                    data=f.read(),
                    file_name=os.path.basename(st.session_state.output_path),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
    with plan_col:
        if st.session_state.plan:
            p = st.session_state.plan
            pain = p.get("pain_hypothesis", "")
            gap  = p.get("gap_hypothesis", "")
            if pain or gap:
                st.markdown(
                    f'<div class="notice ok" style="margin-top:0">'
                    f'<strong>Pain:</strong> {pain or "—"}&nbsp;&nbsp;·&nbsp;&nbsp;'
                    f'<strong>Gap:</strong> {gap or "—"}</div>',
                    unsafe_allow_html=True,
                )

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    tab_cards, tab_table = st.tabs(["Lead cards", "Table view"])

    with tab_cards:
        for lead in leads_sorted:
            score   = lead.get("total_score", 0)
            sc_cls  = "sc-hi" if score >= 80 else ("sc-mid" if score >= 60 else "sc-lo")
            signal  = lead.get("primary_signal", "").strip()
            pain    = lead.get("pain_point", "").strip()
            opening = lead.get("opening_line", "").strip()
            cn      = lead.get("contact_name", "")
            ct      = lead.get("contact_title", "")
            em      = lead.get("email", "")
            li      = lead.get("linkedin_url", "")
            src     = lead.get("source", "")

            chips = []
            if cn and "Manual" not in cn:
                chips.append(f'<span><span class="k">contact</span>{cn}{" · " + ct if ct else ""}</span>')
            if em and "Manual" not in em and "@" in em:
                chips.append(f'<span><span class="k">email</span>{em}</span>')
            if li and "Manual" not in li:
                chips.append(f'<span><span class="k">li</span>{li[:50]}</span>')
            if src:
                chips.append(f'<span><span class="k">via</span>{src}</span>')

            st.markdown(f"""
            <div class="lc">
              <div class="lc-hd">
                <div>
                  <div class="lc-name">{lead.get("company_name","")}</div>
                  <div class="lc-meta">{lead.get("website","") or "—"}</div>
                </div>
                <span class="sc {sc_cls}">{score}/100</span>
              </div>
              {f'<div class="lc-sig">{signal}</div>' if signal else ""}
              {f'<div class="lc-meta" style="margin-top:6px;font-size:12.5px">Pain · {pain}</div>' if pain else ""}
              {f'<div class="lc-opener">{opening}</div>' if opening else ""}
              {f'<div class="lc-chips">{"".join(chips)}</div>' if chips else ""}
            </div>
            """, unsafe_allow_html=True)

    with tab_table:
        df = pd.DataFrame([
            {
                "Rank":    i + 1,
                "Company": l.get("company_name", ""),
                "Score":   l.get("total_score", 0),
                "Contact": l.get("contact_name", ""),
                "Title":   l.get("contact_title", ""),
                "Email":   l.get("email", ""),
                "Signal":  l.get("primary_signal", ""),
                "Opening": l.get("opening_line", ""),
            }
            for i, l in enumerate(leads_sorted)
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("<br>", unsafe_allow_html=True)
    b1, b2, _ = st.columns([1, 1, 4])
    with b1:
        if st.button("New brief", use_container_width=True):
            st.session_state.stage = "setup"
            st.session_state.events = []
            st.session_state.sources = {}
            st.session_state.stage_status = {}
            st.session_state.leads = []
            st.session_state.plan = {}
            st.rerun()
    with b2:
        if st.button("Re-run", use_container_width=True):
            st.session_state.stage = "running"
            st.session_state.events = []
            st.session_state.sources = {}
            st.session_state.stage_status = {}
            st.session_state.leads = []
            st.rerun()
