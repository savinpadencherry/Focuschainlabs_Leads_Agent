"""Global feedback floater — available on every FocusChain Labs screen."""

from __future__ import annotations

import html

import streamlit as st

from utils.feedback_store import (
    CATEGORY_LABELS,
    FEEDBACK_CATEGORIES,
    append_feedback,
    load_feedback,
    save_feedback,
)

PAGE_LABELS: dict[str, str] = {
    "agent": "Agent",
    "reach": "Reach",
    "intel": "Intel",
    "proposal": "Proposal",
    "finance": "Finance",
    "crm": "CRM",
}

FEEDBACK_CSS = """
<style>
/* Clean premium feedback floater — bottom-right, lifted clear of forms + Manage app */
div[class*="st-key-fcl_feedback_floater"] {
    position: fixed !important;
    bottom: 96px !important;
    right: 24px !important;
    left: auto !important;
    z-index: 9999 !important;
    width: 56px !important;
    height: 56px !important;
    margin: 0 !important;
    padding: 0 !important;
    pointer-events: auto !important;
}
div[class*="st-key-fcl_feedback_floater"] [data-testid="stVerticalBlock"],
div[class*="st-key-fcl_feedback_floater"] [data-testid="stElementContainer"] {
    position: static !important;
    margin: 0 !important;
    padding: 0 !important;
    width: 56px !important;
    height: 56px !important;
}
div[class*="st-key-fcl_feedback_floater"] [data-testid="stButton"] {
    margin: 0 !important;
}
div[class*="st-key-fcl_feedback_floater"] .stButton > button,
div[class*="st-key-fcl_feedback_floater"] [data-testid="stBaseButton-primary"],
div[class*="st-key-fcl_feedback_floater"] [data-testid="stBaseButton-secondary"],
div[class*="st-key-fcl_feedback_floater"] button {
    width: 56px !important;
    min-width: 56px !important;
    height: 56px !important;
    border-radius: 50% !important;
    padding: 0 !important;
    font-size: 22px !important;
    line-height: 1 !important;
    background: linear-gradient(145deg, #3cb868 0%, #2E8B4D 48%, #1f6b3a 100%) !important;
    background-color: #2E8B4D !important;
    color: #fff !important;
    border: 1.5px solid rgba(255,255,255,.28) !important;
    box-shadow:
      0 10px 28px -8px rgba(46,139,77,.58),
      0 4px 12px -4px rgba(15,42,51,.25),
      inset 0 1px 0 rgba(255,255,255,.28) !important;
    transition: transform .18s var(--ease-out), box-shadow .18s var(--ease-out) !important;
}
div[class*="st-key-fcl_feedback_floater"] .stButton > button:hover,
div[class*="st-key-fcl_feedback_floater"] [data-testid="stBaseButton-primary"]:hover,
div[class*="st-key-fcl_feedback_floater"] [data-testid="stBaseButton-secondary"]:hover,
div[class*="st-key-fcl_feedback_floater"] button:hover {
    background: linear-gradient(145deg, #45c472 0%, #32a05a 48%, #247a42 100%) !important;
    background-color: #32a05a !important;
    color: #fff !important;
    transform: translateY(-2px) scale(1.03) !important;
    box-shadow:
      0 16px 36px -10px rgba(46,139,77,.65),
      0 6px 16px -6px rgba(15,42,51,.28),
      inset 0 1px 0 rgba(255,255,255,.32) !important;
}
div[class*="st-key-fcl_feedback_floater"] .stButton > button:active,
div[class*="st-key-fcl_feedback_floater"] button:active {
    transform: translateY(0) scale(.98) !important;
}

.fcl-feedback-dialog-kicker {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px; font-weight: 700; letter-spacing: .18em;
    text-transform: uppercase; color: var(--green); margin-bottom: 6px;
}
.fcl-feedback-dialog-title {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 22px; font-weight: 800; color: var(--ink); margin: 0 0 6px;
}
.fcl-feedback-dialog-sub {
    color: var(--ink-mute); font-size: 13px; line-height: 1.45; margin-bottom: 14px;
}
.fcl-feedback-page-pill {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 5px 10px; border-radius: 999px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
    color: var(--green); background: var(--green-bg);
    border: 1px solid rgba(46,139,77,.22); margin-bottom: 12px;
}

@media (max-width: 720px) {
    div[class*="st-key-fcl_feedback_floater"] {
        bottom: 20px !important;
        right: 16px !important;
        width: 52px !important;
        height: 52px !important;
    }
    div[class*="st-key-fcl_feedback_floater"] [data-testid="stVerticalBlock"],
    div[class*="st-key-fcl_feedback_floater"] [data-testid="stElementContainer"] {
        width: 52px !important;
        height: 52px !important;
    }
    div[class*="st-key-fcl_feedback_floater"] .stButton > button,
    div[class*="st-key-fcl_feedback_floater"] button {
        width: 52px !important;
        min-width: 52px !important;
        height: 52px !important;
        font-size: 20px !important;
        touch-action: manipulation;
    }
}
</style>
"""


