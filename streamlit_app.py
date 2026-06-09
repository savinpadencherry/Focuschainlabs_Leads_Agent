"""
FocusChain LeadGen — main UI
Cream / ink / green brand · 3-stage flow · live agent pipeline.
"""

from __future__ import annotations
import os
import json
import glob
import time
import html
import pandas as pd
from datetime import datetime

import streamlit as st
from utils.reach import best_reach_channel, how_to_reach
from crm_ui import add_leads_to_crm, render_crm_page
from reach_ui import render_reach_page
from intel_ui import render_intel_page
from proposal_ui import render_proposal_page
from finance_ui import render_finance_page
from utils.usage_guide import render_usage_guide

# ── Environment ──────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    def _apply_secret_env(prefix: str, value):
        if isinstance(value, str):
            if prefix and prefix not in os.environ:
                os.environ[prefix] = value
            return
        if hasattr(value, "items"):
            for child_key, child_value in value.items():
                _apply_secret_env(str(child_key), child_value)

    for _k, _v in st.secrets.items():
        _apply_secret_env(str(_k), _v)
except Exception:
    pass

if not os.getenv("GEMINI_API_KEY") and os.getenv("GOOGLE_API_KEY"):
    os.environ["GEMINI_API_KEY"] = os.getenv("GOOGLE_API_KEY")

os.makedirs("output", exist_ok=True)

# ── Crash detection across process restarts ──────────────────────────────────
# Streamlit Cloud (free tier) kills the whole process on OOM / time limits.
# When that happens, session_state is wiped and the app silently resets to the
# home screen — no Python exception fires, so the user sees nothing. We persist
# a tiny marker file at run start (survives the process restart) and clear it on
# completion/handled-error. If we boot and find a stale marker, we know the last
# run was killed by the platform and can tell the user exactly what happened.
_RUN_MARKER = os.path.join("output", ".run_in_progress.json")


def _write_run_marker(info: dict) -> None:
    try:
        with open(_RUN_MARKER, "w") as f:
            json.dump({**info, "ts": time.time()}, f)
    except Exception:
        pass


def _clear_run_marker() -> None:
    try:
        if os.path.exists(_RUN_MARKER):
            os.remove(_RUN_MARKER)
    except Exception:
        pass


def _read_run_marker() -> dict:
    try:
        if os.path.exists(_RUN_MARKER):
            with open(_RUN_MARKER) as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}


# ── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FocusChain Labs — LeadGen",
    page_icon="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><circle cx='50' cy='50' r='38' fill='%232E8B4D'/></svg>",
    layout="wide",
    initial_sidebar_state="expanded",
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
    --shadow-sm: 0 2px 8px rgba(15,42,51,.06);
    --shadow-md: 0 6px 20px rgba(15,42,51,.08);
    --shadow-lg: 0 14px 34px rgba(15,42,51,.10);
    --shadow-xl: 0 24px 60px rgba(15,42,51,.14);
    --radius-sm: 8px;
    --radius-md: 12px;
    --radius-lg: 18px;
    --radius-xl: 24px;
    --ease-out: cubic-bezier(.16,1,.3,1);
    --ease-spring: cubic-bezier(.34,1.56,.64,1);
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
      radial-gradient(130% 100% at 50% -10%, rgba(255,255,255,.60), transparent 55%),
      radial-gradient(140% 100% at 50% 110%, rgba(15,42,51,.04), transparent 50%);
    animation: ambientDrift 24s ease-in-out infinite alternate;
}
.stApp::after {
    content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 0;
    opacity: .35; mix-blend-mode: multiply;
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='140' height='140'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.75' numOctaves='2'/><feColorMatrix type='saturate' values='0'/></filter><rect width='140' height='140' filter='url(%23n)' opacity='0.04'/></svg>");
}
.block-container {
    padding-top: 16px !important;
    padding-bottom: 48px !important;
    max-width: 960px !important;
    position: relative; z-index: 1;
}

/* hide header chrome */
header[data-testid="stHeader"] { background: transparent !important; height: 0 !important; }

