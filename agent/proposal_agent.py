"""
Proposal Agent — AI-drafted B2B service proposals.

generate_proposal()   → structured JSON from Gemini
build_html()          → polished self-contained HTML (print to PDF in browser)
send_proposal_email() → sends HTML proposal via Gmail SMTP
"""

from __future__ import annotations

import html as _html
import json
import os
import re
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from utils.gemini import generate_content_text


# ── Gemini prompt ─────────────────────────────────────────────────────────────

_PROPOSAL_PROMPT = """\
You are a senior B2B sales consultant writing a service proposal on behalf of \
{sender_company}.

CLIENT:
  Company:       {company}
  Contact:       {contact_name}, {contact_title}
  Industry:      {industry}
  Pain / Notes:  {notes}
  Intel signals: {signals_text}

ENGAGEMENT:
  Service:        {service_type}
  Deliverables:   {deliverables_text}
  Investment:     {price} {currency}
  Payment terms:  {payment_terms}
  Duration:       {duration}
  Proposed start: {start_date}

Write a complete, compelling proposal. Be specific to their situation — \
reference real pain points and signals. No buzzwords. Professional but human tone.

Return ONLY valid JSON (no markdown fences, no explanation):
{{
  "title": "Proposal title specific to the client and service",
  "executive_summary": "2-3 paragraph executive summary",
  "situation_analysis": "2-3 paragraphs: their current situation, specific challenges, what the signals indicate about where they are now",
  "our_approach": "2-3 paragraphs: methodology, how we work, what differentiates our approach",
  "scope": ["Deliverable or workstream 1", "Deliverable 2", "..."],
  "investment": {{
    "summary": "One paragraph framing the investment",
    "line_items": [
      {{"item": "Service name", "description": "What it includes", "amount": "Price"}}
    ],
    "total": "{price} {currency}",
    "terms": "{payment_terms}"
  }},
  "milestones": [
    {{"period": "Week 1", "milestone": "What happens"}},
    {{"period": "Week 2–3", "milestone": "What happens"}}
  ],
  "why_us": ["Reason 1", "Reason 2", "Reason 3"],
  "next_steps": ["Step 1", "Step 2", "Step 3"],
  "validity_note": "This proposal is valid for 30 days from the date of issue."
}}
"""


