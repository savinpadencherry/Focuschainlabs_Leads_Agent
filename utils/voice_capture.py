"""Browser-native dictation — zero AI, zero quota, zero cost.

Speech-to-text doesn't need an LLM: every modern browser ships its own
speech-recognition engine (the Web Speech API). This wraps it as a tiny
static Streamlit component — the browser converts speech to text locally
and hands back plain words. No audio is recorded, uploaded, or sent to
Gemini; the AI only sees the (editable) text the user ends up with.

Falls back gracefully — the widget disables itself with a clear message on
browsers that don't support the API (e.g. Firefox); typing always works.
"""

from __future__ import annotations

from pathlib import Path

import streamlit.components.v1 as components

_COMPONENT_DIR = Path(__file__).resolve().parent.parent / "components" / "voice_to_text"
_component = components.declare_component("voice_to_text", path=str(_COMPONENT_DIR))


def voice_to_text(*, key: str | None = None) -> str:
    """Render the dictation widget. Returns the latest captured transcript ('' if none yet)."""
    return _component(key=key, default="") or ""
