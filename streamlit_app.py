"""
FocusChain LeadGen — Production UI
Notion × Claude aesthetic, real-time pipeline visualization, Streamlit Cloud ready.
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

# Inject Streamlit Cloud secrets → os.environ so all modules use os.getenv()
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, str) and _k not in os.environ:
            os.environ[_k] = _v
except Exception:
    pass

os.makedirs("output", exist_ok=True)

# ── Page Config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="FocusChain LeadGen",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    --bg:        #09090B;
    --surface:   #0F0F12;
    --elevated:  #18181B;
    --card:      #1C1C22;
    --border:    rgba(255,255,255,0.06);
    --border-m:  rgba(255,255,255,0.10);
    --border-h:  rgba(255,255,255,0.18);
    --t1:        #F4F4F5;
    --t2:        #A1A1AA;
    --t3:        #52525B;
    --accent:    #7C3AED;
    --accent2:   #A855F7;
    --glow:      rgba(124,58,237,0.16);
    --green:     #10B981;
    --green-bg:  rgba(16,185,129,0.08);
    --amber:     #F59E0B;
    --amber-bg:  rgba(245,158,11,0.08);
    --red:       #EF4444;
    --r:         10px;
    --rs:        6px;
}

html,body { margin:0; padding:0; }
.stApp {
    background:var(--bg) !important;
    font-family:'Inter',-apple-system,sans-serif !important;
    color:var(--t1) !important;
}
.block-container { padding-top:20px !important; max-width:900px !important; }

/* ─ Sidebar ─ */
[data-testid="stSidebar"] {
    background:var(--surface) !important;
    border-right:1px solid var(--border) !important;
}
[data-testid="stSidebar"] > div:first-child { padding-top:20px !important; }

/* ─ Buttons ─ */
.stButton > button {
    background:var(--accent) !important;
    color:#fff !important;
    border:none !important;
    border-radius:var(--rs) !important;
    font-family:'Inter',sans-serif !important;
    font-weight:600 !important;
    font-size:14px !important;
    letter-spacing:0.01em !important;
    padding:10px 18px !important;
    transition:background 0.15s,transform 0.1s,box-shadow 0.15s !important;
}
.stButton > button:hover {
    background:var(--accent2) !important;
    transform:translateY(-1px) !important;
    box-shadow:0 6px 28px var(--glow) !important;
}
.stButton > button:active { transform:translateY(0) !important; }
.stButton > button:disabled { opacity:0.4 !important; cursor:not-allowed !important; }

/* ─ Inputs ─ */
[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
[data-testid="stMultiSelect"] div[data-baseweb="select"] > div {
    background:var(--elevated) !important;
    border-color:var(--border-m) !important;
    border-radius:var(--rs) !important;
    color:var(--t1) !important;
}
.stTextArea textarea, .stTextInput input {
    background:var(--elevated) !important;
    border-color:var(--border-m) !important;
    color:var(--t1) !important;
    border-radius:var(--rs) !important;
    font-family:'Inter',sans-serif !important;
    font-size:13px !important;
}
.stTextArea textarea:focus, .stTextInput input:focus {
    border-color:var(--accent) !important;
    box-shadow:0 0 0 3px var(--glow) !important;
}
span[data-baseweb="tag"] {
    background:var(--glow) !important;
    border:1px solid rgba(124,58,237,0.3) !important;
    border-radius:99px !important;
}

/* ─ Slider ─ */
[data-testid="stSlider"] [role="slider"] { background:var(--accent) !important; border:2px solid #fff !important; }
[data-testid="stSlider"] div[data-testid="stSliderTrackFill"] { background:var(--accent) !important; }

/* ─ Progress ─ */
[data-testid="stProgress"] > div {
    background:var(--elevated) !important;
    border-radius:99px !important; height:5px !important;
}
[data-testid="stProgress"] > div > div {
    background:linear-gradient(90deg,var(--accent),var(--accent2)) !important;
    border-radius:99px !important;
}

/* ─ Metrics ─ */
[data-testid="stMetric"] {
    background:var(--elevated) !important;
    border:1px solid var(--border) !important;
    border-radius:var(--r) !important;
    padding:14px 18px !important;
}
[data-testid="stMetricLabel"] p { color:var(--t3) !important; font-size:10px !important; letter-spacing:0.08em !important; text-transform:uppercase !important; font-weight:700 !important; }
[data-testid="stMetricValue"] { color:var(--t1) !important; font-weight:700 !important; }

/* ─ Expander ─ */
[data-testid="stExpander"] { background:var(--elevated) !important; border:1px solid var(--border) !important; border-radius:var(--rs) !important; }

/* ─ File uploader ─ */
[data-testid="stFileUploader"] { background:var(--elevated) !important; border:1px dashed var(--border-m) !important; border-radius:var(--r) !important; }

/* ─ Divider ─ */
hr { border-color:var(--border) !important; margin:12px 0 !important; }

/* ─ Animations ─ */
@keyframes pulse  { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.4;transform:scale(.82)} }
@keyframes fade-up{ from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)} }
@keyframes scan   { 0%{left:-35%} 100%{left:115%} }
@keyframes glow   { 0%,100%{box-shadow:0 0 0 0 var(--glow)} 50%{box-shadow:0 0 0 5px transparent} }
@keyframes shimmer{ 0%{background-position:-400% 0} 100%{background-position:400% 0} }

/* ─ Hero ─ */
.hero { text-align:center; padding:52px 20px 36px; animation:fade-up .4s ease; }
.hero-badge {
    display:inline-flex; align-items:center; gap:6px;
    background:var(--glow); border:1px solid rgba(124,58,237,.25);
    border-radius:99px; padding:4px 14px;
    font-size:10px; font-weight:700; color:var(--accent2);
    letter-spacing:.08em; text-transform:uppercase; margin-bottom:22px;
}
.hero-title {
    font-size:clamp(26px,4vw,44px); font-weight:700;
    color:var(--t1); line-height:1.15;
    letter-spacing:-.03em; margin:0 0 14px;
}
.hero-title span { background:linear-gradient(135deg,var(--accent),var(--accent2)); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
.hero-sub { font-size:15px; color:var(--t2); line-height:1.65; max-width:480px; margin:0 auto 44px; }

/* ─ Feature grid ─ */
.feat-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; max-width:820px; margin:0 auto 44px; }
@media(max-width:680px){.feat-grid{grid-template-columns:repeat(2,1fr)}}
.feat { background:var(--elevated); border:1px solid var(--border); border-radius:var(--r); padding:18px 14px; text-align:center; transition:border-color .2s,transform .2s; }
.feat:hover { border-color:var(--border-h); transform:translateY(-2px); }
.feat-ico { font-size:24px; margin-bottom:8px; }
.feat-name { font-size:12px; font-weight:600; color:var(--t1); margin-bottom:3px; }
.feat-desc { font-size:11px; color:var(--t3); line-height:1.5; }

/* ─ Tip box ─ */
.tip { display:flex; align-items:center; gap:10px; background:var(--elevated); border:1px solid var(--border); border-radius:var(--r); padding:13px 16px; font-size:13px; color:var(--t2); max-width:600px; margin:0 auto; }

/* ─ Pipeline wrapper ─ */
.pl-wrap { max-width:760px; margin:0 auto; animation:fade-up .3s ease; }

/* ─ Stage header ─ */
.pl-header {
    display:flex; align-items:center; gap:12px;
    padding:13px 18px; background:var(--elevated);
    border:1px solid var(--border-m); border-radius:var(--r); margin-bottom:14px;
}
.live-dot { width:9px; height:9px; border-radius:50%; background:var(--green); animation:pulse 1.4s infinite; flex-shrink:0; }
.pl-stage { font-size:14px; font-weight:600; flex:1; }
.pl-meta { font-size:11px; color:var(--t3); }

/* ─ Source cards ─ */
.sources { display:flex; flex-direction:column; gap:6px; margin-bottom:14px; }
.src {
    display:flex; align-items:center; gap:12px;
    background:var(--elevated); border:1px solid var(--border);
    border-radius:var(--rs); padding:11px 16px;
    transition:border-color .3s; position:relative; overflow:hidden;
}
.src.running { border-color:rgba(245,158,11,.4); animation:glow 2s infinite; }
.src.done    { border-color:rgba(16,185,129,.3); }
.src.skip    { opacity:.45; }
.src.warn    { border-color:rgba(245,158,11,.25); }
.scan-line {
    position:absolute; top:0; left:0; width:35%; height:100%;
    background:linear-gradient(90deg,transparent,rgba(245,158,11,.07),transparent);
    animation:scan 1.8s linear infinite;
}
.src-dot { width:7px; height:7px; border-radius:50%; flex-shrink:0; }
.src-dot.pending { background:var(--t3); }
.src-dot.running { background:var(--amber); animation:pulse .9s infinite; }
.src-dot.done    { background:var(--green); }
.src-dot.skip    { background:var(--t3); }
.src-dot.warn    { background:var(--amber); }
.src-lbl { font-size:13px; font-weight:500; flex:1; }
.src-badge { font-size:10px; font-weight:700; padding:2px 9px; border-radius:99px; }
.src-badge.done { background:var(--green-bg); color:var(--green); }
.src-badge.warn { background:var(--amber-bg); color:var(--amber); }
.src-note { font-size:11px; color:var(--t3); }

/* ─ Progress block ─ */
.prog-block { background:var(--elevated); border:1px solid var(--border); border-radius:var(--r); padding:15px 18px; margin-bottom:12px; }
.prog-lbl { font-size:11px; font-weight:700; color:var(--t3); letter-spacing:.07em; text-transform:uppercase; margin-bottom:7px; }
.prog-company { font-family:'JetBrains Mono',monospace; font-size:11px; color:var(--t3); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin-top:7px; }

/* ─ Score feed ─ */
.feed-hdr { font-size:10px; font-weight:700; letter-spacing:.08em; color:var(--t3); text-transform:uppercase; margin:14px 0 7px; }
.feed-item {
    display:flex; align-items:center; gap:10px;
    padding:7px 0; border-bottom:1px solid var(--border);
    animation:fade-up .25s ease;
}
.feed-co { font-size:12px; color:var(--t2); flex:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.feed-bar-bg { width:68px; height:3px; background:var(--border); border-radius:99px; overflow:hidden; }
.feed-bar { height:100%; border-radius:99px; }
.feed-num { font-size:11px; font-weight:700; width:24px; text-align:right; }
.feed-q { font-size:10px; font-weight:700; padding:2px 7px; border-radius:99px; }
.feed-q.yes { background:var(--green-bg); color:var(--green); }
.feed-q.no  { background:rgba(82,82,91,.18); color:var(--t3); }

/* ─ Results ─ */
.res-header {
    display:flex; align-items:center; gap:12px;
    padding:15px 20px; background:var(--green-bg);
    border:1px solid rgba(16,185,129,.22); border-radius:var(--r);
    margin-bottom:22px; animation:fade-up .3s ease;
}
.res-title { font-size:15px; font-weight:700; }
.res-sub   { font-size:12px; color:var(--t2); margin-top:2px; }

.lead-card {
    background:var(--card); border:1px solid var(--border);
    border-radius:var(--r); overflow:hidden;
    margin:10px 0; animation:fade-up .3s ease;
    transition:border-color .2s;
}
.lead-card:hover { border-color:var(--border-h); }
.lead-stripe { height:3px; }
.lead-body  { padding:18px 22px; }
.lead-top   { display:flex; align-items:flex-start; gap:12px; margin-bottom:11px; }
.lead-rank  { font-size:11px; font-weight:700; color:var(--t3); width:22px; flex-shrink:0; padding-top:3px; }
.lead-info  { flex:1; }
.lead-name  { font-size:15px; font-weight:600; color:var(--t1); margin:0 0 3px; }
.lead-sub   { font-size:12px; color:var(--t3); }
.lead-score-num   { font-size:22px; font-weight:700; }
.lead-score-label { font-size:9px; color:var(--t3); text-align:right; letter-spacing:.06em; text-transform:uppercase; }
.lead-bar-bg { height:3px; background:var(--border); border-radius:99px; overflow:hidden; margin:10px 0 14px; }
.lead-bar    { height:100%; border-radius:99px; }
.chips       { display:flex; flex-wrap:wrap; gap:7px; margin-bottom:12px; }
.chip {
    display:inline-flex; align-items:center; gap:5px;
    background:var(--elevated); border:1px solid var(--border);
    border-radius:99px; padding:4px 11px;
    font-size:11px; color:var(--t2);
}
.chip a { color:var(--accent2) !important; text-decoration:none !important; }
.chip a:hover { text-decoration:underline !important; }
.signal-row { display:flex; align-items:flex-start; gap:8px; font-size:12px; color:var(--t2); margin-bottom:10px; }
.sig-dot { width:6px; height:6px; border-radius:50%; background:var(--accent2); flex-shrink:0; margin-top:4px; }
.pitch-box {
    background:var(--elevated); border-left:2px solid var(--accent);
    padding:11px 15px; border-radius:0 var(--rs) var(--rs) 0;
    font-size:13px; color:var(--t2); font-style:italic; line-height:1.65;
}

/* ─ Sidebar helpers ─ */
.sb-lbl { font-size:10px; font-weight:700; letter-spacing:.09em; color:var(--t3); text-transform:uppercase; margin:14px 0 5px; display:block; }
.api-row { display:flex; align-items:center; gap:8px; padding:5px 0; }
.api-dot { width:6px; height:6px; border-radius:50%; flex-shrink:0; }
.api-name { font-size:12px; flex:1; color:var(--t2); }
.api-tag  { font-size:10px; color:var(--t3); }

/* ─ Hide Streamlit chrome ─ */
#MainMenu, footer,
[data-testid="stToolbar"],
[data-testid="stDecoration"] { display:none !important; }

/* ─ Radio (ICP selector) ─ */
[data-testid="stRadio"] > div { flex-direction:column; gap:4px; }
[data-testid="stRadio"] label {
    background:var(--elevated); border:1px solid var(--border);
    border-radius:var(--rs); padding:10px 14px !important;
    cursor:pointer; transition:border-color .15s;
    font-size:13px !important;
}
[data-testid="stRadio"] label:has(input:checked) {
    border-color:rgba(124,58,237,.5) !important;
    background:var(--glow) !important;
}

/* ─ Number input ─ */
[data-testid="stNumberInput"] input { background:var(--elevated) !important; border-color:var(--border-m) !important; color:var(--t1) !important; border-radius:var(--rs) !important; }
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────
def _init_state():
    defaults = {
        "app_state": "idle",      # idle | running | done
        "run_config": {},
        "final_leads": [],
        "output_path": None,
        "stats": {},
        "pipeline_error": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# ── HTML helpers ──────────────────────────────────────────────────────────────

def _score_color(score: int) -> str:
    if score >= 80:
        return "#10B981"
    if score >= 60:
        return "#F59E0B"
    return "#52525B"


def _src_card_html(label: str, status: str, count: int = 0, reason: str = "") -> str:
    dot = status
    scan = '<div class="scan-line"></div>' if status == "running" else ""
    status_text = {
        "pending": "waiting…",
        "running": "scanning…",
        "done":    f"{count:,} signals",
        "skip":    reason or "skipped",
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
        <div class="src-dot {dot}"></div>
        <span class="src-lbl">{label}</span>
        {badge}
        <span class="src-note">{status_text}</span>
    </div>"""