def generate_proposal(contact: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """
    Call Gemini to generate a structured proposal. Returns the parsed JSON dict.
    Raises on Gemini error so the UI can surface it.
    """
    # Pull Intel signals if available
    signals_text = _get_signals_text(contact)

    deliverables_text = "\n".join(
        f"- {d}" for d in (config.get("deliverables") or []) if d.strip()
    ) or config.get("deliverables_text", "")

    prompt = _PROPOSAL_PROMPT.format(
        company           = (contact.get("company") or "the client").strip(),
        contact_name      = (contact.get("name") or "Decision Maker").strip(),
        contact_title     = (contact.get("title") or "").strip(),
        industry          = (contact.get("industry") or "").strip(),
        notes             = (contact.get("notes") or "").strip(),
        signals_text      = signals_text,
        sender_company    = (config.get("sender_company") or "FocusChain Labs").strip(),
        service_type      = (config.get("service_type") or "B2B AI automation service").strip(),
        deliverables_text = deliverables_text or "As discussed",
        price             = str(config.get("price") or ""),
        currency          = (config.get("currency") or "INR").strip(),
        payment_terms     = (config.get("payment_terms") or "50% upfront, 50% on delivery").strip(),
        duration          = (config.get("duration") or "4–6 weeks").strip(),
        start_date        = (config.get("start_date") or "Upon agreement").strip(),
    )

    raw = generate_content_text(prompt)
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    raw = re.sub(r"\s*```\s*$", "", raw.strip(), flags=re.MULTILINE)
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        return _parse_fallback(raw)


def _get_signals_text(contact: dict) -> str:
    """Pull latest Intel briefing for this contact if stored locally."""
    try:
        from utils.intel_store import load_briefings
        company = (contact.get("company") or "").lower()
        cid     = contact.get("id", "")
        briefs  = load_briefings()
        match   = next(
            (b for b in sorted(briefs, key=lambda x: x.get("ran_at", ""), reverse=True)
             if (b.get("company") or "").lower() == company or b.get("contact_id") == cid),
            None,
        )
        if not match:
            return contact.get("signal") or ""
        lines = [match.get("summary") or ""]
        for s in (match.get("signals") or [])[:4]:
            lines.append(f"- [{s.get('type','').upper()}] {s.get('headline','')}")
        return "\n".join(l for l in lines if l)
    except Exception:
        return contact.get("signal") or ""


def _parse_fallback(raw: str) -> dict:
    result: dict[str, Any] = {}
    for key in ("title", "executive_summary", "situation_analysis",
                "our_approach", "validity_note"):
        m = re.search(rf'"{key}"\s*:\s*"((?:[^"\\]|\\.)*)"', raw, re.DOTALL)
        if m:
            result[key] = m.group(1).replace("\\n", "\n").replace('\\"', '"')
    return result


# ── HTML builder ──────────────────────────────────────────────────────────────

def build_html(
    proposal: dict[str, Any],
    config: dict[str, Any],
    contact: dict[str, Any],
) -> str:
    """Render a polished, self-contained HTML proposal (print-to-PDF ready)."""

    def e(v: Any) -> str:
        return _html.escape(str(v or ""))

    company       = e(contact.get("company") or "Client")
    contact_name  = e(contact.get("name") or "")
    sender_name   = e(config.get("sender_name") or "")
    sender_title  = e(config.get("sender_title") or "")
    sender_company= e(config.get("sender_company") or "FocusChain Labs")
    date_str      = datetime.now().strftime("%B %d, %Y")
    service_type  = e(config.get("service_type") or "")

    # Cover initials
    initials = "".join(w[0].upper() for w in (config.get("sender_company") or "FCL").split()[:3])

    # ── Sections ─────────────────────────────────────────────────────────────

    def paragraphs(text: str) -> str:
        return "".join(f"<p>{e(p.strip())}</p>" for p in str(text or "").split("\n\n") if p.strip())

    def bullet_list(items: list, ordered: bool = False) -> str:
        tag = "ol" if ordered else "ul"
        rows = "".join(f"<li>{e(item)}</li>" for item in (items or []) if item)
        return f"<{tag}>{rows}</{tag}>" if rows else ""

    # Scope
    scope_html = bullet_list(proposal.get("scope") or [])

    # Investment
    inv      = proposal.get("investment") or {}
    li_rows  = "".join(
        f"<tr><td>{e(li.get('item',''))}</td>"
        f"<td>{e(li.get('description',''))}</td>"
        f"<td class='amt'>{e(li.get('amount',''))}</td></tr>"
        for li in (inv.get("line_items") or [])
    )
    total    = e(inv.get("total") or f"{config.get('price','')} {config.get('currency','')}".strip())
    terms    = e(inv.get("terms") or config.get("payment_terms") or "")
    inv_summary_html = paragraphs(inv.get("summary") or "")

    inv_table = (
        f"<table class='price-table'>"
        f"<thead><tr><th>Item</th><th>Description</th><th>Amount</th></tr></thead>"
        f"<tbody>{li_rows}"
        f"<tr class='total-row'><td colspan='2'>Total Investment</td><td class='amt'>{total}</td></tr>"
        f"</tbody></table>"
    ) if li_rows else f"<p class='total-solo'>{total}</p>"

    # Timeline
    ms_html = "".join(
        f"<div class='ms-row'>"
        f"<div class='ms-period'>{e(m.get('period',''))}</div>"
        f"<div class='ms-text'>{e(m.get('milestone',''))}</div>"
        f"</div>"
        for m in (proposal.get("milestones") or [])
    )

    # Why us / next steps
    why_html  = bullet_list(proposal.get("why_us") or [])
    next_html = bullet_list(proposal.get("next_steps") or [], ordered=True)

    validity  = e(proposal.get("validity_note") or "This proposal is valid for 30 days.")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Proposal for {company} — {sender_company}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Space+Grotesk:wght@600;700;800&display=swap');

:root {{
  --ink:    #0F2A33;
  --soft:   #3C5158;
  --mute:   #6B7F85;
  --green:  #2E8B4D;
  --green2: #1a6b3c;
  --cream:  #FDFCF9;
  --line:   rgba(15,42,51,.12);
  --pad:    64px;
}}

* {{ margin:0; padding:0; box-sizing:border-box; }}

@page {{ size:A4; margin:0; }}

body {{
  font-family: 'Inter', -apple-system, 'Helvetica Neue', sans-serif;
  color: var(--ink);
  background: white;
  font-size: 14px;
  line-height: 1.7;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}}

/* ── Cover ── */
.cover {{
  min-height: 100vh;
  background: var(--ink);
  color: white;
  display: flex;
  flex-direction: column;
  padding: var(--pad);
  page-break-after: always;
  position: relative;
  overflow: hidden;
}}
.cover::before {{
  content: '';
  position: absolute;
  top: -80px; right: -80px;
  width: 400px; height: 400px;
  background: radial-gradient(circle, rgba(46,139,77,.25) 0%, transparent 70%);
  border-radius: 50%;
  pointer-events: none;
}}
.cover::after {{
  content: '';
  position: absolute;
  bottom: -60px; left: 40px;
  width: 280px; height: 280px;
  background: radial-gradient(circle, rgba(46,139,77,.12) 0%, transparent 70%);
  border-radius: 50%;
  pointer-events: none;
}}
.cover-brand {{
  display: flex;
  align-items: center;
  gap: 14px;
  position: relative; z-index: 1;
}}
.brand-mark {{
  width: 44px; height: 44px;
  background: var(--green);
  border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  font-family: 'Space Grotesk', sans-serif;
  font-size: 15px; font-weight: 800;
  letter-spacing: -.02em;
  color: white;
}}
.brand-name {{
  font-size: 13px; font-weight: 600;
  letter-spacing: .06em; text-transform: uppercase;
  color: rgba(255,255,255,.55);
}}

.cover-mid {{
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  position: relative; z-index: 1;
  padding: 60px 0 40px;
}}
.cover-label {{
  font-size: 11px; font-weight: 700;
  letter-spacing: .25em; text-transform: uppercase;
  color: var(--green);
  margin-bottom: 20px;
}}
.cover-title {{
  font-family: 'Space Grotesk', sans-serif;
  font-size: 48px; font-weight: 800;
  line-height: 1.05;
  letter-spacing: -.02em;
  color: white;
  margin-bottom: 8px;
  max-width: 540px;
}}
.cover-for {{
  font-size: 18px; font-weight: 300;
  color: rgba(255,255,255,.5);
  margin-bottom: 32px;
}}
.cover-divider {{
  width: 48px; height: 3px;
  background: var(--green);
  border-radius: 2px;
  margin-bottom: 24px;
}}
.cover-meta {{
  display: flex; gap: 32px;
  font-size: 13px;
  color: rgba(255,255,255,.45);
}}
.cover-meta strong {{ color: rgba(255,255,255,.75); font-weight: 500; }}

.cover-footer {{
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  position: relative; z-index: 1;
  border-top: 1px solid rgba(255,255,255,.1);
  padding-top: 24px;
}}
.cover-prep {{
  font-size: 12px;
  color: rgba(255,255,255,.4);
  line-height: 1.6;
}}
.cover-prep strong {{ color: rgba(255,255,255,.7); }}
.confidential {{
  font-size: 10px; font-weight: 700;
  letter-spacing: .2em; text-transform: uppercase;
  color: rgba(255,255,255,.25);
  border: 1px solid rgba(255,255,255,.15);
  padding: 4px 10px; border-radius: 3px;
}}

/* ── Content pages ── */
.content {{
  padding: var(--pad);
  max-width: 800px;
  margin: 0 auto;
}}

section {{
  margin-bottom: 52px;
  page-break-inside: avoid;
}}

.sec-row {{
  display: flex;
  align-items: flex-start;
  gap: 20px;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 2px solid var(--ink);
}}
.sec-num {{
  font-family: 'Space Grotesk', sans-serif;
  font-size: 11px; font-weight: 700;
  letter-spacing: .18em; text-transform: uppercase;
  color: var(--mute);
  padding-top: 5px;
  white-space: nowrap;
}}
.sec-title {{
  font-family: 'Space Grotesk', sans-serif;
  font-size: 22px; font-weight: 700;
  letter-spacing: -.01em;
  color: var(--ink);
}}

p {{
  color: var(--soft);
  margin-bottom: 14px;
  font-weight: 300;
}}
p:last-child {{ margin-bottom: 0; }}

ul, ol {{
  padding-left: 22px;
  color: var(--soft);
  font-weight: 300;
}}
li {{ margin-bottom: 8px; line-height: 1.6; }}
li::marker {{ color: var(--green); font-weight: 600; }}

/* ── Pricing table ── */
.price-table {{
  width: 100%;
  border-collapse: collapse;
  margin: 20px 0;
  font-size: 13.5px;
}}
.price-table thead th {{
  font-size: 10px; font-weight: 700;
  letter-spacing: .12em; text-transform: uppercase;
  color: var(--mute);
  padding: 10px 12px;
  text-align: left;
  border-bottom: 2px solid var(--ink);
}}
.price-table tbody td {{
  padding: 12px 12px;
  border-bottom: 1px solid var(--line);
  vertical-align: top;
  color: var(--soft);
}}
.price-table tbody tr:last-child td {{ border-bottom: none; }}
.price-table .total-row td {{
  font-weight: 600;
  color: var(--ink);
  border-top: 2px solid var(--ink);
  padding-top: 14px;
}}
.price-table .amt {{ text-align: right; font-weight: 600; color: var(--ink); white-space: nowrap; }}
.total-solo {{
  font-size: 22px; font-weight: 700;
  color: var(--ink);
  margin-top: 12px;
}}
.terms-note {{
  font-size: 12.5px;
  color: var(--mute);
  margin-top: 10px;
  padding: 10px 14px;
  background: rgba(15,42,51,.04);
  border-left: 3px solid var(--green);
  border-radius: 0 4px 4px 0;
}}

/* ── Timeline ── */
.ms-row {{
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 16px;
  padding: 14px 0;
  border-bottom: 1px solid var(--line);
  align-items: start;
}}
.ms-row:last-child {{ border-bottom: none; }}
.ms-period {{
  font-family: 'Space Grotesk', sans-serif;
  font-size: 11px; font-weight: 700;
  letter-spacing: .08em; text-transform: uppercase;
  color: var(--green);
  padding-top: 2px;
}}
.ms-text {{ color: var(--soft); font-weight: 300; }}

/* ── Validity / Footer ── */
.validity-box {{
  margin-top: 40px;
  padding: 16px 20px;
  background: rgba(46,139,77,.06);
  border: 1px solid rgba(46,139,77,.2);
  border-radius: 6px;
  font-size: 12.5px;
  color: var(--mute);
}}

.doc-footer {{
  margin-top: 60px;
  padding-top: 20px;
  border-top: 1px solid var(--line);
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--mute);
  font-family: 'Inter', monospace;
}}

