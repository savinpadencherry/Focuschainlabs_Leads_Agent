"""Back-compat shim — the engine lives in utils.llm ("FocusChain LLM").

Older imports (`from utils.gemini import generate_content_text/generate_json`)
keep working, but every call now flows through the engine-agnostic layer:
DeepSeek primary when DEEPSEEK_API_KEY is set, Gemini Flash fallback. New code
should import from utils.llm directly.
"""

from __future__ import annotations

from utils.llm import generate_content_text, generate_json  # noqa: F401
