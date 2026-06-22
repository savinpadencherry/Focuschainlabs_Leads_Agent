#!/usr/bin/env python3
"""Generate PDF from WHATSAPP_COEXISTENCE_BROADCAST_GUIDE.md"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MD_PATH = ROOT / "docs" / "WHATSAPP_COEXISTENCE_BROADCAST_GUIDE.md"
OUT_PATH = ROOT / "docs" / "WhatsApp_Coexistence_Broadcast_Guide.pdf"


def _strip_md(text: str) -> str:
    text = re.sub(r"```[\s\S]*?```", "[code block — see markdown source]", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    return text


def build_pdf(md_text: str, out: Path) -> None:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    w = pdf.epw  # effective page width

    pdf.set_font("Helvetica", "B", 18)
    pdf.multi_cell(w, 10, "WhatsApp Coexistence & Broadcast Guide")
    pdf.set_font("Helvetica", size=11)
    pdf.ln(4)
    pdf.multi_cell(w, 6, "FocusChain Labs - Leads Agent CRM\nJune 2026")
    pdf.ln(8)

    body = _strip_md(md_text)
    pdf.set_font("Helvetica", size=9)

    for line in body.splitlines():
        line = line.rstrip()
        if not line:
            pdf.ln(3)
            continue
        if line.startswith("---"):
            pdf.ln(2)
            continue
        # ASCII-only for Helvetica
        safe = line.encode("ascii", "replace").decode("ascii")
        if len(safe) > 200:
            safe = safe[:200] + "..."
        if line.startswith("|") and "|" in line[1:]:
            pdf.set_font("Courier", size=7)
            pdf.multi_cell(w, 4, safe)
            pdf.set_font("Helvetica", size=9)
            continue
        if re.match(r"^Part [A-F]|^Appendix", safe):
            pdf.ln(4)
            pdf.set_font("Helvetica", "B", 11)
            pdf.multi_cell(w, 6, safe[:100])
            pdf.set_font("Helvetica", size=9)
            continue
        if safe.startswith(("+", "-", ">", "`")) and safe[:3] in {"> +", "> -", "> `"}:
            continue
        pdf.multi_cell(w, 5, safe)

    out.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out))
    print(f"Wrote {out}")


def main() -> None:
    try:
        import fpdf  # noqa: F401
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "fpdf2", "-q"])
    if not MD_PATH.exists():
        print(f"Missing {MD_PATH}", file=sys.stderr)
        sys.exit(1)
    md = MD_PATH.read_text(encoding="utf-8")
    build_pdf(md, OUT_PATH)


if __name__ == "__main__":
    main()
