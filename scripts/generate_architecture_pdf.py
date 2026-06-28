#!/usr/bin/env python3
"""Generate the multi-tenant SaaS architecture PDF (design + GCP runbook).

    python scripts/generate_architecture_pdf.py
        -> docs/Architecture_Multi_Tenant_SaaS.pdf

Self-contained: text, tables, callouts and diagrams are all drawn with fpdf2
(no external diagram tooling). Uses DejaVu for full Unicode.
"""

from __future__ import annotations

import math
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

ROOT = Path(__file__).resolve().parents[1]
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
OUT = ROOT / "docs" / "Architecture_Multi_Tenant_SaaS.pdf"

# ── Brand palette ─────────────────────────────────────────────────────────────
INK = (15, 42, 51)
INK_SOFT = (60, 81, 88)
MUTE = (107, 127, 133)
GREEN = (46, 139, 77)
GREEN_BR = (55, 168, 92)
GREEN_SOFT = (224, 238, 229)
CREAM = (244, 240, 231)
CREAM3 = (253, 252, 249)
LINE = (208, 203, 192)
CODEBG = (244, 242, 236)
AMBER = (183, 121, 31)
AMBER_SOFT = (247, 238, 222)
RED = (169, 61, 61)
RED_SOFT = (247, 228, 228)
BLUE = (13, 110, 140)
BLUE_SOFT = (221, 236, 242)