/* ── Left drawer — narrow rail, expands on hover ── */
[data-testid="stSidebar"],
[data-testid="stSidebar"][aria-expanded="false"],
[data-testid="stSidebar"][aria-expanded="true"] {
    display: block !important;
    visibility: visible !important;
    transform: translateX(0) !important;
    margin-left: 0 !important;
    position: relative !important;
    min-width: 54px !important;
    max-width: 54px !important;
    width: 54px !important;
    background: linear-gradient(180deg, rgba(239,234,222,.78), rgba(244,240,231,.52)) !important;
    border-right: 1px solid var(--line-soft) !important;
    box-shadow: 4px 0 18px rgba(15,42,51,.05) !important;
    overflow-x: hidden !important;
    overflow-y: auto !important;
    transition: min-width .30s var(--ease-out), max-width .30s var(--ease-out), width .30s var(--ease-out), box-shadow .30s var(--ease-out) !important;
    z-index: 999 !important;
}
[data-testid="stSidebar"]:hover {
    min-width: 204px !important;
    max-width: 204px !important;
    width: 204px !important;
    box-shadow: 10px 0 28px rgba(15,42,51,.10) !important;
}
[data-testid="stAppViewContainer"] > section[data-testid="stSidebar"] {
    flex: 0 0 54px !important;
    width: 54px !important;
    max-width: 54px !important;
}
[data-testid="stAppViewContainer"]:has([data-testid="stSidebar"]:hover) > section[data-testid="stSidebar"] {
    flex: 0 0 204px !important;
    width: 204px !important;
    max-width: 204px !important;
}
[data-testid="stSidebar"] > div:first-child {
    padding: 0 !important;
    background: transparent !important;
    width: 100% !important;
}
[data-testid="collapsedControl"] { display: none !important; }
.drawer-hamburger {
    position: fixed;
    top: 10px;
    left: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    margin: 0;
    border-radius: 10px;
    background: rgba(255,255,255,.96);
    border: 1px solid rgba(15,42,51,.10);
    box-shadow: 0 6px 18px rgba(15,42,51,.08), inset 0 1px 0 rgba(255,255,255,.95);
    pointer-events: none;
    z-index: 10002;
    transition: opacity .2s ease, transform .26s var(--ease-out);
}
.drawer-hamburger-bars {
    display: block;
    width: 14px;
    height: 2px;
    border-radius: 999px;
    background: var(--ink-soft);
    box-shadow: 0 5px 0 var(--ink-soft), 0 10px 0 var(--ink-soft);
}
[data-testid="stSidebar"]:hover .drawer-hamburger {
    opacity: 0;
    transform: translateX(-6px) scale(.88);
}
.drawer-hero {
    opacity: 0;
    max-height: 0;
    overflow: hidden;
    margin: 0;
    padding: 0 4px;
    pointer-events: none;
}
[data-testid="stSidebar"]:hover .drawer-hero {
    opacity: 1;
    max-height: 72px;
    margin: 52px 0 10px;
    padding: 0 6px 10px;
    border-bottom: 1px solid var(--line-soft);
    pointer-events: auto;
    animation: drawerHeroIn .36s var(--ease-out) both;
}
.drawer-hero-kicker {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: .20em;
    text-transform: uppercase;
    color: var(--green);
    margin-bottom: 4px;
}
.drawer-hero-title {
    font-family: 'Bricolage Grotesque', sans-serif !important;
    font-size: 18px;
    font-weight: 800;
    letter-spacing: -.02em;
    color: var(--ink);
    line-height: 1.1;
}
[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
    padding: 0 !important;
    width: 100% !important;
}
[data-testid="stSidebar"]:hover [data-testid="stSidebarContent"] {
    padding: 0 8px 16px !important;
    background:
        linear-gradient(180deg, rgba(253,252,249,.98) 0%, rgba(239,234,222,.92) 100%);
    border-radius: 0 16px 16px 0;
    box-shadow: inset -1px 0 0 rgba(46,139,77,.08);
    animation: drawerPanelIn .34s var(--ease-out) both;
}
[data-testid="stSidebar"]:not(:hover) [data-testid="stSidebarContent"] [data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"]:has(.stButton) {
    opacity: 0 !important;
    max-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: hidden !important;
    pointer-events: none !important;
    transform: translateX(-10px);
}
[data-testid="stSidebar"]:hover [data-testid="stSidebarContent"] [data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"]:has(.stButton) {
    opacity: 1 !important;
    max-height: 80px !important;
    margin-bottom: 6px !important;
    pointer-events: auto !important;
    transform: translateX(0);
    animation: drawerNavIn .34s var(--ease-out) both;
}
[data-testid="stSidebar"]:hover [data-testid="stSidebarContent"] [data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"]:has(.stButton):nth-child(2) { animation-delay: .04s; }
[data-testid="stSidebar"]:hover [data-testid="stSidebarContent"] [data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"]:has(.stButton):nth-child(3) { animation-delay: .08s; }
[data-testid="stSidebar"]:hover [data-testid="stSidebarContent"] [data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"]:has(.stButton):nth-child(4) { animation-delay: .12s; }
[data-testid="stSidebar"]:hover [data-testid="stSidebarContent"] [data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"]:has(.stButton):nth-child(5) { animation-delay: .16s; }
[data-testid="stSidebar"]:hover [data-testid="stSidebarContent"] [data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"]:has(.stButton):nth-child(6) { animation-delay: .20s; }
[data-testid="stSidebar"]:hover [data-testid="stSidebarContent"] [data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"]:has(.stButton):nth-child(7) { animation-delay: .24s; }
[data-testid="stSidebar"] [data-testid="stSidebarContent"] .stButton {
    margin: 0 !important;
    width: 100% !important;
}
[data-testid="stSidebar"] [data-testid="stSidebarContent"] .stButton > button {
    width: 100% !important;
    justify-content: flex-start !important;
    text-align: left !important;
    padding: 9px 12px !important;
    min-height: 36px !important;
    border-radius: var(--radius-sm) !important;
    font-family: 'Bricolage Grotesque', sans-serif !important;
    font-size: 14px !important;
    font-weight: 600 !important;
    letter-spacing: .005em !important;
    transform: none !important;
    box-shadow: none !important;
}
[data-testid="stSidebar"] [data-testid="stSidebarContent"] [data-testid="stBaseButton-secondary"],
[data-testid="stSidebar"] [data-testid="stSidebarContent"] .stButton > button[kind="secondary"],
[data-testid="stSidebar"] [data-testid="stSidebarContent"] .stButton > button:not([data-testid="stBaseButton-primary"]) {
    background: transparent !important;
    color: var(--ink) !important;
    -webkit-text-fill-color: var(--ink) !important;
    border: 1.5px solid transparent !important;
}
[data-testid="stSidebar"] [data-testid="stSidebarContent"] [data-testid="stBaseButton-secondary"]:hover,
[data-testid="stSidebar"] [data-testid="stSidebarContent"] .stButton > button:not([data-testid="stBaseButton-primary"]):hover {
    background: rgba(255,255,255,.55) !important;
    border-color: var(--line-soft) !important;
    transform: translateX(2px) !important;
}
[data-testid="stSidebar"] [data-testid="stSidebarContent"] [data-testid="stBaseButton-primary"],
[data-testid="stSidebar"] [data-testid="stSidebarContent"] .stButton > button[kind="primary"],
[data-testid="stSidebar"] [data-testid="stSidebarContent"] .stButton > button[data-testid="stBaseButton-primary"] {
    background: var(--green) !important;
    color: #fff !important;
    -webkit-text-fill-color: #fff !important;
    border: 1.5px solid var(--green) !important;
    box-shadow: 0 2px 8px rgba(46,139,77,.18) !important;
}
[data-testid="stSidebar"] [data-testid="stSidebarContent"] [data-testid="stBaseButton-primary"]::after,
[data-testid="stSidebar"] [data-testid="stSidebarContent"] .stButton > button[data-testid="stBaseButton-primary"]::after {
    display: none !important;
}
[data-testid="stSidebar"] [data-testid="stSidebarContent"] [data-testid="stBaseButton-primary"]:hover,
[data-testid="stSidebar"] [data-testid="stSidebarContent"] .stButton > button[data-testid="stBaseButton-primary"]:hover {
    background: var(--green-br) !important;
    border-color: var(--green-br) !important;
    transform: translateX(2px) !important;
    box-shadow: 0 6px 16px rgba(46,139,77,.22) !important;
}

/* ── Typography base ── */
h1, h2, h3, h4, p, div, span, label {
    font-family: 'Bricolage Grotesque', sans-serif !important;
    color: var(--ink);
}
[data-testid="stIconMaterial"] {
    font-family: "Material Symbols Rounded" !important;
}

/* ── Eyebrow ── */
.eyebrow {
    display: inline-flex; align-items: center; gap: 12px;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 10px; font-weight: 500;
    letter-spacing: .42em; text-transform: uppercase;
    color: var(--green);
    animation: fadeUp .7s ease .1s both;
}
.eyebrow .dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--green);
    box-shadow: 0 0 0 4px rgba(46,139,77,.16);
    flex-shrink: 0;
    animation: pulse-dot 3s ease-in-out infinite;
}
.eyebrow .dash { width: 24px; height: 1.5px; background: var(--green); flex-shrink: 0; }

/* ── Wordmark ── */
.wordmark {
    margin: 10px 0 2px;
    font-weight: 800;
    font-size: clamp(34px, 5.5vw, 58px);
    letter-spacing: -0.02em; line-height: .95;
    color: var(--ink);
}
.wordmark .accent { color: var(--green); }
.wordmark .accent {
    position: relative;
    text-shadow: 0 10px 28px rgba(46,139,77,.12);
}
.wordmark .accent::after {
    content: "";
    position: absolute; left: 0; right: 0; bottom: -4px; height: 2.5px;
    background: linear-gradient(90deg, transparent, var(--green), transparent);
    animation: signalSweep 3s ease-in-out 1.1s infinite;
    opacity: .8;
    border-radius: 2px;
}
.wordmark span { display: inline-block; overflow: hidden; vertical-align: bottom; }
.wordmark span i {
    font-style: normal; display: inline-block;
    transform: translateY(110%);
    animation: rise .9s var(--ease-out) forwards;
}
.wordmark .w2 i { animation-delay: .14s; }

.tagline {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 12px; color: var(--ink-mute);
    letter-spacing: .04em;
    animation: fadeUp .7s ease .5s both;
    margin-bottom: 12px;
}

/* ── Sub-page hero header (Reach / Intel / Proposal / CRM) ── */
.pg-eyebrow {
    display: inline-flex; align-items: center; gap: 10px;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 10px; font-weight: 700;
    letter-spacing: .38em; text-transform: uppercase;
    color: var(--green); margin-bottom: 12px;
    animation: fadeUp .5s ease both;
}
.pg-eyebrow .dot {
    width: 5px; height: 5px; border-radius: 50%;
    background: var(--green);
    box-shadow: 0 0 0 3px rgba(46,139,77,.14);
    animation: pulse-dot 3s ease-in-out infinite;
}
.pg-eyebrow .dash { width: 20px; height: 1.5px; background: var(--green); }
.pg-hero {
    font-family: 'Bricolage Grotesque', sans-serif !important;
    font-size: clamp(28px, 4vw, 38px);
    font-weight: 800; letter-spacing: -.03em; line-height: .97;
    color: var(--ink); margin: 0 0 6px;
    animation: fadeUp .6s ease .05s both;
}
.pg-hero .accent { color: var(--green); }
.pg-sub {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 12px; color: var(--ink-mute);
    letter-spacing: .03em; line-height: 1.7;
    margin-bottom: 24px;
    animation: fadeUp .6s ease .12s both;
}

/* ── Step rail ── */
.steps {
    display: flex; align-items: center;
    gap: 0; margin: 0 0 18px;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 10px; font-weight: 600;
    letter-spacing: .22em; text-transform: uppercase;
}
.steps .step {
    display: flex; align-items: center; gap: 9px;
    color: var(--ink-mute); flex-shrink: 0;
    transition: color .4s ease;
}
.steps .step .num {
    width: 26px; height: 26px; border-radius: 50%;
    border: 1.5px solid var(--line-mid);
    display: flex; align-items: center; justify-content: center;
    font-size: 10px; font-weight: 700;
    background: var(--cream-3); color: var(--ink-mute);
    flex-shrink: 0;
    transition: all .4s var(--ease-spring);
}
.steps .step.active { color: var(--ink); }
.steps .step.active .num {
    background: var(--ink); color: var(--cream); border-color: var(--ink);
    transform: scale(1.1);
    animation: stepPulse 2.2s ease-in-out infinite;
}
.steps .step.done { color: var(--green); }
.steps .step.done .num {
    background: var(--green); color: #fff; border-color: var(--green);
    transform: scale(1.05);
}
.steps .seg {
    flex: 1; height: 1.5px; background: var(--line-soft);
    margin: 0 12px; transition: background .5s ease;
    border-radius: 2px;
}
.steps .seg.done { background: var(--green); }

/* ── Section label ── */
.sec {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 10px; font-weight: 600;
    letter-spacing: .28em; text-transform: uppercase;
    color: var(--ink-mute);
    margin: 16px 0 8px;
    display: flex; align-items: center; gap: 12px;
}
.sec .line { flex: 1; height: 1px; background: var(--line-soft); }

/* ── Client cards ── */
.client-card {
    background: var(--cream-3);
    border: 1.5px solid var(--line-soft);
    border-radius: var(--radius-md);
    padding: 18px 20px 14px;
    cursor: pointer;
    transition: all .25s var(--ease-out);
    height: 100%;
    position: relative;
    box-shadow: var(--shadow-sm);
}
.client-card:hover {
    border-color: rgba(46,139,77,.25);
    transform: translateY(-2px);
    box-shadow: var(--shadow-md);
}
.client-card.selected {
    border-color: var(--green);
    background: linear-gradient(135deg, rgba(46,139,77,.06), rgba(255,255,255,.40));
    box-shadow: 0 4px 16px rgba(46,139,77,.12);
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
    width: 20px; height: 20px; border-radius: 50%;
    background: var(--green); display: none;
    align-items: center; justify-content: center;
    box-shadow: 0 2px 8px rgba(46,139,77,.30);
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
.stButton > button[kind="primary"],
.stButton > button[data-testid="stBaseButton-primary"] {
    background: var(--green) !important;
    color: #fff !important;
    -webkit-text-fill-color: #fff !important;
    border: 1.5px solid var(--green) !important;
    border-radius: var(--radius-sm) !important;
    font-family: 'Bricolage Grotesque', sans-serif !important;
    font-weight: 600 !important;
    font-size: 15px !important;
    letter-spacing: .005em !important;
    padding: 13px 26px !important;
    transition: all .25s var(--ease-out) !important;
    box-shadow: 0 2px 8px rgba(46,139,77,.18) !important;
    position: relative !important;
    overflow: hidden !important;
}
[data-testid="stBaseButton-primary"]::after,
.stButton > button[kind="primary"]::after,
.stButton > button[data-testid="stBaseButton-primary"]::after {
    content: "";
    position: absolute; top: 0; bottom: 0; left: -45%; width: 34%;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,.28), transparent);
    transform: skewX(-18deg);
    animation: buttonShine 4.8s ease-in-out infinite;
}
[data-testid="stBaseButton-primary"]:hover,
.stButton > button[kind="primary"]:hover {
    background: var(--green-br) !important;
    border-color: var(--green-br) !important;
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 22px rgba(46,139,77,.26) !important;
}
[data-testid="stBaseButton-primary"]:active,
.stButton > button[kind="primary"]:active {
    transform: translateY(0) scale(.98) !important;
}

/* ── Secondary button — outlined ── */
[data-testid="stBaseButton-secondary"],
.stButton > button {
    background: transparent !important;
    color: var(--ink) !important;
    border: 1.5px solid var(--line) !important;
    border-radius: var(--radius-sm) !important;
    font-family: 'Bricolage Grotesque', sans-serif !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    padding: 10px 20px !important;
    transition: all .2s var(--ease-out) !important;
    box-shadow: none !important;
}
[data-testid="stBaseButton-secondary"]:hover,
.stButton > button:hover {
    background: var(--cream-2) !important;
    border-color: var(--line-mid) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 12px rgba(15,42,51,.06) !important;
}
[data-testid="stBaseButton-secondary"]:active,
.stButton > button:active {
    transform: translateY(0) scale(.98) !important;
}

/* Download button */
.stDownloadButton > button {
    background: var(--green) !important;
    color: #fff !important;
    border: 1.5px solid var(--green) !important;
    border-radius: var(--radius-sm) !important;
    font-family: 'Bricolage Grotesque', sans-serif !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    padding: 10px 20px !important;
    box-shadow: 0 2px 8px rgba(46,139,77,.18) !important;
    transition: all .25s var(--ease-out) !important;
}
.stDownloadButton > button:hover {
    background: var(--green-br) !important;
    border-color: var(--green-br) !important;
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 22px rgba(46,139,77,.26) !important;
}

/* ── Pills (industry selector) ── */
[data-testid="stPills"] {
    gap: 6px !important;
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
    transition: all .2s var(--ease-out) !important;
    box-shadow: none !important;
    cursor: pointer !important;
}
[data-testid="stPills"] button:hover {
    border-color: var(--green) !important;
    color: var(--green) !important;
    background: var(--green-bg) !important;
    transform: translateY(-1px) !important;
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

/* ── Prompt form — Claude-style unified card ── */

/* Outer card */
[data-testid="stForm"] {
    background: var(--cream-3) !important;
    border: 1.5px solid var(--line-soft) !important;
    border-radius: var(--radius-md) !important;
    overflow: hidden !important;
    padding: 0 !important;
    box-shadow: var(--shadow-sm) !important;
    transition: border-color .25s var(--ease-out), box-shadow .25s var(--ease-out) !important;
    position: relative !important;
}
[data-testid="stForm"]::before {
    content: "";
    position: absolute; top: 0; bottom: 0; left: -34%; width: 24%;
    background: linear-gradient(90deg, transparent, rgba(46,139,77,.08), transparent);
    transform: skewX(-15deg);
    pointer-events: none;
    opacity: 0;
}
[data-testid="stForm"]:focus-within {
    border-color: rgba(46,139,77,.50) !important;
    box-shadow: 0 0 0 4px rgba(46,139,77,.09), var(--shadow-md) !important;
}
[data-testid="stForm"]:focus-within::before {
    opacity: 1;
    animation: formSweep 1.5s ease;
}

/* Collapse outer vertical gap */
[data-testid="stForm"] > div > [data-testid="stVerticalBlock"] {
    gap: 0 !important;
}

/* Textarea — borderless & transparent inside the card */
[data-testid="stForm"] .stTextArea textarea {
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
    padding: 18px 20px 14px !important;
    box-shadow: none !important;
    caret-color: var(--green) !important;
    font-family: 'Bricolage Grotesque', sans-serif !important;
    font-size: 15px !important;
    line-height: 1.7 !important;
    color: var(--ink) !important;
    resize: none !important;
}
[data-testid="stForm"] .stTextArea textarea:focus {
    border: none !important;
    box-shadow: none !important;
    background: transparent !important;
    outline: none !important;
}
[data-testid="stForm"] .stTextArea textarea::placeholder {
    color: var(--ink-mute) !important;
    font-style: italic !important;
    font-weight: 300 !important;
    opacity: .65 !important;
}
[data-testid="stForm"] .stTextArea > div,
[data-testid="stForm"] .stTextArea [data-baseweb="base-input"] {
    border: none !important;
    background: transparent !important;
    box-shadow: none !important;
}

/* Toolbar row: the columns block at the bottom of the form */
[data-testid="stForm"] [data-testid="stHorizontalBlock"] {
    border-top: 1px solid var(--line-soft) !important;
    padding: 8px 10px 8px 0 !important;
    margin: 0 !important;
    gap: 0 !important;
    align-items: center !important;
    background: transparent !important;
    min-height: 52px !important;
}

/* Hide the empty spacer column */
[data-testid="stForm"] [data-testid="stHorizontalBlock"] > [data-testid="column"]:first-child {
    padding: 0 !important;
}

/* Button column — flush right */
[data-testid="stForm"] [data-testid="stHorizontalBlock"] > [data-testid="column"]:last-child {
    display: flex !important;
    justify-content: flex-end !important;
    align-items: center !important;
    padding: 0 !important;
}

/* Send button wrapper */
[data-testid="stForm"] [data-testid="stFormSubmitButton"] {
    display: flex !important;
    justify-content: flex-end !important;
    align-items: center !important;
    width: 100% !important;
    background: transparent !important;
    padding: 0 !important;
    margin: 0 !important;
}

/* Circular send button — green circle, white ↑ arrow */
[data-testid="stForm"] [data-testid="stFormSubmitButton"] button {
    width: 36px !important;
    height: 36px !important;
    min-width: 36px !important;
    min-height: 36px !important;
    border-radius: 50% !important;
    padding: 0 !important;
    background: var(--green) !important;
    color: white !important;
    -webkit-text-fill-color: white !important;
    border: none !important;
    font-size: 17px !important;
    font-weight: 700 !important;
    line-height: 1 !important;
    box-shadow: 0 2px 8px rgba(46,139,77,.30) !important;
    transition: transform .2s var(--ease-spring), box-shadow .2s ease, background .2s ease !important;
    cursor: pointer !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
}
[data-testid="stForm"] [data-testid="stFormSubmitButton"] button:hover {
    background: var(--green-br) !important;
    transform: scale(1.12) !important;
    box-shadow: 0 4px 16px rgba(46,139,77,.38) !important;
}
[data-testid="stForm"] [data-testid="stFormSubmitButton"] button:active {
    transform: scale(0.92) !important;
}

/* Minimal setup helpers */
.template-note {
    border: 1px solid var(--line-soft);
    background: rgba(255,255,255,.42);
    border-radius: var(--rs);
    padding: 12px 14px;
    margin: 12px 0 18px;
    font-size: 13px;
    line-height: 1.45;
    color: var(--ink-soft);
}
.template-note strong { color: var(--ink); }
.composer-hint {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 10px;
    letter-spacing: .18em;
    text-transform: uppercase;
    color: var(--ink-mute);
    padding-left: 12px;
}
/* In-form file uploader — render as a single 📎 icon button, hide ALL text */
[data-testid="stForm"] .stFileUploader { padding-left: 10px !important; }
[data-testid="stForm"] .stFileUploader > label { display: none !important; }
[data-testid="stForm"] .stFileUploader section { padding: 0 !important; }
[data-testid="stForm"] .stFileUploader small,
[data-testid="stForm"] .stFileUploader [data-testid="stFileUploaderDropzoneInstructions"],
[data-testid="stForm"] .stFileUploader [data-testid="stFileUploaderDropzoneInstructions"] * {
    font-size: 0 !important;
    color: transparent !important;
    line-height: 0 !important;
}
[data-testid="stForm"] .stFileUploader [data-testid="stFileUploaderDropzone"] {
    min-height: 36px !important;
    height: 36px !important;
    width: 36px !important;
    padding: 0 !important;
    border: 1.5px solid var(--line-soft) !important;
    border-radius: 50% !important;
    background: transparent !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    position: relative !important;
    overflow: hidden !important;
    cursor: pointer !important;
    transition: border-color .2s, background .2s, transform .15s !important;
}
[data-testid="stForm"] .stFileUploader [data-testid="stFileUploaderDropzone"]:hover {
    border-color: var(--green) !important;
    background: var(--green-bg) !important;
    transform: scale(1.05) !important;
}
[data-testid="stForm"] .stFileUploader [data-testid="stFileUploaderDropzone"]::after {
    content: "📎";
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px !important;
    color: var(--ink-soft) !important;
    line-height: 1 !important;
    pointer-events: none;
}
/* Hide the "Browse files" button entirely — the whole dropzone is clickable */
[data-testid="stForm"] .stFileUploader [data-testid="stFileUploaderDropzone"] button {
    position: absolute !important;
    inset: 0 !important;
    width: 100% !important;
    height: 100% !important;
    opacity: 0 !important;
    padding: 0 !important;
    margin: 0 !important;
    border: none !important;
    background: transparent !important;
}

/* ── Text area — standalone (outside forms) ── */
.stTextArea textarea {
    background: var(--cream-3) !important;
    color: var(--ink) !important;
    border: 1.5px solid var(--line-soft) !important;
    border-radius: var(--radius-md) !important;
    padding: 18px 20px !important;
    font-family: 'Bricolage Grotesque', sans-serif !important;
    font-size: 15px !important;
    line-height: 1.7 !important;
    caret-color: var(--green) !important;
    transition: border-color .25s var(--ease-out), box-shadow .25s var(--ease-out), background .25s ease !important;
    resize: none !important;
    box-shadow: var(--shadow-sm) !important;
}
.stTextArea textarea:focus {
    border-color: var(--green) !important;
    background: #fff !important;
    box-shadow: 0 0 0 4px rgba(46,139,77,.09), var(--shadow-md) !important;
    outline: none !important;
}
.stTextArea textarea::placeholder {
    color: var(--ink-mute) !important;
    font-style: italic !important;
    font-weight: 300 !important;
    opacity: .65 !important;
}
.stTextArea > div { border: none !important; background: transparent !important; }

/* ── Text input ── */
.stTextInput input {
    background: var(--cream-3) !important;
    color: var(--ink) !important;
    border: 1.5px solid var(--line-soft) !important;
    border-radius: var(--radius-sm) !important;
    padding: 10px 14px !important;
    font-family: 'Bricolage Grotesque', sans-serif !important;
    font-size: 14px !important;
    transition: border-color .25s var(--ease-out), box-shadow .25s var(--ease-out) !important;
    box-shadow: var(--shadow-sm) !important;
}
.stTextInput input:focus {
    border-color: var(--green) !important;
    box-shadow: 0 0 0 3px rgba(46,139,77,.10), var(--shadow-sm) !important;
}
.stTextInput > div { border: none !important; background: transparent !important; }

/* ── Selectbox ── */
[data-baseweb="select"] > div {
    background: var(--cream-3) !important;
    border: 1.5px solid var(--line-soft) !important;
    border-radius: var(--radius-sm) !important;
    box-shadow: var(--shadow-sm) !important;
    transition: border-color .25s var(--ease-out), box-shadow .25s var(--ease-out) !important;
}

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
    transition: color .25s ease !important;
}
.stTabs [data-baseweb="tab"]:hover { color: var(--ink) !important; }
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
.run-console {
    position: relative;
    overflow: hidden;
    background: linear-gradient(135deg, #0F2A33 0%, #173944 100%);
    border: 1px solid rgba(244,240,231,.18);
    border-radius: var(--radius-lg);
    padding: 24px 26px;
    margin: 8px 0 18px;
    box-shadow: 0 20px 50px rgba(15,42,51,.18);
}
.run-console::after {
    content: "";
    position: absolute;
    left: 0; right: 0; bottom: 0; height: 3px;
    background: linear-gradient(90deg, transparent, var(--green), #9BCF9E, var(--green), transparent);
    background-size: 300% 100%;
    animation: scanline 2.8s linear infinite;
}
.run-console::before {
    content: "";
    position: absolute; top: 0; left: -80%; width: 40%; height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,.03), transparent);
    animation: shimmer-sweep 5s ease-in-out infinite;
    pointer-events: none; z-index: 0;
}
.run-console-top {
    display: flex; align-items: center; gap: 16px;
    margin-bottom: 14px; position: relative; z-index: 1;
}
.run-orbit {
    width: 40px; height: 40px; border-radius: 50%;
    border: 1.5px solid rgba(155,207,158,.65);
    display: flex; align-items: center; justify-content: center;
    color: #DFF0D8; font-family: 'JetBrains Mono', monospace;
    font-size: 12px; font-weight: 700;
    box-shadow: 0 0 0 8px rgba(46,139,77,.12);
    animation: orbit-glow 2s ease-in-out infinite;
    flex-shrink: 0;
    position: relative;
}
.run-orbit::after {
    content: "";
    position: absolute; inset: -6px;
    border-radius: 50%;
    border: 1.5px solid transparent;
    border-top-color: rgba(155,207,158,.85);
    border-right-color: rgba(155,207,158,.20);
    border-bottom-color: rgba(155,207,158,.05);
    animation: orbit-spin 1.8s linear infinite;
    pointer-events: none;
}
.run-title {
    color: var(--cream) !important;
    font-size: 20px; font-weight: 800;
    letter-spacing: -0.01em; line-height: 1.1;
}
.run-sub {
    color: #CBD5C0 !important;
    font-size: 13px; line-height: 1.45; margin-top: 4px;
    opacity: .85;
}
.run-focus {
    background: rgba(244,240,231,.08);
    border: 1px solid rgba(244,240,231,.12);
    border-radius: var(--radius-sm);
    padding: 12px 14px;
    color: #EAF4E4;
    font-size: 13px;
    line-height: 1.6;
    position: relative;
}
.run-focus::after {
    content: "▋";
    color: rgba(155,207,158,.65);
    animation: blink .85s step-end infinite;
    font-size: 12px;
    margin-left: 3px;
    position: relative; bottom: -1px;
}
.run-focus .k {
    font-family: 'JetBrains Mono', monospace;
    color: #9BCF9E; font-size: 9.5px;
    letter-spacing: .16em; text-transform: uppercase;
    margin-right: 8px;
}
.run-signal-strip {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 5px;
    margin-top: 14px; position: relative; z-index: 1;
}
.run-signal-strip span {
    height: 4px;
    border-radius: 999px;
    background: rgba(155,207,158,.12);
    overflow: hidden;
    position: relative;
}
.run-signal-strip span::after {
    content: "";
    position: absolute; inset: 0;
    background: linear-gradient(90deg, transparent, #9BCF9E, transparent);
    animation: scanCell 1.6s ease-in-out infinite;
    animation-delay: calc(var(--i) * .12s);
}
.run-metrics {
    display: grid; grid-template-columns: repeat(4, 1fr);
    gap: 8px; margin-top: 14px; position: relative; z-index: 1;
}
.run-metric {
    border: 1px solid rgba(244,240,231,.11);
    border-radius: var(--radius-sm);
    padding: 10px 12px;
    background: rgba(244,240,231,.06);
    backdrop-filter: blur(4px);
    transition: border-color .2s ease, background .2s ease;
}
.run-metric:hover { border-color: rgba(244,240,231,.20); background: rgba(244,240,231,.09); }
.run-metric .num {
    color: var(--cream); font-size: 22px; font-weight: 800; line-height: 1;
}
.run-metric .lbl {
    margin-top: 5px;
    font-family: 'JetBrains Mono', monospace;
    color: #9DAFA7; font-size: 8.5px;
    letter-spacing: .13em; text-transform: uppercase;
}
@media (max-width: 720px) { .run-metrics { grid-template-columns: repeat(2, 1fr); } }

.pipe-wrap {
    background: var(--cream-3);
    border: 1.5px solid var(--line-soft);
    border-radius: var(--radius-lg);
    padding: 32px 28px 22px;
    margin: 12px 0 18px;
    box-shadow: var(--shadow-sm);
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
    position: absolute; top: 18px; left: 6%; height: 2.5px;
    background: linear-gradient(90deg, var(--green), #9BCF9E);
    border-radius: 2px;
    transition: width 1.2s var(--ease-out); z-index: 1;
}
.pipe-node {
    position: relative; z-index: 2;
    display: flex; flex-direction: column; align-items: center;
    gap: 10px; flex: 1; min-width: 0;
}
.pipe-dot {
    width: 38px; height: 38px; border-radius: 50%;
    background: var(--cream); border: 2px solid var(--line);
    display: flex; align-items: center; justify-content: center;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px; font-weight: 700; color: var(--ink-mute);
    transition: all .45s var(--ease-spring);
}
.pipe-node.active .pipe-dot {
    background: var(--cream); border-color: var(--green); color: var(--green);
    transform: scale(1.18);
    box-shadow: 0 0 0 8px rgba(46,139,77,.10);
    animation: node-glow 1.5s ease-in-out infinite;
}
.pipe-node.done .pipe-dot {
    background: var(--green); border-color: var(--green); color: #fff;
    transform: scale(1.08);
    box-shadow: 0 2px 10px rgba(46,139,77,.20);
}
.pipe-lbl {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px; font-weight: 600;
    letter-spacing: .18em; text-transform: uppercase;
    color: var(--ink-mute); text-align: center;
    transition: color .3s ease;
}
.pipe-node.active .pipe-lbl { color: var(--green); }
.pipe-node.done .pipe-lbl { color: var(--green); }

/* ── Live feed ── */
.feed {
    background: var(--cream-3);
    border: 1.5px solid var(--line-soft);
    border-radius: var(--radius-md);
    padding: 10px 16px;
    margin-bottom: 10px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    box-shadow: var(--shadow-sm);
}
.feed-row {
    display: flex; align-items: center; gap: 12px;
    padding: 7px 0;
    border-bottom: 1px solid var(--line-soft);
    animation: slideInRow .28s ease both;
}
.feed-row:last-child { border-bottom: none; }
.feed-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--line-mid); flex-shrink: 0;
    transition: background .3s ease;
}
.feed-dot.run { background: var(--green); animation: blink 1s ease-in-out infinite; box-shadow: 0 0 0 3px rgba(46,139,77,.20); }
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
    border: 1.5px solid var(--line-soft);
    border-radius: var(--radius-md);
    padding: 22px 24px;
    margin-bottom: 14px;
    transition: all .25s var(--ease-out);
    position: relative;
    overflow: hidden;
    animation: cardIn .42s var(--ease-out) both;
    box-shadow: var(--shadow-sm);
}
.lc::before {
    content: "";
    position: absolute; top: 0; left: 0; right: 0; height: 2px;
    background: linear-gradient(90deg, transparent, rgba(46,139,77,.50), transparent);
    transform: translateX(-100%);
    transition: transform .7s ease;
}
.lc:hover::before { transform: translateX(100%); }
.lc:hover { border-color: var(--line); transform: translateY(-2px);
            box-shadow: var(--shadow-md); }
.lc-hd { display: flex; align-items: flex-start; justify-content: space-between;
         margin-bottom: 12px; gap: 16px; }
.lc-name { font-size: 18px; font-weight: 700; color: var(--ink); margin-bottom: 3px; }
.lc-meta { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--ink-mute); }
.lc-sig {
    border-left: 2.5px solid var(--green);
    padding: 3px 0 3px 14px;
    margin: 10px 0;
    font-size: 14px; color: var(--ink); line-height: 1.6;
}
.lc-opener {
    background: var(--green-bg);
    border-radius: var(--radius-sm);
    padding: 12px 16px;
    margin-top: 12px;
    font-size: 14px; font-style: italic;
    color: var(--ink); line-height: 1.6;
    border-left: 2.5px solid var(--green);
}
.lc-reach {
    margin-top: 12px;
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 10px;
    align-items: start;
    border: 1px solid rgba(46,139,77,.16);
    background: linear-gradient(135deg, rgba(46,139,77,.055), rgba(255,255,255,.40));
    border-radius: var(--radius-sm);
    padding: 11px 13px;
    transition: border-color .2s ease;
}
.lc-reach:hover { border-color: rgba(46,139,77,.25); }
.lc-channel {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9.5px;
    font-weight: 700;
    letter-spacing: .12em;
    text-transform: uppercase;
    color: #fff;
    background: var(--green);
    border-radius: 4px;
    padding: 3px 7px;
    white-space: nowrap;
    box-shadow: 0 2px 6px rgba(46,139,77,.20);
}
.lc-reach-text {
    color: var(--ink);
    font-size: 13px;
    line-height: 1.5;
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
/* Evidence block */
.lc-evidence {
    margin-top: 14px;
    border-top: 1px solid var(--line-soft);
    padding-top: 12px;
    display: flex; flex-direction: column; gap: 6px;
}
.lc-ev-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px; letter-spacing: .14em;
    text-transform: uppercase; color: var(--ink-mute);
    margin-bottom: 4px;
}
.lc-ev-item {
    display: flex; align-items: flex-start; gap: 8px;
    font-size: 12.5px; color: var(--ink-soft); line-height: 1.5;
    padding: 2px 4px;
    border-radius: 6px;
    transition: background .2s ease;
}
.lc-ev-item:hover { background: rgba(15,42,51,.03); }
.lc-ev-cat {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9.5px; letter-spacing: .1em;
    text-transform: uppercase; padding: 2px 6px;
    border-radius: 4px; white-space: nowrap; flex-shrink: 0;
    margin-top: 1px;
}
.ev-paid_ads  { background: #FEF3C7; color: #92400E; }
.ev-hiring    { background: #D1FAE5; color: #065F46; }
.ev-news      { background: #DBEAFE; color: #1E40AF; }
.ev-linkedin  { background: #E0E7FF; color: #3730A3; }
.ev-community { background: #FCE7F3; color: #9D174D; }
.ev-management{ background: #ECFCCB; color: #3F6212; }
/* Outreach strategy note */
.lc-note {
    margin-top: 14px;
    background: linear-gradient(135deg, rgba(15,42,51,.04), rgba(255,255,255,.30));
    border-left: 2.5px solid var(--ink-mute);
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
    padding: 12px 16px;
    transition: border-color .2s ease;
}
.lc-note:hover { border-left-color: var(--ink-soft); }
.lc-note-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9.5px; letter-spacing: .14em;
    text-transform: uppercase; color: var(--ink-mute);
    margin-bottom: 6px;
}
.lc-note-body {
    font-size: 13px; color: var(--ink);
    line-height: 1.7; white-space: pre-wrap;
}

/* ── Live ticker ── */
.ticker {
    background: var(--ink);
    color: var(--cream);
    border-radius: var(--rs);
    padding: 14px 20px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12.5px;
    margin-bottom: 20px;
    display: flex; align-items: center; gap: 14px;
    min-height: 50px; line-height: 1.5;
}
.ticker-pulse {
    width: 9px; height: 9px; border-radius: 50%;
    background: var(--green); flex-shrink: 0;
    animation: blink 1.4s ease-in-out infinite;
}
@keyframes blink {
    0%,100% { opacity: 1; } 50% { opacity: .3; }
}
.ticker-stage {
    color: var(--green); font-size: 9.5px;
    letter-spacing: .14em; text-transform: uppercase;
    margin-right: 4px; white-space: nowrap;
}
.ticker-msg { flex: 1; color: #CBD5C0; }

/* ── Keyword search log ── */
.kw-log { display: flex; flex-direction: column; gap: 0; }
.kw-row {
    display: flex; align-items: center; gap: 8px;
    padding: 7px 0; border-bottom: 1px solid var(--line-soft);
    font-size: 12px;
}
.kw-row:last-child { border-bottom: none; }
.kw-badge {
    font-family: 'JetBrains Mono', monospace;
    font-size: 8.5px; letter-spacing: .1em; text-transform: uppercase;
    padding: 2px 6px; border-radius: 3px; flex-shrink: 0;
}
.kw-google   { background: #DBEAFE; color: #1E40AF; }
.kw-linkedin { background: #E0E7FF; color: #3730A3; }
.kw-reddit   { background: #FCE7F3; color: #9D174D; }
.kw-yahoo    { background: #E6E6FA; color: #4B0082; }
.kw-naukri   { background: #FEF3C7; color: #92400E; }
.kw-q { flex: 1; color: var(--ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kw-count { color: var(--ink-mute); font-family: 'JetBrains Mono', monospace; font-size: 11px; flex-shrink: 0; }

/* ── Company activity log ── */
.act-log { display: flex; flex-direction: column; gap: 0; }
.act-row {
    display: flex; align-items: flex-start; gap: 10px;
    padding: 8px 0; border-bottom: 1px solid var(--line-soft);
    font-size: 12.5px;
}
.act-row:last-child { border-bottom: none; }
.act-dot {
    width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; margin-top: 4px;
}
.act-run   { background: var(--green); animation: blink 1.4s ease-in-out infinite; }
.act-done  { background: var(--green); }
.act-skip  { background: #E5E7EB; }
.act-warn  { background: #F59E0B; }
.act-body { flex: 1; }
.act-company { font-weight: 600; color: var(--ink); }
.act-detail  { color: var(--ink-mute); font-size: 11.5px; margin-top: 1px; }
.act-score {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px; font-weight: 700; padding: 2px 7px;
    border-radius: 4px; flex-shrink: 0; align-self: center;
}

/* ── Stats row ── */
.stats-row {
    display: grid; grid-template-columns: repeat(4, 1fr);
    gap: 12px; margin: 6px 0 28px;
}
.stat-box {
    background: linear-gradient(135deg, var(--cream-3), rgba(255,255,255,.50));
    border: 1.5px solid var(--line-soft);
    border-radius: var(--radius-md); padding: 20px 16px; text-align: center;
    box-shadow: var(--shadow-sm);
    transition: all .25s var(--ease-out);
}
.stat-box:hover {
    border-color: var(--line); transform: translateY(-2px);
    box-shadow: var(--shadow-md);
}
.stat-box .num { font-size: 32px; font-weight: 800; color: var(--ink);
                 letter-spacing: -0.02em; line-height: 1; }
.stat-box .lbl {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9.5px; font-weight: 600; letter-spacing: .22em;
    text-transform: uppercase; color: var(--ink-mute); margin-top: 8px;
}
@media (max-width: 720px) { .stats-row { grid-template-columns: repeat(2, 1fr); } }

/* ── Plan grid ── */
.plan-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 12px; }
.plan-cell {
    background: var(--cream-3); border: 1.5px solid var(--line-soft);
    border-radius: var(--radius-sm); padding: 14px 16px;
    box-shadow: var(--shadow-sm);
    transition: all .2s var(--ease-out);
}
.plan-cell:hover { border-color: var(--line); box-shadow: var(--shadow-md); }
.plan-cell .k { font-family: 'JetBrains Mono', monospace;
                font-size: 9.5px; font-weight: 600; letter-spacing: .22em;
                text-transform: uppercase; color: var(--green); margin-bottom: 5px; }
.plan-cell .v { font-size: 13px; color: var(--ink); line-height: 1.55; }
@media (max-width: 720px) { .plan-grid { grid-template-columns: 1fr; } }

/* ── Notice box ── */
/* ── API Status Bar ──────────────────────────────────────────────── */
.api-bar {
    display: flex; align-items: center; justify-content: space-between;
    background: rgba(15,42,51,.55); border: 1px solid rgba(229,224,211,.1);
    border-radius: 10px; padding: 10px 16px; margin-bottom: 14px;
    flex-wrap: wrap; gap: 8px;
}
.api-chips { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
.api-chip {
    display: flex; align-items: center; gap: 5px;
    border-radius: 20px; padding: 3px 10px 3px 8px;
    font-family: 'JetBrains Mono', monospace; font-size: 10.5px;
    border: 1px solid transparent; cursor: default;
}
.api-icon { font-size: 10px; }
.api-name { color: #CBD5C0; font-weight: 500; }
.api-badge { font-size: 9.5px; font-weight: 700; letter-spacing: .04em; margin-left: 3px; }
.api-chip.api-idle  { background: rgba(203,213,192,.06); border-color: rgba(203,213,192,.12); }
.api-chip.api-idle  .api-badge { color: #7A8F7A; }
.api-chip.api-ok    { background: rgba(46,139,77,.12);  border-color: rgba(46,139,77,.25); }
.api-chip.api-ok    .api-badge { color: #2E8B4D; }
.api-chip.api-rl    { background: rgba(239,68,68,.12);  border-color: rgba(239,68,68,.35); animation: api-pulse 1.4s ease infinite; }
.api-chip.api-rl    .api-badge { color: #EF4444; }
.api-chip.api-err   { background: rgba(239,68,68,.1);   border-color: rgba(239,68,68,.25); }
.api-chip.api-err   .api-badge { color: #EF4444; }
.api-chip.api-nokey { background: rgba(203,213,192,.04); border-color: rgba(203,213,192,.07); opacity: .45; }
.api-chip.api-nokey .api-badge { color: #7A8F7A; }
@keyframes api-pulse {
    0%,100% { box-shadow: 0 0 0 0 rgba(239,68,68,.3); }
    50%      { box-shadow: 0 0 0 4px rgba(239,68,68,.0); }
}
.api-cost { font-family: 'JetBrains Mono', monospace; font-size: 10.5px; color: #7A8F7A; }
.api-cost strong { color: #CBD5C0; }
.api-cost-note { color: #556B55; margin-left: 6px; }
.api-alert {
    background: rgba(239,68,68,.08); border: 1px solid rgba(239,68,68,.3);
    border-radius: 8px; padding: 10px 14px; margin-bottom: 10px;
    font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #FCA5A5;
}
.api-alert strong { color: #EF4444; }
/* ─────────────────────────────────────────────────────────────────── */
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
@keyframes ambientDrift {
    from { transform: translate3d(0, 0, 0) scale(1); }
    to   { transform: translate3d(0, -12px, 0) scale(1.02); }
}
@keyframes fadeUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
@keyframes rise   { to { transform: translateY(0); } }
@keyframes pulse  { 0%, 100% { box-shadow: 0 0 0 7px rgba(46,139,77,.10); }
                    50%       { box-shadow: 0 0 0 12px rgba(46,139,77,.04); } }
@keyframes pulse-dot { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: .6; transform: scale(.9); } }
@keyframes blink      { 0%, 100% { opacity: 1; } 50% { opacity: .3; } }
@keyframes fadeIn     { from { opacity: 0; } to { opacity: 1; } }
@keyframes scanline   { from { background-position: 0% 50%; } to { background-position: 220% 50%; } }
@keyframes signalSweep {
    0%, 20% { transform: translateX(-35%) scaleX(.25); opacity: 0; }
    45%     { opacity: .8; }
    75%,100%{ transform: translateX(35%) scaleX(1); opacity: 0; }
}
@keyframes stepPulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(15,42,51,.14); }
    50%      { box-shadow: 0 0 0 8px rgba(15,42,51,.04); }
}
@keyframes buttonShine {
    0%, 35% { left: -45%; opacity: 0; }
    50%     { opacity: 1; }
    75%,100%{ left: 115%; opacity: 0; }
}
@keyframes formSweep {
    from { left: -34%; }
    to   { left: 118%; }
}
@keyframes scanCell {
    0%, 35% { transform: translateX(-100%); opacity: 0; }
    50%     { opacity: 1; }
    100%    { transform: translateX(100%); opacity: 0; }
}
@keyframes orbit-spin { to { transform: rotate(360deg); } }
@keyframes orbit-glow {
    0%, 100% { box-shadow: 0 0 0 8px rgba(46,139,77,.10), 0 0 14px rgba(46,139,77,.12); }
    50%       { box-shadow: 0 0 0 16px rgba(46,139,77,.04), 0 0 32px rgba(46,139,77,.28); }
}
@keyframes shimmer-sweep {
    0%   { left: -80%; }
    100% { left: 160%; }
}
@keyframes slideInRow {
    from { opacity: 0; transform: translateX(-10px); }
    to   { opacity: 1; transform: translateX(0); }
}
@keyframes drawerSlideIn {
    from { opacity: 0; transform: translateX(-18px); }
    to   { opacity: 1; transform: translateX(0); }
}
@keyframes drawerPanelIn {
    from { opacity: 0; transform: translateX(-12px); box-shadow: inset -1px 0 0 transparent; }
    to   { opacity: 1; transform: translateX(0); box-shadow: inset -1px 0 0 rgba(46,139,77,.08); }
}
@keyframes drawerHeroIn {
    from { opacity: 0; transform: translateY(-8px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes drawerNavIn {
    from { opacity: 0; transform: translateX(-14px); }
    to   { opacity: 1; transform: translateX(0); }
}
@keyframes slideInDrawer {
    from { opacity: 0; transform: translateX(-12px); }
    to   { opacity: 1; transform: translateX(0); }
}
@keyframes node-glow {
    0%, 100% { box-shadow: 0 0 0 8px rgba(46,139,77,.10); }
    50%       { box-shadow: 0 0 0 16px rgba(46,139,77,.04), 0 0 10px rgba(46,139,77,.50); }
}
@keyframes metricPop {
    from { opacity: 0; transform: scale(.88) translateY(5px); }
    to   { opacity: 1; transform: scale(1) translateY(0); }
}
@keyframes flow-pulse { 0%, 100% { opacity: 1; } 50% { opacity: .6; } }
@keyframes cardIn {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: translateY(0); }
}

/* Slide-in for activity rows and keyword rows */
.act-row { animation: slideInRow .28s ease both; }
.kw-row  { animation: slideInRow .22s ease both; }

/* Metric pop-in staggered */
.run-metric { animation: metricPop .45s cubic-bezier(.34,1.56,.64,1) both; }
.run-metric:nth-child(2) { animation-delay: .07s; }
.run-metric:nth-child(3) { animation-delay: .14s; }
.run-metric:nth-child(4) { animation-delay: .21s; }

/* Pipeline progress bar breathing */
.pipe-flow { animation: flow-pulse 2s ease-in-out infinite; }

@media (max-width: 720px) {
    .block-container {
        padding-top: 24px !important;
        padding-left: 18px !important;
        padding-right: 18px !important;
        padding-bottom: 64px !important;
        max-width: 100% !important;
    }
    .eyebrow {
        gap: 8px;
        font-size: 9px;
        letter-spacing: .24em;
        white-space: nowrap;
    }
    .eyebrow .dash { width: 18px; }
    .wordmark {
        font-size: 42px;
        line-height: 1;
        margin-top: 16px;
    }
    .tagline {
        font-size: 11px;
        line-height: 1.7;
        margin-bottom: 22px;
    }
    .stButton > button,
    [data-testid="stBaseButton-primary"],
    [data-testid="stBaseButton-secondary"] {
        min-height: 46px !important;
        padding: 11px 14px !important;
        white-space: nowrap !important;
        word-break: keep-all !important;
        overflow-wrap: normal !important;
    }
}

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
        "prompt_text":    "",
        "max_leads":      30,
        "exclusion_path": None,
        "exclusion_name": "",
        "events":         [],
        "leads":          [],
        "output_path":    None,
        "stats":          {},
        "plan":           {},
        "sources":        {},
        "stage_status":   {},
        "run_error":      "",
        "run_traceback":  "",
        "run_warnings":   [],
        "app_view":       "agent",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # First boot of this session — check for a run that was killed by the platform
    if "crash_checked" not in st.session_state:
        st.session_state.crash_checked = True
        marker = _read_run_marker()
        # Stale marker + session reset to setup ⇒ the process was killed mid-run
        if marker and st.session_state.stage == "setup":
            age = time.time() - marker.get("ts", 0)
            if age < 3600:  # ignore very old markers
                st.session_state.interrupted_run = marker
        _clear_run_marker()

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

DEFAULT_PROMPTS = {
    "FocusChainLabs": (
        "Find at least 30 real companies that are likely buyers for FocusChain Labs.\n\n"
        "FocusChain Labs helps SMB and SME companies improve operations, lead flow, customer "
        "management, reporting, workflow automation, ecommerce, booking systems, CRM, websites, "
        "and practical AI/data workflows. Search broadly across Bangalore and India for textile "
        "manufacturers, small manufacturers, interior designers, law firms, medical equipment "
        "providers, logistics companies, online travel and ticket booking agencies, renewable "
        "energy product/service firms, local IT and broadband providers, diagnostic agencies, "
        "D2C hair care, skin care, makeup/beauty brands, and D2C branding agencies.\n\n"
        "Look for buying signals such as hiring for operations, growth, ecommerce, CRM, "
        "automation, customer support, booking, warehouse, dispatch, sales ops, project "
        "management, or digital marketing roles; recent expansion; poor customer experience; "
        "manual process pain; fragmented software; delayed fulfillment; or public posts/news "
        "showing operational bottlenecks.\n\n"
        "For each lead, find the company, what problem they appear to be facing, proof from "
        "news/posts/job listings, the roles they are hiring for, and the senior person likely "
        "responsible for solving it. Prioritise founders, owners, managing directors, CEOs, "
        "COOs, operations heads, business heads, growth heads, ecommerce heads, marketing heads, "
        "IT managers, plant heads, factory managers, and procurement heads. Include name, title, "
        "email and phone if available, plus a one-line reason for why this is worth outreach."
    ),
    "Cadabams": (
        "Find as many real leads as possible who would BUY, LEASE or RENT a senior-living "
        "home at Cadabams WeNest — and the organisations/communities that have direct access "
        "to those buyers. It's fine to include low-confidence leads.\n\n"
        "Cadabams WeNest sells senior-friendly 1 & 2 BHK homes (around INR 52-67 lakh) in a "
        "luxury senior-living community at Kaggalipura / Kanakapura Road, Bangalore — "
        "barrier-free homes with 24/7 medical and nursing support, assisted living, dining, "
        "wellness, and an assured buyback option. Buyers are typically seniors (55+) wanting "
        "independent or assisted living, retirees downsizing, and adult children or NRIs "
        "arranging a safe home and care for ageing parents in India.\n\n"
        "Search broadly across Bangalore and India for: senior citizens' associations, "
        "pensioner and retired-employee forums, geriatric care and home-nursing agencies, "
        "elder-care NGOs and senior wellness communities, retirement and NRI wealth/financial "
        "advisors, private-banking and NRI relationship teams, estate-planning advisors, "
        "rehab and physiotherapy centres for the elderly, diagnostic chains and clinics with "
        "elderly patients, senior-focused property consultants, and online posts/forums where "
        "families (especially NRIs) ask about retirement homes, assisted living or parent care "
        "in Bangalore.\n\n"
        "For each lead capture: who they are, why they (or their members/clients) would want a "
        "WeNest home, proof from their site/news/posts, a named person or office-bearer to "
        "contact, and email/phone if available, plus a one-line reason to reach out. Surface "
        "even low-confidence buyer leads and flag the uncertainty rather than dropping them."
    ),
    "SNRealtors": (
        "Find real, CONTACTABLE leads for SN Realtors — prioritise leads we can actually "
        "call or email: named professionals and referral channels with discoverable "
        "contacts, plus identifiable HNI/NRI buyers looking for premium Bangalore property.\n\n"
        "SN Realtors is a premium real estate brokerage LLP in Bangalore. They "
        "channel-partner with top developers (Prestige, Sobha, Brigade, Godrej, etc.) and "
        "earn commission by placing wealthy buyers into high-value projects — luxury "
        "apartments, villas, and penthouses typically in the INR 1.5–10 Cr+ range across "
        "Bangalore. Buyers are typically HNIs, NRIs investing back home, startup founders/"
        "CXOs upgrading, senior tech professionals, and families relocating to Bangalore.\n\n"
        "Prioritise REFERRAL CHANNELS that have direct access to these buyers and come with "
        "a named person + public contact: wealth managers and private/NRI bankers, family "
        "offices, premium property consultants and channel partners, corporate relocation "
        "and expat-housing desks, CAs and estate advisors, interior designers and architects "
        "working on luxury homes, and HNI clubs. Also surface NAMED individuals on LinkedIn "
        "in these high-earning cohorts. Use forum/Reddit threads mainly to find which firms, "
        "brokers and advisors are recommended — not anonymous one-off posters.\n\n"
        "For each lead capture: who they are, why they (or their clients) would buy "
        "premium Bangalore property, proof from their site/profile/posts, a named person "
        "to contact, and email/phone if available, plus a one-line reason to reach out. "
        "Rank leads we can actually reach above un-contactable anonymous signals."
    ),
}


def resolve_client_label(template_key: str) -> str:
    """Map visible templates to whatever labels exist in /config."""
    if not ICPS:
        return ""
    needles = {
        "FocusChainLabs": ("focus", "digital"),
        "Cadabams": ("cadabams", "wenest", "senior"),
        "SNRealtors": ("sn realtors", "sn", "realtor", "premium real estate"),
    }.get(template_key, ())
    for label, payload in ICPS.items():
        haystack = f"{label} {payload['data'].get('client', '')} {payload['data'].get('vertical', '')}".lower()
        if any(n in haystack for n in needles):
            return label
    return list(ICPS.keys())[0]


# ── Left drawer navigation ──────────────────────────────────────────────────
APP_NAV = [
    ("agent", "Agent"),
    ("reach", "Reach"),
    ("intel", "Intel"),
    ("proposal", "Proposal"),
    ("finance", "Finance"),
    ("crm", "CRM"),
]


def render_app_drawer() -> None:
    current = st.session_state.get("app_view", "agent")
    with st.sidebar:
        st.markdown(
            """
            <div class="drawer-hamburger" aria-hidden="true">
              <span class="drawer-hamburger-bars"></span>
            </div>
            <div class="drawer-hero">
              <div class="drawer-hero-kicker">FocusChain Labs</div>
              <div class="drawer-hero-title">Modules</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        for view_id, label in APP_NAV:
            if st.button(
                label,
                key=f"nav_{view_id}",
                use_container_width=True,
                type="primary" if current == view_id else "secondary",
            ):
                st.session_state.app_view = view_id
                st.rerun()


def render_agent_hero() -> None:
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


render_app_drawer()

if st.session_state.get("app_view") == "crm":
    render_crm_page()
    st.stop()

if st.session_state.get("app_view") == "reach":
    render_reach_page()
    st.stop()

if st.session_state.get("app_view") == "intel":
    render_intel_page()
    st.stop()

if st.session_state.get("app_view") == "proposal":
    render_proposal_page()
    st.stop()

if st.session_state.get("app_view") == "finance":
    render_finance_page()
    st.stop()

render_agent_hero()

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

    # Surface a run that the hosting platform killed mid-way (OOM / time limit).
    interrupted = st.session_state.pop("interrupted_run", None)
    if interrupted:
        client = interrupted.get("client", "your")
        n = interrupted.get("max_leads", "")
        st.error(
            f"**Your previous {client} run was interrupted before it finished.**\n\n"
            "This almost always means the hosting platform (Streamlit Cloud free tier) "
            "hit its **memory or time limit** and restarted the app — which silently "
            "resets it to this screen. It is not a bug in your brief or keys.\n\n"
            "**To make the next run reliable:**\n"
            f"- Lower **Leads per run** to **5–8** (you had {n}) in Advanced settings below\n"
            "- Run during off-peak hours; the free tier throttles under load\n"
            "- Each lead does ~10 web lookups, so fewer leads = far less memory & time"
        )

    focus_label = resolve_client_label("FocusChainLabs")
    if not st.session_state.get("prompt_text"):
        st.session_state.selected_client = focus_label
        st.session_state.prompt_text = DEFAULT_PROMPTS["FocusChainLabs"]

    # ── TEMPLATE SELECTION ───────────────────────────────────────────────────
    st.markdown('<div class="sec">Template <span class="line"></span></div>',
                unsafe_allow_html=True)

    t_col1, t_col2, t_col3 = st.columns(3, gap="medium")
    template_options = [
        ("FocusChainLabs", "FocusChainLabs", t_col1),
        ("Cadabams", "Cadabams", t_col2),
        ("SNRealtors", "SN Realtors", t_col3),
    ]
    for template_key, label, col in template_options:
        target_label = resolve_client_label(template_key)
        is_sel = st.session_state.selected_client == target_label
        with col:
            if st.button(
                label,
                key=f"template_{template_key}",
                use_container_width=True,
                type="primary" if is_sel else "secondary",
            ):
                st.session_state.selected_client = target_label
                st.session_state.prompt_text = DEFAULT_PROMPTS[template_key]
                # Force the brief box for this client to re-seed with its default
                st.session_state[f"brief_box::{target_label}"] = DEFAULT_PROMPTS[template_key]
                st.session_state.industries = []
                st.session_state.titles = []
                st.rerun()

    client_choice = st.session_state.selected_client or focus_label
    base_icp = ICPS[client_choice]["data"]
    st.session_state.icp_path = ICPS[client_choice]["path"]
    all_industries = base_icp.get("target_industries", [])
    all_titles = base_icp.get("target_titles", [])
    locations = base_icp.get("locations", ["Bangalore"])
    threshold = int(base_icp.get("min_score_threshold", os.getenv("MIN_SCORE_THRESHOLD", 60)))
    # Respect the deployment cap (Streamlit secrets / .env). Heavy runs on the free
    # tier can be killed mid-way and reload to the home screen, so honour the limit.
    max_leads = int(os.getenv("MAX_LEADS_PER_RUN", 30))

    # ── PROMPT + RUN (upload left, send right) ───────────────────────────────
    st.markdown('<div class="sec">Brief <span class="line"></span></div>',
                unsafe_allow_html=True)

    missing_keys = []
    if not os.getenv("GEMINI_API_KEY"): missing_keys.append("GEMINI_API_KEY")
    if not os.getenv("SERPER_API_KEY"): missing_keys.append("SERPER_API_KEY")
    if not (os.getenv("APIFY_API_KEY") or os.getenv("APOLLO_API_KEY")):
        missing_keys.append("APIFY_API_KEY or APOLLO_API_KEY")

    if missing_keys:
        st.markdown(
            f'<div class="notice warn" style="margin-bottom:10px">Missing keys: '
            f'{", ".join(missing_keys)} — add them to .env or Streamlit secrets</div>',
            unsafe_allow_html=True,
        )

    # The brief box uses a per-client key so switching templates always shows the
    # right prompt (a single shared widget key would keep the previous template's
    # text inside the form buffer and submit the wrong brief).
    brief_key = f"brief_box::{client_choice}"
    if brief_key not in st.session_state:
        st.session_state[brief_key] = st.session_state.get("prompt_text", "")

    with st.form("run_form", border=False, clear_on_submit=False):
        prompt = st.text_area(
            "brief",
            height=200,
            placeholder=(
                "Describe what you sell and who you want to reach. The agent will turn it "
                "into web searches, company research, job-post proof, management mapping, "
                "and an Excel sheet."
            ),
            key=brief_key,
            label_visibility="collapsed",
        )
        upload_col, hint_col, _btn = st.columns([0.10, 0.78, 0.12])
        with upload_col:
            uploaded_file = st.file_uploader(
                " ",
                type=["xlsx", "csv"],
                key="previous_list_upload",
                label_visibility="collapsed",
            )
        with hint_col:
            upload_name = (
                uploaded_file.name if uploaded_file
                else st.session_state.exclusion_name
                or "Optional: upload previous list"
            )
            st.markdown(f'<div class="composer-hint">{upload_name}</div>',
                        unsafe_allow_html=True)
        with _btn:
            run = st.form_submit_button("↑")

    if run:
        if not prompt.strip():
            st.warning("Add a brief — even one sentence — so the planner can build a search plan.")
            st.stop()
        # Persist exactly what's visible in the box so the run uses the right brief.
        st.session_state.prompt_text = prompt
        exclusion_path = None
        if uploaded_file:
            safe_name = "".join(
                ch if ch.isalnum() or ch in "._-" else "_"
                for ch in uploaded_file.name
            )
            timestamp = datetime.today().strftime("%Y%m%d_%H%M%S")
            exclusion_path = os.path.join("output", f"exclusion_{timestamp}_{safe_name}")
            with open(exclusion_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            st.session_state.exclusion_path = exclusion_path
            st.session_state.exclusion_name = uploaded_file.name
        else:
            st.session_state.exclusion_path = None
            st.session_state.exclusion_name = ""

        os.environ["MAX_LEADS_PER_RUN"] = str(max_leads)
        os.environ["MIN_SCORE_THRESHOLD"] = str(threshold)
        st.session_state.industries   = all_industries
        st.session_state.locations    = locations
        st.session_state.titles       = all_titles
        st.session_state.max_leads    = max_leads
        st.session_state.events        = []
        st.session_state.sources       = {}
        st.session_state.stage_status  = {}
        st.session_state.api_status    = {}   # service → {state, message, ts}
        st.session_state.gemini_calls  = 0
        st.session_state.run_error     = ""
        st.session_state.run_traceback = ""
        st.session_state.run_warnings  = []
        st.session_state.stage         = "running"
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

    # ── Cost constants (Gemini 3.5 Flash, as of May 2026) ─────────────────────
    # Input: $0.075/M tokens ≈ ₹6.25/M  |  Output: $0.30/M ≈ ₹25/M
    # Per bundle call: ~1500 input + 400 output tokens → ₹0.019
    # Per score call:  ~2000 input + 200 output tokens → ₹0.018
    # Per plan call:   ~800 input  + 300 output tokens → ₹0.013
    COST_PER_PLAN_CALL  = 0.013   # ₹
    COST_PER_SCORE_CALL = 0.018   # ₹
    COST_PER_PITCH_CALL = 0.019   # ₹ (merged bundle)

    # Serper paid: $50/month ÷ 50K searches = $0.001/search × ₹83.5 ≈ ₹0.0835/call.
    # We bill from the live per-run call counter (utils.budget), not a guess.
    COST_PER_SERPER_CALL = 0.001 * 83.5   # ₹ per Serper call
    # Apify free credits vary by actor; show this as a low-confidence estimate.
    COST_PER_CONTACT_RUN = 0

    _SERVICE_META = {
        "gemini": {"label": "Gemini AI",      "icon": "◆"},
        "serper": {"label": "Serper Search",  "icon": "◉"},
        "apollo": {"label": "Apollo",         "icon": "◈"},
        "apify":  {"label": "Apify Scraper",  "icon": "◍"},
        "hunter": {"label": "Hunter Email",   "icon": "◎"},
    }

    def render_api_status(api_status: dict, gemini_calls: int) -> str:
        num_leads = len(st.session_state.get("leads") or [])
        gemini_cost = (
            COST_PER_PLAN_CALL
            + gemini_calls * COST_PER_SCORE_CALL
            + num_leads    * COST_PER_PITCH_CALL
        )
        # Live, real call counts from the per-run budget guard.
        serper_used = budget.used("serper")
        serper_cap  = budget.cap("serper")
        serper_cost = serper_used * COST_PER_SERPER_CALL
        total_est = gemini_cost + serper_cost + COST_PER_CONTACT_RUN
        cost_html = (
            f'<div class="api-cost">'
            f'Est. cost this run: <strong>₹{total_est:.1f}</strong> '
            f'<span class="api-cost-note">'
            f'Gemini ₹{gemini_cost:.2f} · '
            f'Serper {serper_used}/{serper_cap} calls (₹{serper_cost:.1f}) · '
            f'contacts via Apify/public web'
            f'</span></div>'
        )

        services = ["gemini", "serper", "apollo", "apify", "hunter"]
        dots = ""
        alerts = ""
        for svc in services:
            info  = api_status.get(svc, {})
            state = info.get("state", "idle")
            meta  = _SERVICE_META.get(svc, {"label": svc, "icon": "●"})

            # Grey out services with no key configured
            if state == "idle":
                key_env = {
                    "gemini": "GEMINI_API_KEY", "serper": "SERPER_API_KEY",
                    "apollo": "APOLLO_API_KEY", "apify":  "APIFY_API_KEY",
                    "hunter": "HUNTER_API_KEY",
                }.get(svc)
                if key_env and not os.getenv(key_env):
                    state = "no_key"

            cls   = {"ok": "api-ok", "rate_limited": "api-rl",
                     "error": "api-err", "idle": "api-idle",
                     "no_key": "api-nokey"}.get(state, "api-idle")
            label = {"ok": "OK", "rate_limited": "RATE LIMITED",
                     "error": "ERROR", "idle": "Ready",
                     "no_key": "No key"}.get(state, state)

            dots += (
                f'<div class="api-chip {cls}" title="{info.get("message", "")}">'
                f'<span class="api-icon">{meta["icon"]}</span>'
                f'<span class="api-name">{meta["label"]}</span>'
                f'<span class="api-badge">{label}</span>'
                f'</div>'
            )

            if state == "rate_limited":
                alerts += (
                    f'<div class="api-alert">'
                    f'<strong>⚠ {meta["label"]} rate limit reached</strong> — '
                    f'{info.get("message", "")} '
                    f'Pipeline continues but this service is paused. '
                    f'<a href="https://aistudio.google.com" target="_blank" '
                    f'style="color:inherit;text-decoration:underline">Enable billing →</a>'
                    if svc == "gemini" else
                    f'<div class="api-alert">'
                    f'<strong>⚠ {meta["label"]} rate limit reached</strong> — '
                    f'{info.get("message", "")}</div>'
                )
                if svc == "gemini":
                    alerts += '</div>'

        return (
            f'<div class="api-bar">'
            f'<div class="api-chips">{dots}</div>'
            f'{cost_html}'
            f'</div>'
            f'{alerts}'
        )

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

    def _latest(events: list, event_type: str) -> dict:
        return next((e for e in reversed(events) if e.get("type") == event_type), {})

    def agent_state(events: list, stage_status: dict) -> tuple[str, str]:
        stage_labels = {
            "plan": "Planning", "search": "Searching",
            "research": "Researching", "score": "Scoring",
            "enrich": "Enriching", "pitch": "Writing pitches",
        }
        current_stage = next(
            (k for k, v in stage_status.items() if v == "running"), "starting"
        )
        stage_lbl = stage_labels.get(current_stage, current_stage.capitalize())

        # Find most recent meaningful event for the message
        msg = "Initialising pipeline…"
        for ev in reversed(events):
            t = ev.get("type", "")
            if t == "keyword_searching":
                src = ev.get("source", "google")
                src_label = {"serper": "Google", "reddit": "Reddit", "linkedin": "LinkedIn", "naukri": "Naukri"}.get(src, src.capitalize())
                msg = f'Querying {src_label} → &ldquo;{ev["keyword"][:70]}&rdquo;'
                break
            elif t == "research_progress":
                msg = f'Scraping &ldquo;{ev.get("company","")}&rdquo; — fetching homepage, news, LinkedIn &amp; Reddit signals'
                break
            elif t == "company_researched":
                ads = " · ads detected" if ev.get("ad_detected") else ""
                msg = f'&ldquo;{ev.get("company","")}&rdquo; researched — {ev.get("evidence_count", 0)} evidence items{ads}'
                break
            elif t == "score_progress":
                msg = f'Scoring &ldquo;{ev.get("company","")}&rdquo; with Gemini ({ev.get("idx","?")}/{ev.get("total","?")})'
                break
            elif t == "score_result":
                q = "QUALIFIED" if ev.get("qualify") else "filtered"
                msg = f'&ldquo;{ev.get("company","")}&rdquo; → score {ev.get("score",0)}/100 · {q}'
                break
            elif t == "enrich_progress":
                msg = f'Finding name, email, title and phone for &ldquo;{ev.get("company","")}&rdquo;'
                break
            elif t == "pitch_progress":
                msg = f'Writing outreach strategy for &ldquo;{ev.get("company","")}&rdquo;'
                break
            elif t == "plan_ready":
                kws = ev.get("plan", {}).get("trigger_keywords", [])
                msg = f'Search plan ready — {len(kws)} queries generated by Gemini'
                break
            elif t == "search_done":
                msg = (
                    f'Search sweep complete — {ev.get("unique", 0)} unique companies, '
                    f'{ev.get("to_research", 0)} queued for proof gathering'
                )
                break
        return stage_lbl, msg

    def render_agent_console(events: list, stage_status: dict, sources: dict) -> str:
        stage_lbl, msg = agent_state(events, stage_status)
        search_done = _latest(events, "search_done")
        score_done = next(
            (e for e in reversed(events)
             if e.get("type") == "stage_done" and e.get("stage") == "score"),
            {},
        )
        researched = len([e for e in events if e.get("type") == "company_researched"])
        live_sources = len([
            s for s in sources.values()
            if s.get("status") in {"run", "done", "warn"}
        ])
        metrics = [
            (len([e for e in events if e.get("type") == "keyword_done"]), "queries"),
            (search_done.get("unique", 0), "companies"),
            (researched, "researched"),
            (score_done.get("qualified", 0), "qualified"),
        ]
        metric_html = "".join(
            f'<div class="run-metric"><div class="num">{num}</div><div class="lbl">{lbl}</div></div>'
            for num, lbl in metrics
        )
        source_text = (
            f"{live_sources} sources active or completed"
            if live_sources else "Sources are queued"
        )
        return (
            '<div class="run-console">'
            '<div class="run-console-top">'
            '<div class="run-orbit">AI</div>'
            '<div>'
            f'<div class="run-title">Researching your lead market</div>'
            f'<div class="run-sub">{html.escape(source_text)} · {html.escape(stage_lbl)}</div>'
            '</div></div>'
            f'<div class="run-focus"><span class="k">Agent focus</span>{msg}</div>'
            '<div class="run-signal-strip">'
            '<span style="--i:0"></span><span style="--i:1"></span>'
            '<span style="--i:2"></span><span style="--i:3"></span>'
            '<span style="--i:4"></span><span style="--i:5"></span>'
            '<span style="--i:6"></span>'
            '</div>'
            f'<div class="run-metrics">{metric_html}</div>'
            '</div>'
        )

    def render_ticker(events: list, stage_status: dict) -> str:
        stage_lbl, msg = agent_state(events, stage_status)
        return (
            f'<div class="ticker">'
            f'<div class="ticker-pulse"></div>'
            f'<span class="ticker-stage">{stage_lbl}</span>'
            f'<span class="ticker-msg">{msg}</span>'
            f'</div>'
        )

    def render_sources(sources: dict) -> str:
        if not sources: return ""
        rows = ""
        ORDER = ["serper", "reddit", "yahoo", "linkedin_jobs", "yahoo_linkedin", "tracxn", "proxycurl", "naukri"]
        icons = {"serper": "Google", "reddit": "Reddit", "yahoo": "Yahoo",
                 "linkedin_jobs": "LI Jobs", "yahoo_linkedin": "Yahoo·LI", "tracxn": "Tracxn",
                 "proxycurl": "LinkedIn", "naukri": "Naukri"}
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
            right = (f'<span class="feed-count">{count} hits</span>'
                     if status == "done" and count
                     else f'<span class="feed-status">{reason or status_text}</span>')
            rows += (f'<div class="feed-row">'
                     f'<span class="feed-dot {ddot_cls}"></span>'
                     f'<span class="feed-name">{label}</span>{right}</div>')
        return f'<div class="feed">{rows}</div>'

    def render_search_log(events: list) -> str:
        kw_events = [e for e in events if e.get("type") == "keyword_done"][-12:]
        if not kw_events: return '<div style="color:var(--ink-mute);font-size:12px;padding:8px 0">Waiting for search to start…</div>'
        src_badge = {"serper": "google", "linkedin": "linkedin", "reddit": "reddit",
                     "yahoo": "yahoo", "yahoo_linkedin": "yahoo", "linkedin_jobs": "yahoo",
                     "naukri": "naukri"}
        src_label = {"serper": "Google", "linkedin": "LinkedIn", "reddit": "Reddit",
                     "yahoo": "Yahoo", "yahoo_linkedin": "Yahoo·LI", "linkedin_jobs": "LI Jobs",
                     "naukri": "Naukri"}
        rows = ""
        for ev in kw_events:
            src  = ev.get("source", "serper")
            kw   = ev.get("keyword", "")[:65]
            cnt  = ev.get("count", 0)
            cls  = src_badge.get(src, "google")
            lbl  = src_label.get(src, src.capitalize())
            cnt_html = f'<span class="kw-count">{cnt} hits</span>' if cnt else '<span class="kw-count">—</span>'
            rows += (f'<div class="kw-row">'
                     f'<span class="kw-badge kw-{cls}">{lbl}</span>'
                     f'<span class="kw-q">{kw}</span>'
                     f'{cnt_html}</div>')
        return f'<div class="kw-log">{rows}</div>'

    def render_activity(events: list) -> str:
        track = {"company_researched", "score_result", "enrich_result",
                 "research_progress", "score_progress", "enrich_progress", "pitch_progress"}
        recent = [e for e in events if e.get("type") in track][-10:]
        if not recent:
            return '<div style="color:var(--ink-mute);font-size:12px;padding:8px 0">Activity will appear here…</div>'
        rows = ""
        for ev in recent:
            t = ev.get("type", "")
            if t == "score_result":
                score = ev.get("score", 0)
                qualify = ev.get("qualify", False)
                sc_cls = "sc-hi" if score >= 80 else ("sc-mid" if score >= 60 else "sc-lo")
                signal = ev.get("signal", "")[:60]
                dot = "act-done" if qualify else "act-skip"
                status = "QUALIFIED" if qualify else "below threshold"
                rows += (
                    f'<div class="act-row">'
                    f'<div class="act-dot {dot}"></div>'
                    f'<div class="act-body">'
                    f'<div class="act-company">{ev.get("company","")}</div>'
                    + (f'<div class="act-detail">{signal}</div>' if signal else "")
                    + '</div>'
                    + f'<span class="act-score sc {sc_cls}">{score}</span>'
                    + '</div>'
                )
            elif t == "company_researched":
                ads_tag = " · <span style='color:#92400E'>ads detected</span>" if ev.get("ad_detected") else ""
                ev_count = ev.get("evidence_count", 0)
                rows += (
                    f'<div class="act-row">'
                    f'<div class="act-dot act-done"></div>'
                    f'<div class="act-body">'
                    f'<div class="act-company">{ev.get("company","")}</div>'
                    f'<div class="act-detail">{ev_count} evidence items collected{ads_tag}</div>'
                    f'</div></div>'
                )
            elif t == "enrich_result":
                status = ev.get("status", "")
                found = status in {"found", "partial"}
                label = "contact found" if status == "found" else "usable contact path"
                rows += (
                    f'<div class="act-row">'
                    f'<div class="act-dot {"act-done" if found else "act-skip"}"></div>'
                    f'<div class="act-body">'
                    f'<div class="act-company">{ev.get("company","")}</div>'
                    f'<div class="act-detail">{label + " via " + (ev.get("source") or "enrichment") if found else "not found — manual lookup needed"}</div>'
                    f'</div></div>'
                )
            elif t in {"research_progress", "score_progress", "enrich_progress", "pitch_progress"}:
                stage_map = {
                    "research_progress": "scraping homepage & signals",
                    "score_progress":    "scoring with Gemini",
                    "enrich_progress":   "finding decision maker",
                    "pitch_progress":    "writing pitch & strategy",
                }
                rows += (
                    f'<div class="act-row">'
                    f'<div class="act-dot act-run"></div>'
                    f'<div class="act-body">'
                    f'<div class="act-company">{ev.get("company","")}</div>'
                    f'<div class="act-detail">{stage_map.get(t,"")} · {ev.get("idx","?")} of {ev.get("total","?")}</div>'
                    f'</div></div>'
                )
        return f'<div class="act-log">{rows}</div>'

    # Slots — api status bar, research console, ticker, pipeline, live feed, then plan
    api_status_slot = st.empty()
    console_slot    = st.empty()
    ticker_slot     = st.empty()
    pipe_slot       = st.empty()

    col_l, col_r = st.columns([1, 1], gap="large")
    with col_l:
        st.markdown('<div class="sec">Sources <span class="line"></span></div>',
                    unsafe_allow_html=True)
        sources_slot  = st.empty()
        st.markdown('<div class="sec" style="margin-top:18px">Keywords searched <span class="line"></span></div>',
                    unsafe_allow_html=True)
        searchlog_slot = st.empty()
    with col_r:
        st.markdown('<div class="sec">Company activity <span class="line"></span></div>',
                    unsafe_allow_html=True)
        activity_slot = st.empty()

    plan_slot = st.empty()

    console_slot.markdown(
        render_agent_console([], st.session_state.stage_status, st.session_state.sources),
        unsafe_allow_html=True,
    )
    ticker_slot.markdown(render_ticker([], st.session_state.stage_status), unsafe_allow_html=True)
    pipe_slot.markdown(render_pipe(st.session_state.stage_status), unsafe_allow_html=True)

    KNOWN_SOURCES = [
        ("serper",  "Google · web/news"),
        ("reddit",  "Reddit · pain posts"),
        ("yahoo",   "Yahoo · LinkedIn profiles"),
        ("linkedin_jobs", "LinkedIn · hiring signals"),
        ("tracxn",  "Tracxn · funded startups"),
        ("naukri",  "Naukri · job board"),
    ]
    for k, lbl in KNOWN_SOURCES:
        if k not in st.session_state.sources:
            st.session_state.sources[k] = {"label": lbl, "status": "pending",
                                            "count": 0, "reason": "queued"}
    sources_slot.markdown(render_sources(st.session_state.sources), unsafe_allow_html=True)

    # Drop a crash marker — if the platform kills us mid-run, we detect it on reboot.
    _write_run_marker({
        "client":    st.session_state.get("selected_client", "your"),
        "max_leads": st.session_state.get("max_leads", ""),
    })

    try:
        gen = run_pipeline_streaming(
            icp_config_path=st.session_state.icp_path,
            exclusion_list_path=st.session_state.exclusion_path,
            max_leads=st.session_state.max_leads,
            override_industries=st.session_state.industries or None,
            override_locations=st.session_state.locations or None,
            override_titles=st.session_state.titles or None,
            custom_focus=(st.session_state.get("prompt_text") or "").strip(),
            user_prompt=(st.session_state.get("prompt_text") or "").strip(),
        )

        if not hasattr(st.session_state, "api_status"):
            st.session_state.api_status   = {}
        if not hasattr(st.session_state, "gemini_calls"):
            st.session_state.gemini_calls = 0

        def _refresh_all():
            api_status_slot.markdown(
                render_api_status(st.session_state.api_status,
                                  st.session_state.gemini_calls),
                unsafe_allow_html=True,
            )
            console_slot.markdown(
                render_agent_console(
                    st.session_state.events,
                    st.session_state.stage_status,
                    st.session_state.sources,
                ),
                unsafe_allow_html=True,
            )
            ticker_slot.markdown(
                render_ticker(st.session_state.events, st.session_state.stage_status),
                unsafe_allow_html=True)
            pipe_slot.markdown(render_pipe(st.session_state.stage_status), unsafe_allow_html=True)
            activity_slot.markdown(render_activity(st.session_state.events), unsafe_allow_html=True)
            searchlog_slot.markdown(render_search_log(st.session_state.events), unsafe_allow_html=True)

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
                _refresh_all()

            elif t == "stage_done":
                stage = ev.get("stage")
                if stage in [s for s, _ in PIPE_STAGES]:
                    st.session_state.stage_status[stage] = "done"
                _refresh_all()

            elif t == "source_start":
                if st.session_state.stage_status.get("search") != "done":
                    st.session_state.stage_status["search"] = "running"
                k = ev.get("source")
                st.session_state.sources[k] = {
                    **st.session_state.sources.get(k, {}),
                    "label": ev.get("label", k), "status": "run",
                }
                sources_slot.markdown(render_sources(st.session_state.sources), unsafe_allow_html=True)
                _refresh_all()

            elif t == "source_done":
                k = ev.get("source")
                st.session_state.sources[k] = {
                    **st.session_state.sources.get(k, {}),
                    "status": ev.get("status", "done"),
                    "count":  ev.get("count", 0),
                    "reason": ev.get("reason", ""),
                }
                sources_slot.markdown(render_sources(st.session_state.sources), unsafe_allow_html=True)
                _refresh_all()

            elif t == "search_done":
                st.session_state.stage_status["search"] = "done"
                _refresh_all()

            elif t in {"keyword_searching", "keyword_done"}:
                _refresh_all()

            elif t == "plan_ready":
                st.session_state.plan = ev.get("plan", {})
                p = ev["plan"]
                plan_slot.markdown(f"""
                <div class="sec" style="margin-top:24px">Search plan generated <span class="line"></span></div>
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
                _refresh_all()

            elif t == "rate_limit":
                svc = ev.get("service", "unknown")
                msg = ev.get("message", "Rate limit reached")
                st.session_state.api_status[svc] = {"state": "rate_limited", "message": msg}
                warn = f"{svc.upper()} quota exhausted — {msg}"
                if warn not in st.session_state.run_warnings:
                    st.session_state.run_warnings.append(warn)
                _refresh_all()

            elif t in {"plan_ready", "score_result"}:
                # Mark Gemini as healthy + count calls
                st.session_state.api_status["gemini"] = {"state": "ok", "message": ""}
                if t == "score_result":
                    st.session_state.gemini_calls += 1
                _refresh_all()

            elif t == "pitch_progress":
                st.session_state.gemini_calls += 1   # one bundle call per lead
                _refresh_all()

            elif t in {"keyword_done"}:
                # Serper responded — mark healthy
                st.session_state.api_status["serper"] = {"state": "ok", "message": ""}
                _refresh_all()

            elif t == "enrich_result":
                status = ev.get("status", "")
                source = ev.get("source", "")
                if status in ("found", "partial"):
                    if "apify" in source:
                        st.session_state.api_status["apify"] = {"state": "ok", "message": ""}
                    elif source == "apollo":
                        st.session_state.api_status["apollo"] = {"state": "ok", "message": ""}
                _refresh_all()

            elif t in {"research_progress", "enrich_progress",
                       "score_progress", "company_researched"}:
                _refresh_all()

            elif t == "final":
                st.session_state.leads       = ev.get("leads", [])
                st.session_state.output_path = ev.get("output_path")
                st.session_state.stats       = ev.get("stats", {})
                st.session_state.plan        = ev.get("plan", st.session_state.plan)
                st.session_state.run_error   = ev.get("error", "")
                for k, _ in PIPE_STAGES:
                    st.session_state.stage_status[k] = "done"
                _clear_run_marker()  # run finished cleanly
                _refresh_all()
                st.session_state.stage = "results"
                time.sleep(0.35)
                st.rerun()

    except Exception as e:
        # Handled Python error — capture full context and route to the error stage.
        import traceback as _tb
        _clear_run_marker()
        st.session_state.run_error     = str(e)
        st.session_state.run_traceback = _tb.format_exc()
        st.session_state.run_stage_at_error = next(
            (ev.get("stage") for ev in reversed(st.session_state.events)
             if ev.get("type") == "stage_start"), "—"
        )
        st.session_state.stage = "error"
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
        run_error    = st.session_state.get("run_error", "")
        run_warnings = st.session_state.get("run_warnings", [])
        events       = st.session_state.get("events", [])

        # Detect specific failure causes from events
        serper_rate_limited = any(
            e.get("type") == "rate_limit" and "serper" in str(e.get("service", "")).lower()
            for e in events
        )
        no_serper_key = any(
            e.get("type") == "source_done" and e.get("source") == "serper"
            and e.get("status") == "skip" and "key" in str(e.get("reason", "")).lower()
            for e in events
        )
        all_skipped = all(
            e.get("status") in ("skip",)
            for e in events if e.get("type") == "source_done"
        ) and any(e.get("type") == "source_done" for e in events)

        if serper_rate_limited or "serper" in run_error.lower():
            st.error(
                "**Serper search quota exhausted** — no Google searches could run.\n\n"
                "To fix: log in at [serper.dev](https://serper.dev), top up your credits, "
                "then re-run. Your API key and brief are still saved."
            )
        elif no_serper_key or "serper_api_key" in run_error.lower():
            st.error(
                "**SERPER_API_KEY not configured** — add it in Streamlit Cloud → Settings → Secrets.\n\n"
                "At minimum, Serper is required to find companies."
            )
        elif run_error:
            st.error(f"**Run stopped with an error:** {run_error}\n\n"
                     "Check your API keys in Secrets, broaden the brief, or try again.")
        else:
            st.warning(
                "**No leads produced.** Common causes:\n"
                "- A search source was rate-limited or returned nothing\n"
                "- All companies scored below the threshold\n"
                "- The brief was too narrow\n\n"
                "Try again, broaden the brief, or lower the score floor."
            )

        # Show any API warnings collected during the run
        for w in run_warnings:
            st.warning(f"⚠ {w}")

        # Show scored-but-excluded count if available
        scored_events = [e for e in events if e.get("type") == "score_result"]
        if scored_events:
            n_scored = len(scored_events)
            n_qual = sum(1 for e in scored_events if e.get("qualify"))
            st.info(
                f"{n_scored} companies were researched and scored; "
                f"{n_qual} met the threshold. "
                f"{'Lower the Min Score in advanced settings to see more.' if n_scored > n_qual else ''}"
            )

        c1, c2 = st.columns(2)
        with c1:
            if st.button("↻ Re-run same brief", use_container_width=True, type="primary"):
                st.session_state.stage         = "running"
                st.session_state.events        = []
                st.session_state.sources       = {}
                st.session_state.stage_status  = {}
                st.session_state.leads         = []
                st.session_state.run_error     = ""
                st.session_state.run_warnings  = []
                st.rerun()
        with c2:
            if st.button("← New brief", use_container_width=True):
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
        if st.button(
            "Add all to CRM",
            use_container_width=True,
            help="Save these leads to your GitHub-backed CRM",
        ):
            stats = add_leads_to_crm(
                leads_sorted,
                client=st.session_state.get("selected_client", ""),
            )
            st.success(
                f"Added to CRM — {stats.get('added', 0)} new, "
                f"{stats.get('updated', 0)} updated."
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
            esc = html.escape
            score   = lead.get("total_score", 0)
            sc_cls  = "sc-hi" if score >= 80 else ("sc-mid" if score >= 60 else "sc-lo")
            signal  = lead.get("primary_signal", "").strip()
            pain    = lead.get("pain_point", "").strip()
            opening = lead.get("opening_line", "").strip()
            note    = lead.get("outreach_note", "").strip()
            channel = lead.get("reach_channel", "") or best_reach_channel(lead)
            reach   = lead.get("how_to_reach", "") or how_to_reach(lead)
            cn      = lead.get("contact_name", "")
            ct      = lead.get("contact_title", "")
            em      = lead.get("email", "")
            ph      = lead.get("phone", "")
            src     = lead.get("source", "")
            owner   = lead.get("responsible_owner", "")
            running_ads = lead.get("running_ads", False)
            evidence    = lead.get("evidence", []) or []
            selection_note = lead.get("selection_note", "")

            chips = []
            if selection_note or score < 60:
                chips.append('<span style="background:#FEF3C7;color:#92400E;padding:2px 8px;border-radius:4px;font-size:10px;letter-spacing:.08em">VERIFY FIT</span>')
            if running_ads:
                chips.append('<span style="background:#FEF3C7;color:#92400E;padding:2px 8px;border-radius:4px;font-size:10px;letter-spacing:.08em">RUNNING ADS</span>')
            if channel:
                chips.append(f'<span><span class="k">channel</span>{esc(channel)}</span>')
            if cn and "Manual" not in cn:
                chips.append(f'<span><span class="k">contact</span>{esc(cn)}{" · " + esc(ct) if ct else ""}</span>')
            if em and "Manual" not in em and "@" in em:
                chips.append(f'<span><span class="k">email</span>{esc(em)}</span>')
            if ph and "Manual" not in ph:
                chips.append(f'<span><span class="k">phone</span>{esc(ph)}</span>')
            if src:
                chips.append(f'<span><span class="k">via</span>{esc(src)}</span>')

            # Evidence items HTML
            ev_html = ""
            if evidence:
                ev_items = ""
                for ev in evidence[:5]:
                    cat = str(ev.get("category", "news") or "news")
                    cat_cls = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in cat.lower())
                    obs = str(ev.get("observation", "") or "")[:120]
                    ev_items += f'<div class="lc-ev-item"><span class="lc-ev-cat ev-{cat_cls}">{esc(cat)}</span>{esc(obs)}</div>'
                ev_html = f'<div class="lc-evidence"><div class="lc-ev-label">Evidence</div>{ev_items}</div>'

            note_html = ""
            if note:
                note_body = esc(note).replace("\n", "<br>")
                note_html = f'<div class="lc-note"><div class="lc-note-label">Call Strategy</div><div class="lc-note-body">{note_body}</div></div>'

            sig_html   = f'<div class="lc-sig">{esc(signal)}</div>' if signal else ""
            pain_html  = f'<div class="lc-meta" style="margin-top:6px;font-size:12.5px">Pain · {esc(pain)}</div>' if pain else ""
            owner_html = f'<div class="lc-meta" style="margin-top:4px;font-size:12.5px">Owner · {esc(owner)}</div>' if owner else ""
            verify_html = f'<div class="lc-meta" style="margin-top:4px;font-size:12.5px;color:#92400E">Verify · {esc(selection_note)}</div>' if selection_note else ""
            reach_html = f'<div class="lc-reach"><span class="lc-channel">{esc(channel)}</span><div class="lc-reach-text">{esc(reach).replace(chr(10), " ")}</div></div>' if reach else ""
            opener_html = f'<div class="lc-opener">{esc(opening)}</div>' if opening else ""
            chips_html = f'<div class="lc-chips">{"".join(chips)}</div>' if chips else ""

            # Single-line HTML — indented multi-line strings make Streamlit's
            # markdown parser fall back to a code block when a field has newlines.
            card_html = (
                '<div class="lc">'
                '<div class="lc-hd"><div>'
                f'<div class="lc-name">{esc(lead.get("company_name",""))}</div>'
                f'<div class="lc-meta">{esc(lead.get("website","") or "—")}</div>'
                '</div>'
                f'<span class="sc {sc_cls}">{score}/100</span>'
                '</div>'
                f'{sig_html}{pain_html}{owner_html}{verify_html}'
                f'{reach_html}{opener_html}{ev_html}{note_html}{chips_html}'
                '</div>'
            )
            st.markdown(card_html, unsafe_allow_html=True)

    with tab_table:
        df = pd.DataFrame([
            {
                "Rank":    i + 1,
                "Company": l.get("company_name", ""),
                "Score":   l.get("total_score", 0),
                "Contact": l.get("contact_name", ""),
                "Title":   l.get("contact_title", ""),
                "Email":   l.get("email", ""),
                "Phone":   l.get("phone", ""),
                "Channel": l.get("reach_channel", "") or best_reach_channel(l),
                "How To Reach": l.get("how_to_reach", "") or how_to_reach(l),
                "Status":  "Verify" if l.get("selection_note") or int(l.get("total_score", 0) or 0) < 60 else "Ready",
                "Owner":   l.get("responsible_owner", ""),
                "Signal":  l.get("primary_signal", ""),
                "Opening": l.get("opening_line", ""),
            }
            for i, l in enumerate(leads_sorted)
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("<br>", unsafe_allow_html=True)
    b1, b2, b3, _ = st.columns([1, 1, 1, 3])
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
            st.session_state.stage         = "running"
            st.session_state.events        = []
            st.session_state.sources       = {}
            st.session_state.stage_status  = {}
            st.session_state.leads         = []
            st.session_state.run_error     = ""
            st.session_state.run_warnings  = []
            st.rerun()
    with b3:
        if st.button("Open CRM", use_container_width=True):
            st.session_state.app_view = "crm"
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
#  STAGE — ERROR  (persistent error display, survives Streamlit reruns)
# ═══════════════════════════════════════════════════════════════════════════════
elif st.session_state.stage == "error":
    import html as _html

    err_msg  = st.session_state.get("run_error", "An unexpected error occurred.")
    err_tb   = st.session_state.get("run_traceback", "")
    warnings = st.session_state.get("run_warnings", [])
    events   = st.session_state.get("events", [])

    # Human-readable diagnosis based on error text
    err_lower = err_msg.lower()
    if "serper" in err_lower or "429" in err_lower or "quota" in err_lower or "rate limit" in err_lower:
        diagnosis = (
            "**API quota exhausted.** A search or AI service ran out of credits mid-run.\n\n"
            "- **Serper quota**: top up at serper.dev — your key is already saved.\n"
            "- **Gemini quota**: free tier resets daily; try again later or upgrade.\n"
            "Your brief and template are still selected."
        )
    elif "gemini" in err_lower or "google" in err_lower:
        diagnosis = (
            "**Gemini AI call failed.** The GEMINI_API_KEY may be missing, invalid, or "
            "the free-tier quota has been reached.\n\n"
            "Check your key in Streamlit → Settings → Secrets and try again."
        )
    elif "serper_api_key" in err_lower or "api key" in err_lower:
        diagnosis = (
            "**API key missing or invalid.** Check that all required keys "
            "(SERPER_API_KEY, GEMINI_API_KEY) are set in Streamlit → Settings → Secrets."
        )
    elif "filenotfounderror" in err_lower or "icp" in err_lower or "config" in err_lower:
        diagnosis = (
            "**ICP configuration file could not be loaded.** "
            "Make sure the config JSON file exists in the `/config` directory."
        )
    elif "json" in err_lower or "decode" in err_lower:
        diagnosis = (
            "**JSON parsing failed** — Gemini returned an unexpected response. "
            "This is usually transient; try running again."
        )
    else:
        diagnosis = (
            "**The run stopped unexpectedly.** Your brief and template are still selected. "
            "Retry the run or go back to edit the brief."
        )

    st.markdown(
        f'<div class="api-alert">'
        f'<strong>⚠ Run failed</strong> — {_html.escape(err_msg)}'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown(f"\n\n{diagnosis}")

    # Show any rate-limit or quota warnings collected before the crash
    for w in warnings:
        st.warning(f"⚠ {w}")

    # Show events summary (how far the run got)
    scored_events = [e for e in events if e.get("type") == "score_result"]
    search_done   = next((e for e in reversed(events) if e.get("type") == "search_done"), None)
    last_stage    = next(
        (e.get("stage") for e in reversed(events) if e.get("type") == "stage_start"), "—"
    )
    if events:
        parts = [f"Last active stage: **{last_stage}**"]
        if search_done:
            parts.append(f"{search_done.get('unique', 0)} companies found")
        if scored_events:
            parts.append(f"{len(scored_events)} scored")
        st.info("  ·  ".join(parts))

    # Technical traceback in expander
    if err_tb:
        with st.expander("Technical details (traceback)"):
            st.code(err_tb)

    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("↻ Retry run", use_container_width=True, type="primary"):
            st.session_state.stage         = "running"
            st.session_state.events        = []
            st.session_state.sources       = {}
            st.session_state.stage_status  = {}
            st.session_state.api_status    = {}
            st.session_state.gemini_calls  = 0
            st.session_state.run_error     = ""
            st.session_state.run_traceback = ""
            st.session_state.run_warnings  = []
            st.rerun()
    with c2:
        if st.button("← Back to brief", use_container_width=True):
            st.session_state.stage         = "setup"
            st.session_state.run_error     = ""
            st.session_state.run_traceback = ""
            st.session_state.run_warnings  = []
            st.rerun()