/* ── Print rules ── */
@media print {{
  .cover {{ page-break-after: always; min-height: 100vh; }}
  section {{ page-break-inside: avoid; }}
  .doc-footer {{ position: fixed; bottom: 30px; left: 64px; right: 64px; }}
}}
</style>
</head>
<body>

<!-- COVER PAGE -->
<div class="cover">
  <div class="cover-brand">
    <div class="brand-mark">{initials}</div>
    <div class="brand-name">{sender_company}</div>
  </div>

  <div class="cover-mid">
    <div class="cover-label">Service Proposal</div>
    <div class="cover-title">{e(proposal.get("title") or f"Proposal for {company}")}</div>
    <div class="cover-for">Prepared for {company}</div>
    <div class="cover-divider"></div>
    <div class="cover-meta">
      {"<span>To: <strong>" + contact_name + "</strong></span>" if contact_name else ""}
      <span>Date: <strong>{date_str}</strong></span>
      {"<span>Service: <strong>" + service_type + "</strong></span>" if service_type else ""}
    </div>
  </div>

  <div class="cover-footer">
    <div class="cover-prep">
      Prepared by <strong>{sender_name}</strong>
      {"<br>" + sender_title if sender_title else ""}
      {"<br>" + sender_company}
    </div>
    <div class="confidential">Confidential</div>
  </div>