class PDF(FPDF):
    def __init__(self) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(18, 18, 18)
        self.add_font("DejaVu", "", str(FONT_DIR / "DejaVuSans.ttf"))
        self.add_font("DejaVu", "B", str(FONT_DIR / "DejaVuSans-Bold.ttf"))
        self.add_font("Mono", "", str(FONT_DIR / "DejaVuSansMono.ttf"))
        self.add_font("Mono", "B", str(FONT_DIR / "DejaVuSansMono-Bold.ttf"))
        self._on_cover = True

    # ── chrome ───────────────────────────────────────────────────────────────
    def header(self) -> None:
        if self._on_cover:
            return
        self.set_font("DejaVu", "", 7.5)
        self.set_text_color(*MUTE)
        self.set_y(8)
        self.cell(0, 4, "FocusChain CRM · Multi-Tenant SaaS Architecture",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
        self.set_draw_color(*LINE)
        self.set_line_width(0.2)
        self.line(18, 14, self.w - 18, 14)
        self.set_y(20)

    def footer(self) -> None:
        if self._on_cover:
            return
        self.set_y(-14)
        self.set_draw_color(*LINE)
        self.line(18, self.h - 16, self.w - 18, self.h - 16)
        self.set_font("DejaVu", "", 7.5)
        self.set_text_color(*MUTE)
        self.cell(0, 5, f"{self.page_no()}", align="C")

    # ── primitives ───────────────────────────────────────────────────────────
    def need(self, h: float) -> None:
        if self.get_y() + h > self.h - 20:
            self.add_page()

    def h1(self, text: str, kicker: str = "") -> None:
        self.add_page()
        self.ln(2)
        if kicker:
            self.set_font("Mono", "B", 8)
            self.set_text_color(*GREEN)
            self.cell(0, 5, kicker.upper(), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(1)
        self.set_font("DejaVu", "B", 21)
        self.set_text_color(*INK)
        self.multi_cell(0, 9, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*GREEN)
        self.set_line_width(0.8)
        y = self.get_y() + 1
        self.line(18, y, 42, y)
        self.ln(6)

    def h2(self, text: str) -> None:
        self.need(20)
        self.ln(3)
        self.set_font("DejaVu", "B", 14)
        self.set_text_color(*INK)
        self.multi_cell(0, 7, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1.5)

    def h3(self, text: str) -> None:
        self.need(14)
        self.ln(1.5)
        self.set_font("DejaVu", "B", 11)
        self.set_text_color(*GREEN)
        self.multi_cell(0, 6, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(0.5)

    def body(self, text: str) -> None:
        self.set_font("DejaVu", "", 10)
        self.set_text_color(*INK_SOFT)
        self.multi_cell(0, 5.4, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1.5)

    def bullet(self, text: str, label: str = "") -> None:
        self.set_font("DejaVu", "", 10)
        self.set_text_color(*GREEN)
        x = self.get_x()
        self.cell(5, 5.2, "•")
        self.set_text_color(*INK_SOFT)
        if label:
            self.set_font("DejaVu", "B", 10)
            self.set_text_color(*INK)
            lbl_w = self.get_string_width(label + "  ")
            self.cell(lbl_w, 5.2, label + " ")
            self.set_font("DejaVu", "", 10)
            self.set_text_color(*INK_SOFT)
        self.multi_cell(0, 5.2, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_x(x)
        self.ln(0.6)

    def step(self, n: int, text: str) -> None:
        self.set_font("Mono", "B", 9)
        self.set_text_color(*GREEN)
        self.cell(7, 5.2, f"{n}.")
        self.set_font("DejaVu", "", 10)
        self.set_text_color(*INK_SOFT)
        self.multi_cell(0, 5.2, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(0.6)

    def code(self, text: str) -> None:
        lines = text.strip("\n").split("\n")
        self.set_font("Mono", "", 8.2)
        line_h = 4.3
        pad = 2.6
        h = len(lines) * line_h + pad * 2
        self.need(h + 2)
        x, y = self.get_x(), self.get_y()
        w = self.epw
        self.set_fill_color(*CODEBG)
        self.set_draw_color(*LINE)
        self.set_line_width(0.2)
        self.rect(x, y, w, h, style="DF")
        self.set_draw_color(*GREEN)
        self.set_line_width(0.7)
        self.line(x, y, x, y + h)
        self.set_xy(x + 3, y + pad)
        self.set_text_color(40, 60, 66)
        for ln in lines:
            self.set_x(x + 4)
            self.cell(w - 6, line_h, ln, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_y(y + h)
        self.ln(2.5)

    def callout(self, title: str, text: str, kind: str = "info") -> None:
        palette = {
            "info": (GREEN, GREEN_SOFT),
            "warn": (AMBER, AMBER_SOFT),
            "danger": (RED, RED_SOFT),
            "note": (BLUE, BLUE_SOFT),
        }[kind]
        border, fill = palette
        self.set_font("DejaVu", "B", 9.5)
        title_h = 5.5
        self.set_font("DejaVu", "", 9.2)
        # measure body height
        text_w = self.epw - 10
        n_lines = self._lines_for(text, 9.2, text_w)
        h = title_h + n_lines * 4.6 + 5
        self.need(h + 2)
        x, y = self.get_x(), self.get_y()
        self.set_fill_color(*fill)
        self.set_draw_color(*border)
        self.set_line_width(0.2)
        self.rect(x, y, self.epw, h, style="DF")
        self.set_line_width(1.0)
        self.line(x, y, x, y + h)
        self.set_xy(x + 5, y + 2.5)
        self.set_font("DejaVu", "B", 9.5)
        self.set_text_color(*border)
        self.cell(0, title_h, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_x(x + 5)
        self.set_font("DejaVu", "", 9.2)
        self.set_text_color(*INK_SOFT)
        self.multi_cell(text_w, 4.6, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_y(y + h)
        self.ln(2.5)

    def _lines_for(self, text: str, size: float, w: float) -> int:
        self.set_font("DejaVu", "", size)
        count = 0
        for para in text.split("\n"):
            words = para.split(" ")
            cur = ""
            for word in words:
                trial = (cur + " " + word).strip()
                if self.get_string_width(trial) > w:
                    count += 1
                    cur = word
                else:
                    cur = trial
            count += 1
        return count

    def table(self, headers: list[str], rows: list[list[str]], widths: list[float]) -> None:
        self.need(10 + len(rows) * 7)
        self.set_font("DejaVu", "B", 8.6)
        self.set_fill_color(*INK)
        self.set_text_color(*CREAM)
        self.set_draw_color(*LINE)
        self.set_line_width(0.2)
        for hd, w in zip(headers, widths):
            self.cell(w, 7, " " + hd, border=0, align="L", fill=True)
        self.ln(7)
        self.set_font("DejaVu", "", 8.6)
        fill = False
        for row in rows:
            # compute row height by tallest cell
            heights = []
            self.set_font("DejaVu", "", 8.6)
            for txt, w in zip(row, widths):
                heights.append(self._lines_for(str(txt), 8.6, w - 3) * 4.2 + 2.4)
            rh = max(heights)
            if self.get_y() + rh > self.h - 20:
                self.add_page()
            x0, y0 = self.get_x(), self.get_y()
            self.set_fill_color(*(CREAM3 if fill else (255, 255, 255)))
            x = x0
            for txt, w in zip(row, widths):
                self.rect(x, y0, w, rh, style="F")
                x += w
            self.set_text_color(*INK_SOFT)
            x = x0
            for i, (txt, w) in enumerate(zip(row, widths)):
                self.set_xy(x + 1.5, y0 + 1.2)
                if i == 0:
                    self.set_font("DejaVu", "B", 8.6)
                    self.set_text_color(*INK)
                else:
                    self.set_font("DejaVu", "", 8.6)
                    self.set_text_color(*INK_SOFT)
                self.multi_cell(w - 3, 4.2, str(txt), new_x=XPos.LMARGIN, new_y=YPos.TOP)
                x += w
            self.set_draw_color(*LINE)
            self.line(x0, y0 + rh, x0 + sum(widths), y0 + rh)
            self.set_y(y0 + rh)
            fill = not fill
        self.ln(3)

    # ── diagram primitives ───────────────────────────────────────────────────
    def dbox(self, x, y, w, h, title, sub="", fill=GREEN_SOFT, border=GREEN, tcol=INK):
        self.set_draw_color(*border)
        self.set_fill_color(*fill)
        self.set_line_width(0.4)
        self.rect(x, y, w, h, style="DF", round_corners=True, corner_radius=1.6)
        self.set_text_color(*tcol)
        self.set_font("DejaVu", "B", 8)
        ty = y + (h / 2 - 4.2 if sub else h / 2 - 2.2)
        self.set_xy(x, ty)
        self.multi_cell(w, 4, title, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if sub:
            self.set_font("Mono", "", 6.4)
            self.set_text_color(*MUTE)
            self.set_xy(x, y + h / 2 + 0.5)
            self.multi_cell(w, 3, sub, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def arrow(self, x1, y1, x2, y2, color=INK_SOFT, label="", dashed=False):
        self.set_draw_color(*color)
        self.set_line_width(0.4)
        if dashed:
            self.set_dash_pattern(dash=1.2, gap=1.2)
        self.line(x1, y1, x2, y2)
        if dashed:
            self.set_dash_pattern()
        ang = math.atan2(y2 - y1, x2 - x1)
        L, sp = 2.6, 0.42
        self.line(x2, y2, x2 - L * math.cos(ang - sp), y2 - L * math.sin(ang - sp))
        self.line(x2, y2, x2 - L * math.cos(ang + sp), y2 - L * math.sin(ang + sp))
        if label:
            self.set_font("Mono", "", 6.2)
            self.set_text_color(*MUTE)
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            self.set_xy(mx - 14, my - 5.4)
            self.cell(28, 3, label, align="C")

    def caption(self, text: str) -> None:
        self.set_font("Mono", "", 7)
        self.set_text_color(*MUTE)
        self.cell(0, 4, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
        self.ln(2)


# ── content ───────────────────────────────────────────────────────────────────
def cover(pdf: PDF) -> None:
    pdf.add_page()
    pdf.set_auto_page_break(False)  # keep the cover to exactly one page
    pdf.set_fill_color(*INK)
    pdf.rect(0, 0, pdf.w, pdf.h, style="F")
    pdf.set_fill_color(*GREEN)
    pdf.rect(0, 95, pdf.w, 1.2, style="F")
    pdf.set_xy(18, 40)
    pdf.set_font("Mono", "B", 10)
    pdf.set_text_color(*GREEN_BR)
    pdf.cell(0, 6, "FOCUSCHAIN LABS  ·  ENGINEERING", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_xy(18, 54)
    pdf.set_font("DejaVu", "B", 30)
    pdf.set_text_color(*CREAM)
    pdf.multi_cell(pdf.w - 36, 12, "Multi-Tenant SaaS\nArchitecture & GCP Runbook",
                   new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_xy(18, 102)
    pdf.set_font("DejaVu", "", 12)
    pdf.set_text_color(208, 214, 210)
    pdf.multi_cell(pdf.w - 36, 6,
                   "How the FocusChain CRM serves FocusChain Labs and SN Realtors "
                   "from one codebase — the design, why it works, and exactly what "
                   "to click and run on Google Cloud to take it live.",
                   new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    # mini legend
    pdf.set_xy(18, 250)
    pdf.set_font("Mono", "", 8.5)
    pdf.set_text_color(150, 165, 165)
    pdf.multi_cell(pdf.w - 36, 5,
                   "Google Sign-In  ·  organization_id isolation  ·  WhatsApp Embedded Signup\n"
                   "Daily AI batch (~Rs 2,000/mo)  ·  Cloud Run  ·  Cloud SQL  ·  CI/CD",
                   new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_y(278)
    pdf.set_font("DejaVu", "", 9)
    pdf.set_text_color(120, 135, 135)
    pdf.cell(0, 5, "Generated for Savin · scripts/generate_architecture_pdf.py",
             align="L")
    pdf._on_cover = False
    pdf.set_auto_page_break(auto=True, margin=18)


def contents(pdf: PDF) -> None:
    pdf.add_page()
    pdf.set_font("DejaVu", "B", 20)
    pdf.set_text_color(*INK)
    pdf.cell(0, 11, "Contents", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)
    items = [
        ("PART I — THE SYSTEM", True),
        ("1  Executive summary", False),
        ("2  Architecture at a glance", False),
        ("3  Why this architecture (key decisions)", False),
        ("PART II — HOW IT WORKS", True),
        ("4  Multi-tenancy: the organization_id model", False),
        ("5  Authentication & tenant resolution", False),
        ("6  WhatsApp: Embedded Signup & inbound routing", False),
        ("7  The AI cost engine: daily batch", False),
        ("8  CI/CD & deployment topology", False),
        ("9  Observability per tenant", False),
        ("PART III — GCP PRODUCTION RUNBOOK", True),
        ("Steps 0–15: click-by-click + every command", False),
        ("APPENDICES", True),
        ("A  Environment variable reference", False),
        ("B  Troubleshooting", False),
    ]
    for label, is_head in items:
        if is_head:
            pdf.ln(2)
            pdf.set_font("Mono", "B", 9)
            pdf.set_text_color(*GREEN)
            pdf.cell(0, 6.5, label, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.set_font("DejaVu", "", 11)
            pdf.set_text_color(*INK_SOFT)
            pdf.cell(0, 6.5, "      " + label, new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def part_divider(pdf: PDF, num: str, title: str, blurb: str) -> None:
    pdf.add_page()
    pdf.ln(60)
    pdf.set_font("Mono", "B", 11)
    pdf.set_text_color(*GREEN)
    pdf.cell(0, 8, num, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("DejaVu", "B", 26)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 12, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_draw_color(*GREEN)
    pdf.set_line_width(0.9)
    yy = pdf.get_y() + 2
    pdf.line(18, yy, 50, yy)
    pdf.ln(8)
    pdf.set_font("DejaVu", "", 11.5)
    pdf.set_text_color(*INK_SOFT)
    pdf.multi_cell(0, 6, blurb, new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def sec_summary(pdf: PDF) -> None:
    pdf.h1("Executive summary", "Part I · 1")
    pdf.body(
        "FocusChain CRM is one application that serves two independent companies — "
        "FocusChain Labs and SN Realtors — from a single codebase and a single set "
        "of cloud resources. Each company (a \"tenant\" or \"organisation\") sees only "
        "its own leads, conversations and WhatsApp numbers, with its own branding, "
        "behind Google Sign-In.")
    pdf.body(
        "The system is built on three ideas that make it cheap, safe and easy to "
        "operate:")
    pdf.bullet(
        "Every row of business data carries an organization_id. One shared database, "
        "partitioned in software — not a separate database per customer. This is the "
        "cheapest model that still guarantees isolation.", label="Shared multi-tenancy.")
    pdf.bullet(
        "A user's tenant is derived from their verified Google email domain at "
        "sign-in — never from anything they can type — and every query is scoped to "
        "it. Unknown domains are refused.", label="Identity = tenant.")
    pdf.bullet(
        "Inbound WhatsApp messages are stored cheaply and enriched by one AI call "
        "per active contact, once a day — keeping the AI bill near Rs 2,000/month "
        "even at 500+ leads per tenant.", label="Batched AI.")
    pdf.body(
        "Everything runs on Google Cloud Run (scale-to-zero containers) with Cloud "
        "SQL (PostgreSQL) for storage, deploys itself from GitHub on every push to "
        "main, and is observable per-tenant through structured logs. Part III is a "
        "literal click-and-command runbook to take it from an empty Google Cloud "
        "project to production.")
    pdf.callout(
        "Who this document is for",
        "You (the operator) — to understand the system deeply and to stand it up on "
        "GCP yourself. No prior Google Cloud experience is assumed in Part III: every "
        "step says where to go in the console and the exact command to run.",
        kind="note")


def diagram_topology(pdf: PDF) -> None:
    pdf.h2("2  Architecture at a glance")
    pdf.body(
        "Two public entry points (the web app and the WhatsApp webhook), one shared "
        "database, and a scheduled job for the daily AI work. Both companies are "
        "served by the same boxes; the organization_id on every row keeps their data "
        "apart.")
    pdf.need(118)
    top = pdf.get_y() + 2
    # external row
    pdf.dbox(20, top, 52, 16, "Users (browsers)", "FocusChain · SN Realtors", fill=CREAM3, border=LINE, tcol=INK)
    pdf.dbox(138, top, 52, 16, "Meta WhatsApp", "Cloud API", fill=CREAM3, border=LINE, tcol=INK)
    # google auth
    pdf.dbox(20, top + 26, 52, 14, "Google OAuth", "st.login (OIDC)", fill=BLUE_SOFT, border=BLUE, tcol=INK)
    # cloud run row
    pdf.dbox(20, top + 50, 52, 18, "Cloud Run: crm-app", "Streamlit · shared", fill=GREEN_SOFT, border=GREEN)
    pdf.dbox(138, top + 50, 52, 18, "Cloud Run: crm-webhook", "FastAPI", fill=GREEN_SOFT, border=GREEN)
    # batch + scheduler
    pdf.dbox(138, top + 80, 52, 14, "Cloud Run Job", "crm-daily-batch", fill=GREEN_SOFT, border=GREEN)
    pdf.dbox(138, top + 100, 52, 12, "Cloud Scheduler", "0 2 * * *", fill=AMBER_SOFT, border=AMBER, tcol=INK)
    pdf.dbox(95, top + 100, 36, 12, "Gemini Flash", "1 call/contact", fill=BLUE_SOFT, border=BLUE, tcol=INK)
    # database (center bottom)
    pdf.dbox(64, top + 50, 60, 18, "Cloud SQL · PostgreSQL", "organization_id on every row", fill=INK, border=INK, tcol=CREAM)

    # arrows
    pdf.arrow(46, top + 16, 46, top + 26)                 # users -> oauth
    pdf.arrow(46, top + 40, 46, top + 50)                 # oauth -> app
    pdf.arrow(164, top + 16, 164, top + 50)               # meta -> webhook
    pdf.arrow(72, top + 59, 64, top + 59)                 # app -> db
    pdf.arrow(138, top + 59, 124, top + 59)               # webhook -> db
    pdf.arrow(164, top + 80, 164, top + 68)               # job -> webhook? no: job->db
    pdf.arrow(164, top + 80, 124, top + 64, dashed=True)  # job -> db
    pdf.arrow(164, top + 100, 164, top + 94)              # scheduler -> job
    pdf.arrow(138, top + 90, 131, top + 106, dashed=True) # job -> gemini
    pdf.set_y(top + 116)
    pdf.caption("Figure 1 — Deployment topology. Solid = request/data path · dashed = the daily batch.")


def sec_decisions(pdf: PDF) -> None:
    pdf.h2("3  Why this architecture (key decisions)")
    pdf.body(
        "Each choice below trades complexity for either cost or safety. The recurring "
        "theme: keep one of everything, and separate tenants in software.")
    pdf.table(
        ["Decision", "What we chose", "Why"],
        [
            ["Tenancy model", "Shared tables + organization_id",
             "One DB and one app for both tenants. A database-per-tenant model "
             "would roughly double cost and ops for two customers; isolation is "
             "still guaranteed by scoping every query."],
            ["Tenant identity", "Google email domain -> org",
             "No passwords to manage; the domain is verified by Google. A user can "
             "never pick another tenant — it is derived server-side."],
            ["Compute", "Cloud Run (scale to zero)",
             "Pay only when used; both services idle to zero. Fits a low monthly "
             "budget and needs no servers to patch."],
            ["WhatsApp onboarding", "Meta Embedded Signup",
             "The official, compliant 'scan a QR' flow. Unofficial libraries risk "
             "the business number being banned and need an always-on server."],
            ["AI processing", "Daily batch, 1 call/contact",
             "An LLM call per message is unaffordable at 500+ leads. Batching to "
             "one call per active contact per day holds the bill near Rs 2,000/mo."],
            ["Deploys", "GitHub Actions -> Cloud Run",
             "Push to main and it ships. No manual deploys; identity via Workload "
             "Identity Federation means no long-lived keys in GitHub."],
        ],
        [30, 42, 108],
    )


def sec_tenancy(pdf: PDF) -> None:
    pdf.h1("Multi-tenancy: the organization_id model", "Part II · 4")
    pdf.body(
        "A tenant is a customer company. The whole system rests on one rule: every "
        "row of business data belongs to exactly one tenant, named by its "
        "organization_id, and no query ever returns rows from another tenant.")
    pdf.h3("The data model")
    pdf.need(70)
    top = pdf.get_y() + 1
    pdf.dbox(72, top, 56, 15, "organizations", "id · name", fill=INK, border=INK, tcol=CREAM)
    pdf.dbox(20, top + 32, 50, 16, "contacts", "organization_id (FK)", fill=GREEN_SOFT, border=GREEN)
    pdf.dbox(78, top + 32, 50, 16, "interactions", "organization_id (FK)", fill=GREEN_SOFT, border=GREEN)
    pdf.dbox(136, top + 32, 54, 16, "whatsapp_accounts", "organization_id (FK)", fill=GREEN_SOFT, border=GREEN)
    pdf.arrow(90, top + 15, 60, top + 32)
    pdf.arrow(103, top + 15, 103, top + 32)
    pdf.arrow(116, top + 15, 150, top + 32)
    pdf.set_y(top + 52)
    pdf.caption("Figure 2 — One row per tenant in organizations; every owned row points back to it.")
    pdf.body(
        "All reads filter by organization_id; all writes stamp it. The Streamlit UI, "
        "the WhatsApp webhook, the mobile REST API and the daily batch all go through "
        "one storage layer (utils/crm_store_postgres.py) that takes organization_id "
        "as an explicit argument — it is never read from a request body or a webhook "
        "payload, both of which an attacker could forge.")
    pdf.h3("Three isolation guarantees")
    pdf.bullet(
        "A globally-unique primary key (a contact id, a phone_number_id) that "
        "collides across tenants cannot be overwritten — the UPDATE carries a "
        "WHERE organization_id = ... guard, so a write to the wrong tenant is a "
        "no-op, not corruption.", label="No cross-tenant overwrite.")
    pdf.bullet(
        "Replacing a tenant's contact list computes its delete-set only within that "
        "tenant, so a save can never delete another tenant's rows.", label="Scoped deletes.")
    pdf.bullet(
        "Inbound WhatsApp traffic is mapped to a tenant by looking up our own "
        "whatsapp_accounts table (phone_number_id -> organization_id), never by "
        "trusting the message payload.", label="Server-side routing.")
    pdf.callout(
        "Fail-closed on the wrong backend",
        "Isolation only holds on Cloud SQL (where rows carry organization_id). If "
        "sign-in is enabled but Cloud SQL isn't configured, the app refuses to load "
        "rather than fall back to a shared file/Supabase store that has no per-tenant "
        "scoping. Better a locked door than a leak.",
        kind="warn")
    pdf.callout(
        "Deferred: PostgreSQL Row-Level Security (RLS)",
        "Today isolation is enforced in the application layer (every query is "
        "scoped). A future hardening pass can add database-enforced RLS policies so "
        "isolation holds even if a query forgets its filter. Documented as a "
        "follow-up, not a blocker for two trusted tenants.",
        kind="note")


def sec_auth(pdf: PDF) -> None:
    pdf.h1("Authentication & tenant resolution", "Part II · 5")
    pdf.body(
        "Sign-in uses Streamlit's native OpenID Connect with Google. The clever part "
        "isn't the login — it's turning a verified identity into a tenant and a data "
        "scope, with no way for the user to influence which tenant they land in.")
    pdf.need(40)
    top = pdf.get_y() + 1
    boxes = [
        (18, "Sign in with Google", "st.login"),
        (62, "Verified email", "user@domain"),
        (106, "Domain -> org", "org_config"),
        (150, "organization_id", "in session"),
    ]
    for x, t, s in boxes:
        pdf.dbox(x, top, 40, 16, t, s, fill=GREEN_SOFT, border=GREEN)
    pdf.arrow(58, top + 8, 62, top + 8)
    pdf.arrow(102, top + 8, 106, top + 8)
    pdf.arrow(146, top + 8, 150, top + 8)
    pdf.set_y(top + 22)
    pdf.caption("Figure 3 — From Google identity to a scoped tenant in four steps.")
    pdf.h3("How the domain maps to a tenant")
    pdf.body(
        "utils/org_config.py is the registry of tenants: each has an id, display "
        "name, branding and a list of email domains. resolve_org_for_email() matches "
        "the verified domain to a tenant; an unmapped domain returns None and the "
        "user is shown an access-denied screen. The mapping is overridable in "
        "production via the ORG_CONFIG or ORG_EMAIL_DOMAINS secrets, so you can add a "
        "domain without a code change.")
    pdf.code(
        'ORG_EMAIL_DOMAINS = \'{"focuschainlabs.com":"focuschainlabs",\n'
        '                      "snrealtors.in":"sn_realtors"}\'')
    pdf.h3("Branding follows the tenant")
    pdf.body(
        "Once the tenant is known, the same UI renders that tenant's name, tagline "
        "and accent — FocusChain Labs or SN Realtors — so each company sees \"their\" "
        "app. The manual org-switcher that exists for local development is hidden "
        "under real auth, so a signed-in user cannot switch tenants by hand.")
    pdf.callout(
        "Local development needs no Google client",
        "If the [auth] secrets aren't present, the app runs unauthenticated in "
        "single-tenant 'dev mode' (set DEV_ORG_ID to pick which tenant to preview). "
        "Production turns auth on simply by adding the [auth] section.",
        kind="note")


def sec_whatsapp(pdf: PDF) -> None:
    pdf.h1("WhatsApp: Embedded Signup & inbound routing", "Part II · 6")
    pdf.body(
        "Each tenant connects its own WhatsApp number(s) from inside the CRM using "
        "Meta's official Embedded Signup — the compliant 'scan a QR in Meta's popup' "
        "flow. The hard problem is binding that connection to the right tenant "
        "without trusting the browser.")
    pdf.h3("The connect flow (and its security)")
    pdf.need(46)
    top = pdf.get_y() + 1
    pdf.dbox(18, top, 40, 16, "CRM app", "mints signed state", fill=GREEN_SOFT, border=GREEN)
    pdf.dbox(64, top, 40, 16, "Meta popup", "business scans QR", fill=CREAM3, border=LINE, tcol=INK)
    pdf.dbox(110, top, 40, 16, "/connect/whatsapp", "verify state", fill=GREEN_SOFT, border=GREEN)
    pdf.dbox(156, top, 36, 16, "whatsapp_accounts", "under org", fill=INK, border=INK, tcol=CREAM)
    pdf.arrow(58, top + 8, 64, top + 8, label="state")
    pdf.arrow(104, top + 8, 110, top + 8, label="code")
    pdf.arrow(150, top + 8, 156, top + 8, label="token")
    pdf.set_y(top + 22)
    pdf.caption("Figure 4 — The signed state carries the tenant end-to-end; the browser can't forge it.")
    pdf.body(
        "The app (which knows the signed-in tenant) mints a short-lived HMAC-signed "
        "token that encodes the organization_id. The browser passes it through Meta's "
        "popup to the webhook's /connect/whatsapp endpoint, which verifies the "
        "signature, exchanges Meta's authorization code for a business token, asks "
        "Meta for the authoritative phone number, and stores it under that tenant. "
        "Because the tenant comes from the signed token (not a browser field), one "
        "tenant can never attach a number to another.")
    pdf.h3("Inbound messages route themselves")
    pdf.body(
        "When a customer messages a connected number, Meta calls the webhook with the "
        "receiving phone_number_id. The webhook looks that up in whatsapp_accounts to "
        "find the organization_id, then finds-or-creates the lead and stores the "
        "message — all under the right tenant, with no payload trust. Retried "
        "deliveries are de-duplicated by Meta's message id.")


def sec_ai(pdf: PDF) -> None:
    pdf.h1("The AI cost engine: daily batch", "Part II · 7")
    pdf.body(
        "Reading and updating a CRM record from free-text messages needs an LLM. "
        "Doing that per message, in the webhook, is the obvious design — and it's "
        "unaffordable at 500+ leads per tenant. The fix is to separate cheap storage "
        "from expensive understanding.")
    pdf.need(52)
    top = pdf.get_y() + 1
    pdf.dbox(18, top, 44, 16, "Inbound message", "webhook stores", fill=GREEN_SOFT, border=GREEN)
    pdf.dbox(72, top, 46, 16, "interactions", "processed_at = NULL", fill=INK, border=INK, tcol=CREAM)
    pdf.dbox(72, top + 26, 46, 15, "Daily job", "group by contact", fill=GREEN_SOFT, border=GREEN)
    pdf.dbox(132, top + 26, 40, 15, "1 LLM call", "per contact", fill=BLUE_SOFT, border=BLUE, tcol=INK)
    pdf.dbox(132, top, 40, 16, "CRM updated", "+ stamped", fill=GREEN_SOFT, border=GREEN)
    pdf.arrow(62, top + 8, 72, top + 8, label="cheap")
    pdf.arrow(95, top + 16, 95, top + 26)
    pdf.arrow(118, top + 33, 132, top + 33, label="once/day")
    pdf.arrow(152, top + 26, 152, top + 16, label="merge")
    pdf.set_y(top + 46)
    pdf.caption("Figure 5 — Store cheaply now; understand in one batched call per active contact, later.")
    pdf.body(
        "INBOUND_LLM_MODE=batch tells the webhook to store messages without an LLM "
        "call (processed_at stays NULL). Once a day, a Cloud Run Job groups the "
        "pending messages by contact and makes a single Gemini Flash call per active "
        "contact, merges the result into the record (filling only empty fields and "
        "accumulating notes, so it never clobbers what a human typed), and stamps "
        "the messages processed. A per-tenant cap (DAILY_LLM_BUDGET) bounds spend; "
        "anything over the cap simply waits for tomorrow. Stamping makes re-runs "
        "idempotent and cheap.")
    pdf.h3("Why it fits ~Rs 2,000/month/tenant")
    pdf.table(
        ["Item", "Estimate"],
        [
            ["Model", "Gemini 2.5 Flash"],
            ["Tokens per call", "~1.5k in + ~0.3k out"],
            ["Cost per call", "~ Rs 0.10 – 0.12"],
            ["Daily cap (DAILY_LLM_BUDGET)", "500 calls / tenant / day"],
            ["Worst case", "500 x 30 x Rs 0.11  =  ~ Rs 1,650 / month / tenant"],
            ["Realistic", "far fewer contacts active per day -> well under the cap"],
        ],
        [70, 110],
    )


def sec_cicd(pdf: PDF) -> None:
    pdf.h1("CI/CD & deployment topology", "Part II · 8")
    pdf.body(
        "Pushing to the main branch on GitHub builds and deploys the affected service "
        "to Cloud Run automatically. There are no long-lived cloud keys stored in "
        "GitHub: Workload Identity Federation lets the GitHub Action prove its "
        "identity to Google and assume a deploy service account just for that run.")
    pdf.bullet(
        ".github/workflows/deploy-app.yml builds Dockerfile.streamlit and deploys the "
        "crm-app service.", label="App.")
    pdf.bullet(
        ".github/workflows/deploy-webhook.yml builds the root Dockerfile, deploys "
        "crm-webhook, and updates the crm-daily-batch job image in lock-step.",
        label="Webhook + job.")
    pdf.bullet(
        "Every deploy attaches labels (app, component, env, tenant-model) so "
        "resources and billing are filterable.", label="Labels.")
    pdf.callout(
        "One image, two runtimes",
        "The webhook image also contains scripts/, so the daily batch job reuses the "
        "exact same image — it just overrides the command. One build, always in sync.",
        kind="note")


def sec_obs(pdf: PDF) -> None:
    pdf.h1("Observability per tenant", "Part II · 9")
    pdf.body(
        "In a shared deployment there is no per-tenant Cloud Run service to look at, "
        "so per-tenant visibility comes from the logs. The app, webhook and batch "
        "emit single-line JSON (utils/obs.py) that Cloud Logging parses into "
        "structured fields — including organization_id.")
    pdf.code(
        'jsonPayload.event="inbound_message"\n'
        'jsonPayload.organization_id="focuschainlabs"')
    pdf.body(
        "From those logs you build log-based metrics with an organization_id label: "
        "inbound volume per tenant, and daily LLM calls per tenant (your cost "
        "watchdog against the budget). One dashboard then breaks every chart out by "
        "tenant. Resource labels drive the billing breakdown (Billing -> Reports -> "
        "group by label). Full queries are in docs/OBSERVABILITY.md.")


# ── Part III: GCP runbook ──────────────────────────────────────────────────────
def runbook(pdf: PDF) -> None:
    part_divider(
        pdf, "PART III", "GCP Production Runbook",
        "From an empty Google Cloud project to a live, auto-deploying, two-tenant "
        "system. Each step says where to go in the console and the exact command. "
        "Commands assume the gcloud CLI; you can do most of it in the console UI too. "
        "Set these once and reuse them:")
    pdf.code(
        'export PROJECT_ID=focuschain-crm           # your GCP project id\n'
        'export REGION=asia-south1                  # Mumbai\n'
        'export REPO=focuschain                     # Artifact Registry repo\n'
        'gcloud config set project "$PROJECT_ID"')

    def stepblock(n, title, where, lines, code=None, callout=None):
        pdf.h2(f"Step {n} — {title}")
        if where:
            pdf.set_font("Mono", "", 7.6)
            pdf.set_text_color(*GREEN)
            pdf.multi_cell(0, 4.4, "CONSOLE:  " + where, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
        for ln in lines:
            pdf.step(ln[0], ln[1]) if isinstance(ln, tuple) else pdf.body(ln)
        if code:
            pdf.code(code)
        if callout:
            pdf.callout(callout[0], callout[1], callout[2] if len(callout) > 2 else "note")

    stepblock(
        0, "Prerequisites", "console.cloud.google.com",
        ["You need: a Google account with billing, the GitHub repo, and a phone "
         "with the WhatsApp Business app. Install the gcloud CLI locally (or use "
         "Cloud Shell — the >_ icon, top-right of the console — which has gcloud "
         "pre-installed)."],
        code='gcloud auth login\ngcloud components update')

    stepblock(
        1, "Create the project & enable billing",
        "Console -> top project dropdown -> New Project; then Billing -> Link a billing account",
        [(1, "Create a project (note its Project ID, e.g. focuschain-crm)."),
         (2, "Billing -> link a billing account to it."),
         (3, "Set it as your active project with the command below.")],
        code='gcloud projects create "$PROJECT_ID"   # or pick an existing one\n'
             'gcloud config set project "$PROJECT_ID"')

    stepblock(
        2, "Enable the APIs", "APIs & Services -> Enable APIs and Services",
        ["Turn on every API the system uses in one command."],
        code='gcloud services enable \\\n'
             '  run.googleapis.com sqladmin.googleapis.com \\\n'
             '  artifactregistry.googleapis.com cloudbuild.googleapis.com \\\n'
             '  cloudscheduler.googleapis.com secretmanager.googleapis.com \\\n'
             '  iamcredentials.googleapis.com logging.googleapis.com')

    stepblock(
        3, "Create the Artifact Registry repo",
        "Artifact Registry -> Create Repository (Format: Docker, Region: asia-south1)",
        ["This is where your container images live. The workflows push to repo "
         "name 'focuschain'."],
        code='gcloud artifacts repositories create "$REPO" \\\n'
             '  --repository-format=docker --location="$REGION" \\\n'
             '  --description="FocusChain CRM images"')

    stepblock(
        4, "Provision Cloud SQL (PostgreSQL)",
        "SQL -> Create Instance -> PostgreSQL",
        [(1, "Create a small Postgres 15 instance (db-g1-small is fine to start)."),
         (2, "Create a database named focuschain and a user focuschain_user."),
         (3, "Note the INSTANCE CONNECTION NAME (looks like project:region:instance) "
             "— Cloud Run uses it."),
         (4, "Apply the schema (run the file in db/schema_cloudsql.sql).")],
        code='gcloud sql instances create focuschain-db \\\n'
             '  --database-version=POSTGRES_15 --tier=db-g1-small --region="$REGION"\n'
             'gcloud sql databases create focuschain --instance=focuschain-db\n'
             'gcloud sql users create focuschain_user --instance=focuschain-db --password=\'CHOOSE_A_STRONG_PW\'\n'
             '# apply schema (Cloud SQL Studio in the console, or via the proxy):\n'
             'psql "$DATABASE_URL" -f db/schema_cloudsql.sql',
        callout=("Connection name", "Save it: export "
                 "CLOUD_SQL_CONNECTION_NAME=\"$PROJECT_ID:$REGION:focuschain-db\". "
                 "This is what links Cloud Run to the database.", "note"))

    stepblock(
        5, "Store secrets", "Security -> Secret Manager -> Create Secret",
        ["Create one secret per sensitive value (DB password, API keys, OAuth "
         "client secret, Meta app secret, WA_CONNECT_SECRET). You'll reference them "
         "from Cloud Run with --set-secrets. Generate the shared connect secret:"],
        code='python -c "import secrets; print(secrets.token_hex(32))"   # WA_CONNECT_SECRET\n'
             'printf \'%s\' "YOUR_DB_PASSWORD" | gcloud secrets create DB_PASSWORD --data-file=-')

    stepblock(
        6, "Create the Google OAuth client (for sign-in)",
        "APIs & Services -> Credentials -> Create Credentials -> OAuth client ID -> Web application",
        [(1, "Configure the OAuth consent screen (Internal if both companies use "
             "Google Workspace you control; otherwise External)."),
         (2, "Create a Web application client."),
         (3, "Add an Authorized redirect URI: https://YOUR-APP-URL/oauth2callback "
             "(you'll get the real URL after Step 9 — come back and add it)."),
         (4, "Copy the Client ID and Client Secret into the app's [auth] secrets.")],
        callout=("The [auth] block", "In the app's Streamlit secrets set: "
                 "redirect_uri, a random cookie_secret, and [auth.google] "
                 "client_id / client_secret / server_metadata_url. Template is in "
                 ".streamlit/secrets.example.toml.", "note"))

    stepblock(
        7, "Set up the Meta app (WhatsApp Embedded Signup)",
        "developers.facebook.com -> My Apps -> Create App (Business) -> add WhatsApp",
        [(1, "Create a Business app; add the WhatsApp product."),
         (2, "Set up Embedded Signup (Configurations) and note the Configuration ID."),
         (3, "From App settings copy App ID and App Secret."),
         (4, "Point the WhatsApp webhook to https://YOUR-WEBHOOK-URL/webhook with your "
             "WHATSAPP_VERIFY_TOKEN; subscribe to the messages field.")],
        callout=("Maps to env vars", "META_APP_ID, META_APP_SECRET, META_CONFIG_ID, "
                 "WA_CONNECT_SECRET, WEBHOOK_PUBLIC_URL, APP_PUBLIC_URL. See "
                 ".streamlit/secrets.example.toml.", "note"))

    stepblock(
        8, "First deploy: the webhook (manual, once)",
        "Cloud Run -> the service appears after this command",
        ["Build, push and deploy the webhook image once by hand so the service "
         "exists (CI takes over afterwards). Wire in Cloud SQL and its secrets."],
        code='IMG="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/webhook:bootstrap"\n'
             'gcloud builds submit --tag "$IMG" .\n'
             'gcloud run deploy crm-webhook --image "$IMG" --region "$REGION" \\\n'
             '  --allow-unauthenticated \\\n'
             '  --add-cloudsql-instances "$CLOUD_SQL_CONNECTION_NAME" \\\n'
             '  --set-env-vars INBOUND_LLM_MODE=batch,CLOUD_SQL_CONNECTION_NAME="$CLOUD_SQL_CONNECTION_NAME" \\\n'
             '  --set-secrets DB_PASSWORD=DB_PASSWORD:latest,WHATSAPP_ACCESS_TOKEN=WA_TOKEN:latest')

    stepblock(
        9, "First deploy: the app (manual, once)",
        "Cloud Run -> crm-app",
        ["Same idea for the Streamlit app. Its URL is what you put in the Google "
         "OAuth redirect URI (Step 6) and in APP_PUBLIC_URL / WEBHOOK_PUBLIC_URL."],
        code='IMG="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/app:bootstrap"\n'
             'gcloud builds submit --tag "$IMG" -f Dockerfile.streamlit .\n'
             'gcloud run deploy crm-app --image "$IMG" --region "$REGION" \\\n'
             '  --allow-unauthenticated \\\n'
             '  --add-cloudsql-instances "$CLOUD_SQL_CONNECTION_NAME" \\\n'
             '  --set-env-vars CLOUD_SQL_CONNECTION_NAME="$CLOUD_SQL_CONNECTION_NAME"',
        callout=("Now finish Step 6", "Copy the crm-app URL, add /oauth2callback to "
                 "the Google OAuth redirect URIs, and set redirect_uri to match. "
                 "Sign-in won't work until these line up exactly.", "warn"))

    stepblock(
        10, "Turn on auto-deploy (Workload Identity Federation)",
        "IAM & Admin -> Workload Identity Federation -> Create Pool",
        [(1, "Create a Workload Identity Pool + an OIDC provider for GitHub "
             "(issuer https://token.actions.githubusercontent.com)."),
         (2, "Create a deploy service account; grant it run.admin, "
             "iam.serviceAccountUser, artifactregistry.writer, cloudbuild.builds.editor."),
         (3, "Allow your GitHub repo to impersonate it (attribute on repository)."),
         (4, "Add four GitHub repo secrets so the workflows can authenticate.")],
        code='# GitHub -> repo -> Settings -> Secrets and variables -> Actions:\n'
             'GCP_PROJECT_ID=...        GCP_SERVICE_ACCOUNT=deployer@PROJECT.iam.gserviceaccount.com\n'
             'GCP_WORKLOAD_IDENTITY_PROVIDER=projects/NUM/locations/global/workloadIdentityPools/POOL/providers/PROVIDER',
        callout=("After this", "Every push to main runs the workflows in "
                 ".github/workflows and deploys automatically — no keys stored.", "info"))

    stepblock(
        11, "Schedule the daily AI batch", "Cloud Run -> Jobs -> Create Job; then Cloud Scheduler",
        [(1, "Create the crm-daily-batch job from the webhook image, overriding the "
             "command. Give it Cloud SQL + the same env."),
         (2, "Create a Scheduler trigger to run it once a day."),
         (3, "Confirm the webhook has INBOUND_LLM_MODE=batch so messages defer to "
             "this job.")],
        code='gcloud run jobs create crm-daily-batch --image "$IMG_WEBHOOK" --region "$REGION" \\\n'
             '  --command python --args scripts/process_inbound_daily.py,--all \\\n'
             '  --add-cloudsql-instances "$CLOUD_SQL_CONNECTION_NAME" \\\n'
             '  --set-env-vars INBOUND_LLM_MODE=batch,DAILY_LLM_BUDGET=500\n'
             'gcloud scheduler jobs create http crm-daily-batch-trigger \\\n'
             '  --schedule "0 2 * * *" --location "$REGION" \\\n'
             '  --uri "https://$REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT_ID/jobs/crm-daily-batch:run" \\\n'
             '  --http-method POST --oauth-service-account-email "$RUN_INVOKER_SA"')

    stepblock(
        12, "Labels, metrics & a per-tenant dashboard",
        "Logging -> Log-based Metrics; Monitoring -> Dashboards",
        [(1, "Deploys already label resources; filter the Cloud Run list with "
             "labels.app:focuschain-crm."),
         (2, "Create a log-based counter on jsonPayload.event=\"inbound_message\" with "
             "a label organization_id."),
         (3, "Create a distribution metric on jsonPayload.event=\"daily_batch\" value "
             "jsonPayload.llm_calls, label organization_id — your cost watchdog."),
         (4, "Build a dashboard grouped by organization_id. Full queries: "
             "docs/OBSERVABILITY.md.")])

    stepblock(
        13, "Custom domain (optional)", "Cloud Run -> Manage Custom Domains",
        ["Map a domain (e.g. app.focuschainlabs.com) to crm-app, update the DNS "
         "records it shows you, then update the Google OAuth redirect URI and "
         "APP_PUBLIC_URL to the new domain."])

    stepblock(
        14, "Assign existing data to a tenant", "Cloud SQL Studio (or psql)",
        ["Leads created before multi-tenancy carry organization_id='default' and are "
         "invisible to the new tenants. Assign them once."],
        code="UPDATE contacts     SET organization_id='focuschainlabs' WHERE organization_id='default';\n"
             "UPDATE interactions SET organization_id='focuschainlabs' WHERE organization_id='default';")

    pdf.h2("Step 15 — Go-live checklist")
    for item in [
        "Cloud SQL schema applied (db/schema_cloudsql.sql); existing data assigned.",
        "crm-app and crm-webhook deploy green from GitHub on push to main.",
        "Google sign-in works; a focuschainlabs user sees FocusChain branding, an "
        "sn_realtors user sees SN Realtors — and neither sees the other's leads.",
        "A test WhatsApp message to a connected number lands on the right tenant.",
        "crm-daily-batch runs on schedule; daily_batch logs show calls under the cap.",
        "Per-tenant metrics visible; a budget alert is set.",
    ]:
        pdf.set_font("DejaVu", "B", 10)
        pdf.set_text_color(*GREEN)
        pdf.cell(6, 5.4, "✓")
        pdf.set_font("DejaVu", "", 10)
        pdf.set_text_color(*INK_SOFT)
        pdf.multi_cell(0, 5.4, item, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(0.6)


def appendix(pdf: PDF) -> None:
    pdf.h1("Appendix A — Environment variables", "Reference")
    pdf.table(
        ["Variable", "Where", "Purpose"],
        [
            ["CLOUD_SQL_CONNECTION_NAME", "app, webhook, job", "Links Cloud Run to Cloud SQL (project:region:instance)."],
            ["DATABASE_URL", "local dev", "Postgres URL when not on Cloud Run."],
            ["[auth] + auth.google", "app", "Google OIDC sign-in (redirect_uri, cookie_secret, client id/secret)."],
            ["ORG_CONFIG / ORG_EMAIL_DOMAINS", "app", "Tenant registry & email-domain -> org mapping."],
            ["API_KEYS", "webhook", "Bearer token -> org for the mobile REST API."],
            ["META_APP_ID / META_APP_SECRET", "app / webhook", "Meta app for Embedded Signup + token exchange."],
            ["META_CONFIG_ID", "app", "Embedded Signup configuration id."],
            ["WA_CONNECT_SECRET", "app + webhook", "Shared HMAC secret binding a connect to a tenant."],
            ["WEBHOOK_PUBLIC_URL / APP_PUBLIC_URL", "app / webhook", "Public URLs (popup target + CORS allow-list)."],
            ["INBOUND_LLM_MODE", "webhook", "'batch' defers per-message LLM to the daily job."],
            ["DAILY_LLM_BUDGET", "job", "Max LLM calls per tenant per run (default 500)."],
        ],
        [54, 34, 92],
    )
    pdf.h1("Appendix B — Troubleshooting", "Reference")
    tb = [
        ("\"Almost there\" config screen after login",
         "Auth is on but Cloud SQL isn't reachable. Check CLOUD_SQL_CONNECTION_NAME "
         "and that the service has --add-cloudsql-instances."),
        ("Sign-in loops or 'redirect_uri mismatch'",
         "The Google OAuth redirect URI must exactly equal redirect_uri in secrets, "
         "including https and /oauth2callback."),
        ("A tenant's CRM is empty",
         "Likely the pre-existing data is still under organization_id='default' — run "
         "the Step 14 assignment."),
        ("WhatsApp messages don't appear",
         "Confirm the number is in whatsapp_accounts under that tenant, the webhook "
         "URL/verify token match Meta, and the messages field is subscribed."),
        ("Daily batch did nothing",
         "It only processes unprocessed inbound rows. If the webhook is in realtime "
         "mode, messages are stamped processed on arrival; set INBOUND_LLM_MODE=batch."),
        ("AI bill creeping up",
         "Watch the daily_batch llm_calls metric; lower DAILY_LLM_BUDGET or confirm "
         "batch mode is on."),
    ]
    for q, a in tb:
        pdf.h3(q)
        pdf.body(a)


def build() -> None:
    pdf = PDF()
    cover(pdf)
    contents(pdf)
    part_divider(pdf, "PART I", "The System",
                 "What the system is, the shape of it, and the decisions that make "
                 "it cheap and safe.")
    sec_summary(pdf)
    pdf.add_page()
    diagram_topology(pdf)
    sec_decisions(pdf)
    part_divider(pdf, "PART II", "How It Works",
                 "The mechanisms — tenancy, identity, WhatsApp, AI cost, delivery and "
                 "observability — and why each is built the way it is.")
    sec_tenancy(pdf)
    sec_auth(pdf)
    sec_whatsapp(pdf)
    sec_ai(pdf)
    sec_cicd(pdf)
    sec_obs(pdf)
    runbook(pdf)
    appendix(pdf)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUT))
    print(f"✓ wrote {OUT}  ({OUT.stat().st_size // 1024} KB, {pdf.page_no()} pages)")


if __name__ == "__main__":
    build()
