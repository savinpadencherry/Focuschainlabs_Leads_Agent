"""
Finance Agent — invoicing, payment tracking & dunning.

Closes the revenue loop after the Proposal Agent: a won deal becomes an invoice,
the invoice gets sent and tracked, and overdue invoices trigger AI-composed
dunning (payment-reminder) sequences.

Design notes
------------
• Invoice generation is fully deterministic — NO LLM call, so creating an
  invoice costs nothing. Totals are computed from line items + tax rate.
• Only dunning emails use Gemini (one call each) — the AI value-add is the
  escalating, human-sounding reminder tone.
• Reuses the proposal/reach infrastructure: HTML→PDF rendering aesthetic and
  Gmail SMTP sending.
• Invoices are stored on the CRM contact (GitHub-backed) — persistent financial
  records, not an ephemeral local cache.

Public API
----------
  next_invoice_number(existing)      → "INV-2026-007"
  build_invoice(contact, config)     → normalized invoice dict (no API call)
  build_invoice_html(inv, cfg, c)    → self-contained print-ready HTML
  compose_dunning_email(...)         → {subject, body} via Gemini
  send_invoice_email(...)            → Gmail SMTP send
"""

from __future__ import annotations

import html as _html
import os
import re
import smtplib
import ssl
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from utils import budget
from utils.crm_models import (
    normalize_invoice,
    to_amount,
    utc_now_iso,
)
from utils.llm import generate_content_text


# Currency symbols for display
_CURRENCY_SYMBOL = {
    "INR": "₹",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "AED": "AED ",
}


def currency_symbol(code: str) -> str:
    return _CURRENCY_SYMBOL.get((code or "INR").upper(), (code or "").upper() + " ")


def fmt_money(amount: Any, currency: str = "INR") -> str:
    """Format a number as currency. Uses Indian grouping for INR, else western."""
    value = to_amount(amount)
    sym = currency_symbol(currency)
    if (currency or "INR").upper() == "INR":
        return f"{sym}{_indian_group(value)}"
    return f"{sym}{value:,.2f}"


def _indian_group(value: float) -> str:
    """Format 150000.0 → '1,50,000.00' (Indian lakh/crore grouping)."""
    neg = value < 0
    value = abs(value)
    whole = int(value)
    frac = round(value - whole, 2)
    s = str(whole)
    if len(s) > 3:
        last3 = s[-3:]
        rest = s[:-3]
        rest = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", rest)
        grouped = f"{rest},{last3}"
    else:
        grouped = s
    frac_str = f"{frac:.2f}"[2:]
    out = f"{grouped}.{frac_str}"
    return f"-{out}" if neg else out


# ── Invoice numbering ───────────────────────────────────────────────────────────

def next_invoice_number(existing_numbers: list[str], *, prefix: str = "", year: int = 0) -> str:
    """
    Generate the next sequential invoice number: PREFIX-YEAR-NNN.
    Scans existing numbers for the highest sequence in the current year.
    """
    prefix = (prefix or os.getenv("INVOICE_PREFIX", "INV")).strip().upper()
    year = year or datetime.now().year
    head = f"{prefix}-{year}-"
    highest = 0
    for num in existing_numbers or []:
        if not num:
            continue
        m = re.match(rf"{re.escape(prefix)}-{year}-(\d+)$", str(num).strip().upper())
        if m:
            highest = max(highest, int(m.group(1)))
    return f"{head}{highest + 1:03d}"


# ── Invoice builder (deterministic — no API call) ───────────────────────────────