</div>

<!-- CONTENT PAGES -->
<div class="content">

  <section>
    <div class="sec-row">
      <div class="sec-num">01</div>
      <div class="sec-title">Executive Summary</div>
    </div>
    {paragraphs(proposal.get("executive_summary") or "")}
  </section>

  <section>
    <div class="sec-row">
      <div class="sec-num">02</div>
      <div class="sec-title">Your Situation</div>
    </div>
    {paragraphs(proposal.get("situation_analysis") or "")}
  </section>

  <section>
    <div class="sec-row">
      <div class="sec-num">03</div>
      <div class="sec-title">Our Approach</div>
    </div>
    {paragraphs(proposal.get("our_approach") or "")}
  </section>

  <section>
    <div class="sec-row">
      <div class="sec-num">04</div>
      <div class="sec-title">Scope of Work</div>
    </div>
    {scope_html or "<p>Scope to be finalised with client.</p>"}
  </section>

  <section>
    <div class="sec-row">
      <div class="sec-num">05</div>
      <div class="sec-title">Investment</div>
    </div>
    {inv_summary_html}
    {inv_table}
    {"<div class='terms-note'>" + terms + "</div>" if terms else ""}
  </section>

  <section>
    <div class="sec-row">
      <div class="sec-num">06</div>
      <div class="sec-title">Timeline &amp; Milestones</div>
    </div>
    <div class="timeline">{ms_html or "<p>Timeline to be confirmed at kickoff.</p>"}</div>
  </section>

  <section>
    <div class="sec-row">
      <div class="sec-num">07</div>
      <div class="sec-title">Why {sender_company}</div>
    </div>
    {why_html}
  </section>

  <section>
    <div class="sec-row">
      <div class="sec-num">08</div>
      <div class="sec-title">Next Steps</div>
    </div>
    {next_html}
    <div class="validity-box">{validity}</div>
  </section>

  <div class="doc-footer">
    <span>{sender_company} · {sender_name}</span>
    <span>Confidential · {date_str}</span>
  </div>