def _score_bar_html(score: int, height: str = "3px", cls: str = "lead-bar-bg", fill_cls: str = "lead-bar") -> str:
    color = _score_color(score)
    return f"""
    <div class="{cls}">
        <div class="{fill_cls}" style="width:{score}%;background:{color};"></div>
    </div>"""


def _lead_card_html(rank: int, lead: dict) -> str:
    score = lead.get("total_score", 0)
    color = _score_color(score)
    tier = "high" if score >= 80 else "medium" if score >= 60 else "low"

    name  = lead.get("company_name", "—")
    web   = lead.get("website", "")
    src   = lead.get("source", "")
    vrt   = lead.get("vertical", "")
    signal = lead.get("primary_signal", "")
    pain   = lead.get("pain_point", "")
    pitch  = lead.get("opening_line", "")

    cname  = lead.get("contact_name", "")
    ctitle = lead.get("contact_title", "")
    email  = lead.get("email", "")
    li_url = lead.get("linkedin_url", "")

    web_chip = f'<span class="chip">🔗 <a href="{web}" target="_blank">{web[:35]}…</a></span>' if web and web.startswith("http") else ""
    email_chip = f'<span class="chip">✉ {email}</span>' if email and "Manual" not in email else ""
    li_chip = f'<span class="chip">💼 <a href="{li_url}" target="_blank">LinkedIn</a></span>' if li_url and "Manual" not in li_url else ""
    src_chip = f'<span class="chip">📡 {src}</span>' if src else ""

    contact_line = ""
    if cname and "Manual" not in cname:
        contact_line = f'<span class="chip">👤 {cname}{(" · " + ctitle) if ctitle and "Manual" not in ctitle else ""}</span>'

    pitch_html = f'<div class="pitch-box">{pitch}</div>' if pitch else ""
    pain_html  = f'<div class="signal-row"><div class="sig-dot"></div><span><b>Pain:</b> {pain}</span></div>' if pain else ""
    signal_html = f'<div class="signal-row"><div class="sig-dot" style="background:var(--amber)"></div><span><b>Signal:</b> {signal}</span></div>' if signal else ""

    return f"""
    <div class="lead-card">
        <div class="lead-stripe" style="background:{color};"></div>
        <div class="lead-body">
            <div class="lead-top">
                <div class="lead-rank">#{rank}</div>
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
            <div class="chips">
                {contact_line}
                {email_chip}
                {li_chip}
                {web_chip}
                {src_chip}
            </div>
            {signal_html}
            {pain_html}
            {pitch_html}
        </div>
    </div>"""