def build_invoice(contact: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """
    Build a normalized invoice from a CRM contact + config form. Pure function,
    no network/LLM call — creating an invoice is free.
    """
    issue = config.get("issue_date") or date.today().isoformat()
    net_days = int(config.get("net_days") or 14)
    due = config.get("due_date")
    if not due:
        try:
            due = (datetime.fromisoformat(issue).date() + timedelta(days=net_days)).isoformat()
        except ValueError:
            due = (date.today() + timedelta(days=net_days)).isoformat()

    return normalize_invoice({
        "number":     config.get("number", ""),
        "contact_id": contact.get("id", ""),
        "company":    contact.get("company") or contact.get("name") or "",
        "currency":   config.get("currency", "INR"),
        "issue_date": issue,
        "due_date":   due,
        "line_items": config.get("line_items") or [],
        "tax_rate":   config.get("tax_rate", 0),
        "notes":      config.get("notes", ""),
        "status":     config.get("status", "draft"),
    })


def line_items_from_proposal(contact: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Best-effort: build draft line items from the most recent proposal logged in
    the CRM thread (so a won deal pre-fills its invoice). Falls back to empty.
    """
    items: list[dict[str, Any]] = []
    value = to_amount(contact.get("value"))
    if value > 0:
        items.append({"item": "Agreed engagement", "qty": 1, "rate": value})
    return items


# ── HTML invoice (print-to-PDF ready) ───────────────────────────────────────────

def build_invoice_html(
    invoice: dict[str, Any],
    config: dict[str, Any],
    contact: dict[str, Any],
) -> str:
    """Render a polished, self-contained HTML invoice matching the proposal aesthetic."""

    def e(v: Any) -> str:
        return _html.escape(str(v or ""))

    currency       = invoice.get("currency", "INR")
    company        = e(contact.get("company") or contact.get("name") or "Client")
    contact_name   = e(contact.get("name") or "")
    contact_email  = e(contact.get("email") or "")
    sender_name    = e(config.get("sender_name") or os.getenv("SENDER_NAME", ""))
    sender_company = e(config.get("sender_company") or os.getenv("SENDER_COMPANY", "FocusChain Labs"))
    sender_email   = e(config.get("sender_email") or os.getenv("SMTP_FROM_EMAIL", ""))
    pay_to         = e(config.get("payment_instructions") or os.getenv("PAYMENT_INSTRUCTIONS", ""))
    initials = "".join(w[0].upper() for w in (config.get("sender_company") or os.getenv("SENDER_COMPANY", "FCL")).split()[:3]) or "FCL"

    number     = e(invoice.get("number") or "—")
    issue_date = _pretty_date(invoice.get("issue_date"))
    due_date   = _pretty_date(invoice.get("due_date"))
    notes      = e(invoice.get("notes") or "")

    # Line item rows
    rows = ""
    for li in invoice.get("line_items") or []:
        rows += (
            f"<tr>"
            f"<td><div class='li-item'>{e(li.get('item',''))}</div>"
            + (f"<div class='li-desc'>{e(li.get('description',''))}</div>" if li.get('description') else "")
            + f"</td>"
            f"<td class='num'>{_qty_str(li.get('qty'))}</td>"
            f"<td class='num'>{e(fmt_money(li.get('rate'), currency))}</td>"
            f"<td class='num'>{e(fmt_money(li.get('amount'), currency))}</td>"
            f"</tr>"
        )

    subtotal = e(fmt_money(invoice.get("subtotal"), currency))
    tax_rate = invoice.get("tax_rate") or 0
    tax_amt  = e(fmt_money(invoice.get("tax_amount"), currency))
    total    = e(fmt_money(invoice.get("total"), currency))

    tax_row = (
        f"<tr><td class='sum-l'>Tax ({_qty_str(tax_rate)}%)</td>"
        f"<td class='sum-v'>{tax_amt}</td></tr>"
        if to_amount(tax_rate) > 0 else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Invoice {number} — {sender_company}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Space+Grotesk:wght@600;700;800&display=swap');

:root {{
  --ink:    #0F2A33;
  --soft:   #3C5158;
  --mute:   #6B7F85;
  --green:  #2E8B4D;
  --cream:  #FDFCF9;
  --line:   rgba(15,42,51,.12);
  --pad:    56px;
}}

* {{ margin:0; padding:0; box-sizing:border-box; }}
@page {{ size:A4; margin:0; }}

body {{
  font-family: 'Inter', -apple-system, 'Helvetica Neue', sans-serif;
  color: var(--ink);
  background: white;
  font-size: 14px;
  line-height: 1.6;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}}

.sheet {{ max-width: 820px; margin: 0 auto; padding: var(--pad); }}

/* ── Header ── */
.inv-head {{
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding-bottom: 28px;
  border-bottom: 3px solid var(--ink);
  margin-bottom: 32px;
}}
.brand {{ display: flex; align-items: center; gap: 13px; }}
.brand-mark {{
  width: 46px; height: 46px;
  background: var(--ink);
  border-radius: 9px;
  display: flex; align-items: center; justify-content: center;
  font-family: 'Space Grotesk', sans-serif;
  font-size: 16px; font-weight: 800; color: white;
}}
.brand-name {{ font-family: 'Space Grotesk', sans-serif; font-size: 17px; font-weight: 700; }}
.brand-sub  {{ font-size: 11px; color: var(--mute); margin-top: 2px; }}
.inv-title-block {{ text-align: right; }}
.inv-title {{
  font-family: 'Space Grotesk', sans-serif;
  font-size: 34px; font-weight: 800;
  letter-spacing: .04em; color: var(--ink);
  line-height: 1;
}}
.inv-number {{
  font-family: 'Space Grotesk', sans-serif;
  font-size: 13px; font-weight: 600;
  color: var(--green); margin-top: 6px;
}}

/* ── Meta row (bill-to + dates) ── */
.meta-grid {{
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 32px;
  margin-bottom: 36px;
}}
.meta-label {{
  font-size: 10px; font-weight: 700;
  letter-spacing: .16em; text-transform: uppercase;
  color: var(--mute); margin-bottom: 8px;
}}
.bill-name {{ font-size: 16px; font-weight: 600; color: var(--ink); margin-bottom: 2px; }}
.bill-line {{ font-size: 13px; color: var(--soft); }}
.dates {{ display: flex; flex-direction: column; gap: 12px; }}
.date-row {{ display: flex; justify-content: space-between; align-items: baseline; }}
.date-k {{ font-size: 12px; color: var(--mute); }}
.date-v {{
  font-family: 'Space Grotesk', sans-serif;
  font-size: 13px; font-weight: 600; color: var(--ink);
}}
.date-v.due {{ color: var(--green); }}

/* ── Items table ── */
.items {{ width: 100%; border-collapse: collapse; margin-bottom: 0; }}
.items thead th {{
  font-size: 10px; font-weight: 700;
  letter-spacing: .12em; text-transform: uppercase;
  color: var(--mute);
  padding: 10px 12px;
  border-bottom: 2px solid var(--ink);
  text-align: left;
}}
.items thead th.num {{ text-align: right; }}
.items tbody td {{
  padding: 14px 12px;
  border-bottom: 1px solid var(--line);
  vertical-align: top;
  color: var(--soft);
}}
.items tbody td.num {{ text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }}
.li-item {{ font-size: 14px; font-weight: 500; color: var(--ink); }}
.li-desc {{ font-size: 12px; color: var(--mute); margin-top: 3px; font-weight: 300; }}

/* ── Summary ── */
.summary {{ display: flex; justify-content: flex-end; margin-top: 22px; }}
.sum-table {{ width: 300px; }}
.sum-table tr td {{ padding: 7px 12px; }}
.sum-l {{ color: var(--mute); font-size: 13px; }}
.sum-v {{ text-align: right; font-weight: 600; color: var(--ink); font-variant-numeric: tabular-nums; }}
.sum-total td {{
  border-top: 2px solid var(--ink);
  padding-top: 13px !important;
  font-family: 'Space Grotesk', sans-serif;
}}
.sum-total .sum-l {{ font-size: 14px; font-weight: 700; color: var(--ink); letter-spacing: .02em; }}
.sum-total .sum-v {{ font-size: 21px; font-weight: 800; color: var(--green); }}

/* ── Footer ── */
.pay-box {{
  margin-top: 40px;
  padding: 18px 20px;
  background: rgba(46,139,77,.06);
  border: 1px solid rgba(46,139,77,.22);
  border-radius: 8px;
}}
.pay-box .meta-label {{ color: var(--green); }}
.pay-box .pay-body {{ font-size: 13px; color: var(--soft); line-height: 1.7; white-space: pre-line; }}
.notes-box {{ margin-top: 22px; font-size: 12.5px; color: var(--mute); line-height: 1.65; }}
.inv-footer {{
  margin-top: 48px;
  padding-top: 18px;
  border-top: 1px solid var(--line);
  display: flex;
  justify-content: space-between;
  font-size: 11px; color: var(--mute);
}}

@media print {{
  .sheet {{ padding: 40px; }}
}}
</style>
</head>
<body>
<div class="sheet">

  <div class="inv-head">
    <div class="brand">
      <div class="brand-mark">{initials}</div>
      <div>
        <div class="brand-name">{sender_company}</div>
        {"<div class='brand-sub'>" + sender_email + "</div>" if sender_email else ""}
      </div>
    </div>
    <div class="inv-title-block">
      <div class="inv-title">INVOICE</div>
      <div class="inv-number">{number}</div>
    </div>
  </div>

  <div class="meta-grid">
    <div>
      <div class="meta-label">Bill To</div>
      <div class="bill-name">{company}</div>
      {"<div class='bill-line'>" + contact_name + "</div>" if contact_name else ""}
      {"<div class='bill-line'>" + contact_email + "</div>" if contact_email else ""}
    </div>
    <div class="dates">
      <div class="date-row"><span class="date-k">Issue date</span><span class="date-v">{issue_date}</span></div>
      <div class="date-row"><span class="date-k">Due date</span><span class="date-v due">{due_date}</span></div>
    </div>
  </div>

  <table class="items">
    <thead>
      <tr>
        <th>Description</th>
        <th class="num">Qty</th>
        <th class="num">Rate</th>
        <th class="num">Amount</th>
      </tr>
    </thead>
    <tbody>
      {rows or "<tr><td colspan='4' style='text-align:center;color:#6B7F85;padding:24px;'>No line items</td></tr>"}
    </tbody>
  </table>

  <div class="summary">
    <table class="sum-table">
      <tr><td class="sum-l">Subtotal</td><td class="sum-v">{subtotal}</td></tr>
      {tax_row}
      <tr class="sum-total"><td class="sum-l">Total Due</td><td class="sum-v">{total}</td></tr>
    </table>
  </div>

  {"<div class='pay-box'><div class='meta-label'>Payment Instructions</div><div class='pay-body'>" + pay_to + "</div></div>" if pay_to else ""}
  {"<div class='notes-box'>" + notes + "</div>" if notes else ""}

  <div class="inv-footer">
    <span>{sender_company}{(" · " + sender_name) if sender_name else ""}</span>
    <span>Invoice {number} · {issue_date}</span>
  </div>

</div>
</body>
</html>"""


def _pretty_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(str(iso)[:10]).strftime("%b %d, %Y")
    except (ValueError, TypeError):
        return str(iso or "—")


def _qty_str(v: Any) -> str:
    n = to_amount(v)
    return str(int(n)) if n == int(n) else f"{n:g}"


# ── Dunning (AI payment reminders) ──────────────────────────────────────────────

_DUNNING_PROMPT = """\
You are {sender_name} from {sender_company}, writing a payment reminder to a \
client about an unpaid invoice. Write in first person, like a real person — \
warm, professional, never robotic or threatening.

INVOICE:
  Number:       {number}
  Amount due:   {amount}
  Issue date:   {issue_date}
  Due date:     {due_date}
  Days overdue: {days_overdue}
  Client:       {company} ({contact_name})

REMINDER LEVEL: {level_desc}

Tone guidance for this level:
{tone}

Rules:
• 3-4 sentences maximum. No bullet points.
• Reference the specific invoice number and amount.
• Make it easy to resolve — offer to help if there's an issue.
• No legal threats unless level 3, and even then stay courteous.
• No jargon, no "kindly", no "please find attached".

Return ONLY valid JSON (no markdown fences):
{{"subject": "...", "body": "..."}}
"""

_DUNNING_LEVELS = {
    1: (
        "Gentle first nudge",
        "Friendly and assuming-good-intent. They probably just forgot. "
        "Light, no pressure at all.",
    ),
    2: (
        "Firmer second reminder",
        "Still warm but clearer that payment is now overdue. Politely direct. "
        "Ask if there's a blocker you can help with.",
    ),
    3: (
        "Final courteous notice",
        "Professional and serious, but never hostile. Make clear this is the final "
        "reminder before next steps, while keeping the relationship intact.",
    ),
}


def dunning_level_for(days_overdue: int) -> int:
    """Pick an escalation level from how overdue the invoice is."""
    if days_overdue <= 7:
        return 1
    if days_overdue <= 21:
        return 2
    return 3


def compose_dunning_email(
    invoice: dict[str, Any],
    contact: dict[str, Any],
    *,
    level: int = 0,
    sender_name: str = "",
    sender_company: str = "",
) -> dict[str, str]:
    """
    Generate an escalating payment-reminder email via Gemini.
    Returns {subject, body}. Raises on Gemini error so the UI can surface it.
    """
    budget.reset()

    due = (invoice.get("due_date") or "")[:10]
    days_overdue = 0
    if due:
        try:
            days_overdue = (date.today() - datetime.fromisoformat(due).date()).days
        except ValueError:
            days_overdue = 0
    level = level or dunning_level_for(max(days_overdue, 0))
    level = max(1, min(3, level))
    level_desc, tone = _DUNNING_LEVELS[level]

    currency = invoice.get("currency", "INR")
    prompt = _DUNNING_PROMPT.format(
        sender_name    = (sender_name or os.getenv("SENDER_NAME", "the team")).strip(),
        sender_company = (sender_company or os.getenv("SENDER_COMPANY", "FocusChain Labs")).strip(),
        number         = invoice.get("number", ""),
        amount         = fmt_money(invoice.get("total"), currency),
        issue_date     = _pretty_date(invoice.get("issue_date")),
        due_date       = _pretty_date(invoice.get("due_date")),
        days_overdue   = max(days_overdue, 0),
        company        = contact.get("company") or contact.get("name") or "the client",
        contact_name   = contact.get("name") or "there",
        level_desc     = level_desc,
        tone           = tone,
    )

    import json as _json
    raw = generate_content_text(prompt)
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    raw = re.sub(r"\s*```\s*$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        data = _json.loads(raw)
    except _json.JSONDecodeError:
        data = {}
        for key in ("subject", "body"):
            m = re.search(rf'"{key}"\s*:\s*"((?:[^"\\]|\\.)*)"', raw, re.DOTALL)
            if m:
                data[key] = m.group(1).replace("\\n", "\n").replace('\\"', '"')

    subject = str(data.get("subject") or f"Reminder: Invoice {invoice.get('number','')} now due")
    body = str(data.get("body") or "").strip()
    return {"subject": subject, "body": body, "level": str(level)}


# ── Email sending ───────────────────────────────────────────────────────────────

def smtp_configured() -> bool:
    return bool(os.getenv("SMTP_FROM_EMAIL") and os.getenv("SMTP_APP_PASSWORD"))


def send_invoice_email(
    to_email: str,
    subject: str,
    intro_body: str,
    invoice_html: str,
    *,
    from_email: str = "",
    app_password: str = "",
) -> dict[str, Any]:
    """Send the invoice as an inline HTML email (intro text above the invoice)."""
    from_email   = (from_email   or os.getenv("SMTP_FROM_EMAIL",   "")).strip()
    app_password = (app_password or os.getenv("SMTP_APP_PASSWORD", "")).strip()

    if not from_email or not app_password:
        return {"ok": False, "error": "SMTP_FROM_EMAIL + SMTP_APP_PASSWORD not configured in secrets."}
    if not to_email or "@" not in to_email:
        return {"ok": False, "error": "Invalid recipient email address."}

    full_html = (
        f"<div style='font-family:sans-serif;font-size:14px;line-height:1.6;"
        f"color:#0F2A33;max-width:700px;'>"
        f"<p>{_html.escape(intro_body).replace(chr(10), '<br>')}</p>"
        f"</div><hr style='border:none;border-top:1px solid #e0e0e0;margin:24px 0;'>"
        + invoice_html
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


def send_plain_email(
    to_email: str,
    subject: str,
    body: str,
    *,
    from_email: str = "",
    app_password: str = "",
) -> dict[str, Any]:
    """Send a plain-text email (used for dunning reminders)."""
    from_email   = (from_email   or os.getenv("SMTP_FROM_EMAIL",   "")).strip()
    app_password = (app_password or os.getenv("SMTP_APP_PASSWORD", "")).strip()

    if not from_email or not app_password:
        return {"ok": False, "error": "SMTP not configured."}
    if not to_email or "@" not in to_email:
        return {"ok": False, "error": "Invalid recipient email address."}

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = from_email
    msg["To"]      = to_email
    msg.attach(MIMEText(body, "plain", "utf-8"))

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


# ── Portfolio aggregation (cashflow snapshot) ───────────────────────────────────

def collect_invoices(contacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten every invoice across all CRM contacts, tagged with its contact."""
    out: list[dict[str, Any]] = []
    for c in contacts or []:
        for inv in c.get("invoices") or []:
            out.append({**inv, "_contact": c})
    return out


def cashflow_snapshot(contacts: list[dict[str, Any]], *, today: str = "") -> dict[str, Any]:
    """
    Aggregate totals for the Finance dashboard. Returns counts + amounts by
    status, grouped per currency (so mixed-currency portfolios stay honest).
    """
    from utils.crm_models import invoice_display_status

    today = today or utc_now_iso()[:10]
    invoices = collect_invoices(contacts)

    by_ccy: dict[str, dict[str, float]] = {}
    counts = {"draft": 0, "sent": 0, "paid": 0, "overdue": 0, "cancelled": 0}

    for inv in invoices:
        ccy = inv.get("currency", "INR")
        status = invoice_display_status(inv, today=today)
        counts[status] = counts.get(status, 0) + 1
        bucket = by_ccy.setdefault(ccy, {
            "invoiced": 0.0, "paid": 0.0, "outstanding": 0.0, "overdue": 0.0,
        })
        total = to_amount(inv.get("total"))
        if status == "cancelled":
            continue
        bucket["invoiced"] += total
        if status == "paid":
            bucket["paid"] += total
        else:  # draft / sent / overdue all count as not-yet-collected
            bucket["outstanding"] += total
            if status == "overdue":
                bucket["overdue"] += total

    for bucket in by_ccy.values():
        for k in bucket:
            bucket[k] = round(bucket[k], 2)

    return {
        "total_invoices": len(invoices),
        "counts": counts,
        "by_currency": by_ccy,
    }