</div>
</body>
</html>"""


# ── Email sending ─────────────────────────────────────────────────────────────

def send_proposal_email(
    to_email: str,
    subject: str,
    intro_body: str,
    proposal_html: str,
    *,
    from_email: str = "",
    app_password: str = "",
) -> dict[str, Any]:
    """
    Send proposal as an HTML email. The proposal HTML is appended below the
    intro text so the recipient sees it inline (no attachment needed).
    """
    from_email   = (from_email   or os.getenv("SMTP_FROM_EMAIL",   "")).strip()
    app_password = (app_password or os.getenv("SMTP_APP_PASSWORD", "")).strip()

    if not from_email or not app_password:
        return {"ok": False, "error": "SMTP_FROM_EMAIL + SMTP_APP_PASSWORD not configured in secrets."}
    if not to_email or "@" not in to_email:
        return {"ok": False, "error": "Invalid recipient email address."}

    # Combine intro text + proposal HTML
    full_html = (
        f"<div style='font-family:sans-serif;font-size:14px;line-height:1.6;"
        f"color:#0F2A33;max-width:700px;'>"
        f"<p>{_html.escape(intro_body).replace(chr(10), '<br>')}</p>"
        f"</div><hr style='border:none;border-top:1px solid #e0e0e0;margin:24px 0;'>"
        + proposal_html
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = from_email
    msg["To"]      = to_email
    msg.attach(MIMEText(full_html, "html", "utf-8"))

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls(context=ctx)
            server.login(from_email, app_password)
            server.sendmail(from_email, to_email, msg.as_string())
        return {"ok": True}
    except smtplib.SMTPAuthenticationError:
        return {"ok": False, "error": "Gmail auth failed — check SMTP_APP_PASSWORD is an App Password."}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