# ── Sidebar ───────────────────────────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        # Logo
        st.markdown("""
        <div style="padding:0 4px 16px;">
            <div style="display:flex;align-items:center;gap:10px;">
                <div style="font-size:22px;">⚡</div>
                <div>
                    <div style="font-size:15px;font-weight:700;color:var(--t1);">FocusChain</div>
                    <div style="font-size:10px;color:var(--t3);letter-spacing:.07em;text-transform:uppercase;">LeadGen Agent</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        st.divider()

        # ── ICP Selector ──
        st.markdown('<span class="sb-lbl">Client ICP</span>', unsafe_allow_html=True)
        config_files = sorted(glob.glob("config/*.json"))
        if not config_files:
            st.error("No config files found in /config/")
            return None

        config_labels = {
            f.split("/")[-1].replace(".json", "").replace("_", " ").title(): f
            for f in config_files
        }
        selected_label = st.radio(
            "ICP", list(config_labels.keys()), label_visibility="collapsed"
        )
        selected_config_path = config_labels[selected_label]

        with open(selected_config_path) as _f:
            icp_preview = json.load(_f)

        st.markdown(f"""
        <div style="background:var(--elevated);border:1px solid var(--border);border-radius:var(--rs);
                    padding:10px 13px;margin:6px 0 2px;font-size:12px;color:var(--t2);">
            <b style="color:var(--t1);">{icp_preview.get('client','')}</b>
            &nbsp;·&nbsp; {icp_preview.get('vertical','')}<br>
            <span style="color:var(--t3);">{', '.join(icp_preview.get('locations',[]))}</span>
        </div>
        """, unsafe_allow_html=True)

        st.divider()

        # ── Natural Language Focus ──
        st.markdown('<span class="sb-lbl">What are you looking for?</span>', unsafe_allow_html=True)
        custom_focus = st.text_area(
            "Focus", placeholder="e.g. Manufacturing companies that recently hired a new CTO and are upgrading their ERP…",
            height=90, label_visibility="collapsed",
            help="Natural language context — the AI weighs this when scoring leads."
        )

        # ── Industry Filter ──
        st.markdown('<span class="sb-lbl">Target Industries</span>', unsafe_allow_html=True)
        all_industries = icp_preview.get("target_industries", [])
        selected_industries = st.multiselect(
            "Industries", options=all_industries,
            default=all_industries, label_visibility="collapsed"
        )

        # ── Location ──
        st.markdown('<span class="sb-lbl">Location</span>', unsafe_allow_html=True)
        location_default = ", ".join(icp_preview.get("locations", ["Bangalore"]))
        location_val = st.text_input(
            "Location", value=location_default, label_visibility="collapsed"
        )

        # ── Controls ──
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            st.markdown('<span class="sb-lbl">Max Leads</span>', unsafe_allow_html=True)
            max_leads = st.number_input("Max Leads", min_value=1, max_value=50,
                                        value=10, label_visibility="collapsed")
        with col2:
            st.markdown('<span class="sb-lbl">Min Score</span>', unsafe_allow_html=True)
            min_score = st.number_input("Min Score", min_value=0, max_value=99,
                                        value=int(os.getenv("MIN_SCORE_THRESHOLD", 60)),
                                        label_visibility="collapsed")

        # ── Advanced ──
        with st.expander("Advanced"):
            exclusion_file = st.file_uploader(
                "Exclusion list (Excel)", type=["xlsx"],
                help="Companies already contacted — they will be skipped."
            )

        # ── API Status ──
        with st.expander("API Status"):
            apis = [
                ("Gemini",    "GEMINI_API_KEY",    True),
                ("Serper",    "SERPER_API_KEY",    True),
                ("Apollo",    "APOLLO_API_KEY",    True),
                ("ProxyCurl", "PROXYCURL_API_KEY", False),
                ("Tracxn",    "TRACXN_API_KEY",    False),
            ]
            for name, key, required in apis:
                has_key = bool(os.getenv(key))
                dot_color = "#10B981" if has_key else "#EF4444" if required else "#F59E0B"
                tag = "" if has_key else ("required" if required else "optional")
                st.markdown(f"""
                <div class="api-row">
                    <div class="api-dot" style="background:{dot_color};"></div>
                    <span class="api-name">{name}</span>
                    <span class="api-tag">{tag}</span>
                </div>""", unsafe_allow_html=True)

        st.divider()

        # ── Run Button ──
        is_running = st.session_state.app_state == "running"
        run_label  = "⏳ Running…" if is_running else "▶ Run Agent"
        run_clicked = st.button(run_label, use_container_width=True,
                                disabled=is_running, type="primary")

        if run_clicked and not is_running:
            # Save exclusion file
            exclusion_path = None
            if exclusion_file:
                exclusion_path = "output/exclusion_upload.xlsx"
                with open(exclusion_path, "wb") as _ef:
                    _ef.write(exclusion_file.read())

            # Inject min_score into env so scorer picks it up
            os.environ["MIN_SCORE_THRESHOLD"] = str(int(min_score))

            st.session_state.run_config = {
                "icp_config_path": selected_config_path,
                "exclusion_list_path": exclusion_path,
                "max_leads": int(max_leads),
                "override_industries": selected_industries or all_industries,
                "custom_focus": custom_focus.strip() if custom_focus else None,
            }
            st.session_state.app_state = "running"
            st.session_state.pipeline_error = None
            st.rerun()

        # Reset button when done
        if st.session_state.app_state == "done":
            if st.button("↩ New Run", use_container_width=True):
                st.session_state.app_state = "idle"
                st.session_state.final_leads = []
                st.session_state.output_path = None
                st.session_state.stats = {}
                st.rerun()

        return selected_config_path


# ── Idle View ─────────────────────────────────────────────────────────────────

def render_idle():
    st.markdown("""
    <div class="hero">
        <div class="hero-badge">⚡ Powered by Gemini 3.5 Flash</div>
        <h1 class="hero-title">Find your next<br><span>qualified lead</span></h1>
        <p class="hero-sub">
            Configure your ICP in the sidebar, describe what you're looking for,
            and let the agent do the rest — from signal detection to personalised outreach.
        </p>
        <div class="feat-grid">
            <div class="feat">
                <div class="feat-ico">📡</div>
                <div class="feat-name">Signal Detection</div>
                <div class="feat-desc">4 live sources scan for buying signals in parallel</div>
            </div>
            <div class="feat">
                <div class="feat-ico">🤖</div>
                <div class="feat-name">AI Scoring</div>
                <div class="feat-desc">Gemini scores each company across 4 dimensions</div>
            </div>
            <div class="feat">
                <div class="feat-ico">👤</div>
                <div class="feat-name">Contact Finder</div>
                <div class="feat-desc">Apollo enrichment finds the right decision maker</div>
            </div>
            <div class="feat">
                <div class="feat-ico">✍️</div>
                <div class="feat-name">1:1 Pitches</div>
                <div class="feat-desc">Personalised opening lines, not templates</div>
            </div>
        </div>
        <div class="tip">
            💡 &nbsp; Select a client ICP in the sidebar, describe your focus, and click <b>Run Agent</b>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ── Pipeline View (live) ──────────────────────────────────────────────────────

def render_pipeline_live():
    from main import run_pipeline_streaming

    cfg = st.session_state.run_config

    # ── Placeholders ──
    header_ph  = st.empty()
    sources_ph = st.empty()
    progress_ph = st.empty()
    feed_ph    = st.empty()

    # ── Internal state ──
    ps = {
        "stage": "search",
        "stage_label": "Scanning signal sources",
        "sources": {
            "serper":    {"label": "Google Search (Serper)",     "status": "pending", "count": 0, "reason": ""},
            "tracxn":    {"label": "Tracxn — Funded Startups",   "status": "pending", "count": 0, "reason": ""},
            "proxycurl": {"label": "LinkedIn Jobs (ProxyCurl)",  "status": "pending", "count": 0, "reason": ""},
            "naukri":    {"label": "Naukri Job Board (scraper)", "status": "pending", "count": 0, "reason": ""},
        },
        "research_idx": 0, "research_total": 0,
        "score_idx":    0, "score_total":    0,
        "enrich_idx":   0, "enrich_total":   0,
        "pitch_idx":    0, "pitch_total":    0,
        "current_company": "",
        "feed_items": [],
        "total_raw": 0, "total_unique": 0,
    }

    STAGE_LABELS = {
        "search":   "01 · Scanning signal sources",
        "research": "02 · Researching companies",
        "score":    "03 · AI scoring with Gemini",
        "enrich":   "04 · Finding decision makers",
        "pitch":    "05 · Writing personalised pitches",
    }

    pilot = os.getenv("PILOT_MODE", "true").lower() == "true"
    pilot_tag = '<span class="pl-meta">pilot mode</span>' if pilot else ""

    def _draw_header():
        header_ph.markdown(f"""
        <div class="pl-header">
            <div class="live-dot"></div>
            <span class="pl-stage">{STAGE_LABELS.get(ps["stage"], ps["stage_label"])}</span>
            {pilot_tag}
        </div>""", unsafe_allow_html=True)

    def _draw_sources():
        html = '<div class="sources">'
        for src_id, src in ps["sources"].items():
            html += _src_card_html(src["label"], src["status"], src["count"], src["reason"])
        html += "</div>"
        sources_ph.markdown(html, unsafe_allow_html=True)

    def _draw_progress():
        stage = ps["stage"]
        idx_map = {
            "research": (ps["research_idx"], ps["research_total"], "Researching"),
            "score":    (ps["score_idx"],    ps["score_total"],    "Scoring with AI"),
            "enrich":   (ps["enrich_idx"],   ps["enrich_total"],   "Finding contacts"),
            "pitch":    (ps["pitch_idx"],     ps["pitch_total"],    "Writing pitches"),
        }
        if stage not in idx_map:
            progress_ph.empty()
            return

        idx, total, lbl = idx_map[stage]
        pct = idx / max(total, 1)

        with progress_ph.container():
            st.markdown(f'<div class="prog-block"><div class="prog-lbl">{lbl}</div>', unsafe_allow_html=True)
            st.progress(pct)
            st.markdown(
                f'<div class="prog-company">▸ {ps["current_company"]}'
                f'  <span style="float:right;">{idx} / {total}</span></div></div>',
                unsafe_allow_html=True
            )

    def _draw_feed():
        items = ps["feed_items"]
        if not items:
            feed_ph.empty()
            return
        html = '<div class="feed-hdr">Live scoring feed</div>'
        for item in items[-8:]:
            sc = item.get("score", 0)
            cl = _score_color(sc)
            qc = "yes" if item.get("qualify") else "no"
            qt = "✓" if item.get("qualify") else "✗"
            html += f"""
            <div class="feed-item">
                <span class="feed-co">{item["company"]}</span>
                <div class="feed-bar-bg"><div class="feed-bar" style="width:{sc}%;background:{cl};"></div></div>
                <span class="feed-num" style="color:{cl};">{sc}</span>
                <span class="feed-q {qc}">{qt}</span>
            </div>"""
        feed_ph.markdown(html, unsafe_allow_html=True)

    # ── Initial draw ──
    _draw_header()
    _draw_sources()

    # ── Generator loop ──
    try:
        for event in run_pipeline_streaming(**cfg):
            t = event.get("type", "")

            if t == "source_start":
                src = event.get("source", "")
                if src in ps["sources"]:
                    ps["sources"][src]["status"] = "running"
                _draw_sources()

            elif t == "source_done":
                src = event.get("source", "")
                if src in ps["sources"]:
                    ps["sources"][src].update({
                        "status": event.get("status", "done"),
                        "count":  event.get("count", 0),
                        "reason": event.get("reason", ""),
                    })
                _draw_sources()

            elif t == "search_done":
                ps["total_raw"]    = event.get("raw", 0)
                ps["total_unique"] = event.get("unique", 0)

            elif t == "stage_start":
                stage = event.get("stage", "")
                ps["stage"] = stage
                total = event.get("total", 0)
                if stage == "research": ps["research_total"] = total
                if stage == "score":    ps["score_total"]    = total
                if stage == "enrich":   ps["enrich_total"]   = total
                if stage == "pitch":    ps["pitch_total"]    = total
                _draw_header()
                _draw_progress()

            elif t == "research_progress":
                ps["research_idx"]    = event.get("idx", 0)
                ps["current_company"] = event.get("company", "")
                _draw_progress()

            elif t == "score_progress":
                ps["score_idx"]       = event.get("idx", 0)
                ps["current_company"] = event.get("company", "")
                _draw_progress()

            elif t == "score_result":
                ps["feed_items"].append(event)
                _draw_feed()

            elif t == "enrich_progress":
                ps["enrich_idx"]      = event.get("idx", 0)
                ps["current_company"] = event.get("company", "")
                _draw_progress()

            elif t == "pitch_progress":
                ps["pitch_idx"]       = event.get("idx", 0)
                ps["current_company"] = event.get("company", "")
                _draw_progress()

            elif t == "final":
                st.session_state.final_leads = event.get("leads", [])
                st.session_state.output_path  = event.get("output_path")
                st.session_state.stats        = event.get("stats", {})
                err = event.get("error")
                if err:
                    st.session_state.pipeline_error = err
                break

    except Exception as exc:
        st.session_state.pipeline_error = str(exc)

    # Transition to done
    st.session_state.app_state = "done"

    # Clear live UI
    header_ph.empty()
    sources_ph.empty()
    progress_ph.empty()
    feed_ph.empty()

    st.rerun()


# ── Results View ──────────────────────────────────────────────────────────────

def render_results():
    leads  = st.session_state.final_leads
    path   = st.session_state.output_path
    stats  = st.session_state.stats
    error  = st.session_state.pipeline_error

    if error:
        st.error(f"Pipeline error: {error}")
        return

    if not leads:
        st.warning("No qualified leads found. Try lowering the Min Score threshold or adding API keys.")
        return

    # ── Header ──
    n = stats.get("total_leads", len(leads))
    avg = stats.get("avg_score", 0)
    top = stats.get("top_score", 0)
    qrate = stats.get("qualification_rate", "—")

    st.markdown(f"""
    <div class="res-header">
        <span style="font-size:22px;">✓</span>
        <div>
            <div class="res-title">Pipeline complete — {n} lead{'s' if n != 1 else ''} ready</div>
            <div class="res-sub">Avg score {avg} · Top score {top} · Qualification rate {qrate}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Metrics ──
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Leads Found",    n)
    c2.metric("Avg Score",      avg)
    c3.metric("Top Score",      top)
    c4.metric("Qualify Rate",   qrate)

    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

    # ── Tabs: Cards | Table | Download ──
    tab_cards, tab_table, tab_dl = st.tabs(["📋 Lead Cards", "📊 Table View", "⬇️ Download"])

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
                label="⬇️ Download Excel",
                data=data,
                file_name=os.path.basename(path),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
            st.markdown(
                f'<div style="font-size:11px;color:var(--t3);margin-top:8px;">'
                f'{path} · {round(len(data)/1024, 1)} KB</div>',
                unsafe_allow_html=True
            )


# ── App Router ────────────────────────────────────────────────────────────────

def main():
    render_sidebar()

    state = st.session_state.app_state

    if state == "idle":
        render_idle()
    elif state == "running":
        st.markdown('<div class="pl-wrap">', unsafe_allow_html=True)
        render_pipeline_live()   # blocks until pipeline finishes, then st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
    elif state == "done":
        render_results()


main()