def page_label(page: str) -> str:
    return PAGE_LABELS.get(page, page.replace("_", " ").title() or "App")


def inject_feedback_css() -> None:
    if st.session_state.get("_feedback_css_injected"):
        return
    st.markdown(FEEDBACK_CSS, unsafe_allow_html=True)
    st.session_state._feedback_css_injected = True


def ensure_feedback_loaded(*, force: bool = False) -> None:
    if force or "feedback_db" not in st.session_state:
        db, meta = load_feedback(force_remote=force)
        st.session_state.feedback_db = db
        st.session_state.feedback_meta = meta
        st.session_state.feedback_sha = meta.get("sha")


def persist_feedback(message: str = "App: product feedback") -> bool:
    db = st.session_state.get("feedback_db") or {"entries": []}
    result = save_feedback(db, sha=st.session_state.get("feedback_sha"), message=message)
    st.session_state.feedback_meta = result
    if result.get("committed") or result.get("source") == "local":
        st.session_state.feedback_sha = result.get("sha")
        return True
    if result.get("conflict"):
        st.warning("Someone else updated feedback — close and try again.")
        return False
    if result.get("saved_locally"):
        st.warning(result.get("error", "Saved locally — GitHub sync unavailable."))
        return True
    if result.get("error"):
        st.error(result.get("error"))
        return False
    st.session_state.feedback_sha = result.get("sha")
    return True


def _close_feedback_dialog() -> None:
    st.session_state.feedback_open = False


def close_feedback_on_view_change() -> None:
    """Close feedback dialog when the user navigates to a different module."""
    current = st.session_state.get("app_view", "agent")
    prev = st.session_state.get("_feedback_tracked_view")
    if prev is not None and prev != current:
        st.session_state.feedback_open = False
    st.session_state._feedback_tracked_view = current


def _open_feedback_dialog(page: str) -> None:
    st.session_state.feedback_open = True
    st.session_state.feedback_page = page


@st.dialog("Share feedback", width="small")
def _feedback_dialog() -> None:
    page = st.session_state.get("feedback_page") or st.session_state.get("app_view", "agent")
    label = page_label(page)
    ensure_feedback_loaded()

    st.markdown(
        f'<div class="fcl-feedback-dialog-kicker">FocusChain Labs</div>'
        f'<div class="fcl-feedback-dialog-title">Help us improve {html.escape(label)}</div>'
        f'<div class="fcl-feedback-page-pill">Screen · {html.escape(label)}</div>'
        f'<div class="fcl-feedback-dialog-sub">'
        f"Tell us what's working, what's broken, or what you'd like next on "
        f"<strong>{html.escape(label)}</strong>. Feedback is saved to the repo so the team "
        f"can prioritise by screen."
        f"</div>",
        unsafe_allow_html=True,
    )
    category = st.selectbox(
        "Type",
        FEEDBACK_CATEGORIES,
        format_func=lambda c: CATEGORY_LABELS.get(c, c.title()),
        key=f"feedback_category_{page}",
    )
    message = st.text_area(
        "Your feedback",
        placeholder=f"e.g. On {label}, it would help if…",
        height=120,
        key=f"feedback_message_{page}",
    )
    submitted_by = st.text_input(
        "Your name (optional)",
        placeholder="Who should we thank?",
        key=f"feedback_name_{page}",
    )
    submit_col, cancel_col = st.columns(2)
    with submit_col:
        if st.button("Send feedback", type="primary", use_container_width=True, key=f"feedback_submit_{page}"):
            text = (message or "").strip()
            if not text:
                st.error("Please add a short message before sending.")
                return
            db = st.session_state.get("feedback_db") or {"entries": []}
            db, outcome = append_feedback(
                db,
                message=text,
                category=category,
                page=page,
                page_label=label,
                submitted_by=(submitted_by or "").strip(),
            )
            if not outcome.get("ok"):
                st.error(outcome.get("error", "Couldn't save feedback."))
                return
            st.session_state.feedback_db = db
            commit_msg = f"Feedback: {label} — {category}"
            if persist_feedback(commit_msg):
                _close_feedback_dialog()
                st.session_state.feedback_toast = f"Thanks — saved for {label}"
                st.rerun()
    with cancel_col:
        if st.button("Cancel", use_container_width=True, key=f"feedback_cancel_{page}"):
            _close_feedback_dialog()
            st.rerun()


def render_feedback_floater(page: str | None = None) -> None:
    """Render the global feedback floater for the active screen."""
    inject_feedback_css()
    close_feedback_on_view_change()
    active_page = page or st.session_state.get("app_view", "agent")
    label = page_label(active_page)

    with st.container(key="fcl_feedback_floater"):
        st.button(
            "💬",
            key="fcl_feedback_open",
            type="primary",
            help=f"Share feedback about {label}",
            on_click=_open_feedback_dialog,
            kwargs={"page": active_page},
        )

    toast = st.session_state.pop("feedback_toast", None)
    if toast:
        st.toast(toast)

    should_open = (
        st.session_state.get("feedback_open")
        and st.session_state.get("feedback_page") == active_page
    )
    if should_open:
        _feedback_dialog()
