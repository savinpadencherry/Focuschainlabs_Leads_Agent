"""Reusable "How to use this agent" cards.

One collapsible panel per agent: a one-line description, when to use it, and a
concrete worked example. Rendered at the top of every agent page so a new user
always knows what the page does and how to drive it.
"""

from __future__ import annotations

import html

import streamlit as st

_GUIDES: dict[str, dict] = {
    "scout": {
        "title": "Scout Agent",
        "tagline": "Finds companies that are ready to buy.",
        "what": "Describe your ideal customer in plain English. Scout searches the web, researches each company, scores buying signals, and returns a ranked shortlist with reasons.",
        "steps": [
            "Type who you sell to and what you offer (or pick a saved ICP).",
            "Press <b>Run</b> and watch it research companies live.",
            "Review the scored leads, then push the good ones to your CRM.",
        ],
        "example": "“Mid-size real-estate developers in Bangalore who are hiring sales staff and would benefit from AI lead-gen.”",
    },
    "reach": {
        "title": "Reach Agent",
        "tagline": "Writes and sends personalised outreach.",
        "what": "Pick a lead from your pipeline. Reach drafts a tailored first email using the company's signals, lets you edit it, and can send it straight from your Gmail.",
        "steps": [
            "Select a contact from the queue.",
            "Generate the draft, then tweak the tone or details.",
            "Send via Gmail — it's logged back on the contact automatically.",
        ],
        "example": "Select “Rajesh @ Prestige Group” → generate → a 5-line email referencing their recent sales-team expansion.",
    },
    "intel": {
        "title": "Intel Agent",
        "tagline": "Monitors your pipeline for fresh news.",
        "what": "Scans the web for recent news, hiring, funding, and launches about the companies already in your pipeline — so you reach out with perfect timing.",
        "steps": [
            "Open Intel; it reads the companies in your CRM/pipeline.",
            "Run a scan to pull the latest signals per company.",
            "Use a signal as the hook for your next Reach email.",
        ],
        "example": "Intel surfaces “SN Realtors opened a new Whitefield office” → a timely reason to follow up.",
    },
    "proposal": {
        "title": "Proposal Agent",
        "tagline": "Drafts a tailored B2B proposal.",
        "what": "Turns a qualified deal into a structured proposal — scope, deliverables, pricing — as clean HTML you can download or email.",
        "steps": [
            "Pick the deal and confirm scope and pricing.",
            "Generate the proposal and review the sections.",
            "Download the HTML or email it to the client.",
        ],
        "example": "Won-stage deal → a proposal with phased delivery and INR pricing, ready to send.",
    },
    "finance": {
        "title": "Finance Agent",
        "tagline": "Invoices, tracks payment, and chases overdue.",
        "what": "Turns a won deal into an invoice (free, no AI cost), tracks its status, and drafts AI dunning emails that escalate politely as an invoice ages.",
        "steps": [
            "Create an invoice from a won deal (line items auto-total).",
            "Send it and mark it sent/paid as money moves.",
            "For overdue invoices, generate a reminder and send it.",
        ],
        "example": "₹1,50,000 invoice 20 days overdue → a firm-but-warm level-2 reminder, ready to send.",
    },
    "crm": {
        "title": "Contact CRM",
        "tagline": "Your single working list of every lead.",
        "what": "Every contact, follow-up, invoice, and conversation in one place. Add leads by typing or dictating a sentence, importing a Scout run, or quick-typing — then search, filter, and work them.",
        "steps": [
            "Add a lead with <b>Add with AI</b> — type a sentence (or tap the box and use your keyboard's mic to dictate, free, no AI), then let the agent structure and save it.",
            "Search and filter to find anyone instantly, even across thousands.",
            "Open a contact → <b>Activity</b> tab → <b>Send WhatsApp</b> to message one lead, or select multiple leads for a broadcast.",
        ],
        "example": "Click Add with AI → type or dictate “Add Priya Nair, founder of Zenith Interiors, 98xxxxxx12, met at the Mumbai expo, wants a demo next week” → review the text → Review with AI.",
    },
}


def render_usage_guide(agent_key: str, *, expanded: bool = False) -> None:
    """Render the collapsible how-to card for the given agent page."""
    guide = _GUIDES.get(agent_key)
    if not guide:
        return

    steps_html = "".join(f"<li>{s}</li>" for s in guide["steps"])
    example = html.escape(guide["example"])

    st.markdown(
        """
        <style>
        .ug-card{background:rgba(46,139,77,.06);border:1px solid rgba(46,139,77,.22);
          border-radius:14px;padding:14px 18px;margin:4px 0 14px;}
        .ug-card .ug-tag{font-family:'JetBrains Mono',monospace;font-size:11px;
          letter-spacing:.08em;text-transform:uppercase;color:#2E8B4D;font-weight:600;}
        .ug-card .ug-what{color:#0F2A33;margin:6px 0 10px;font-size:14.5px;line-height:1.5;}
        .ug-card ol{margin:0 0 10px 18px;padding:0;color:#0F2A33;font-size:13.5px;line-height:1.7;}
        .ug-card .ug-eg{background:rgba(15,42,51,.05);border-left:3px solid #2E8B4D;
          border-radius:6px;padding:8px 12px;font-size:13px;color:#33514f;}
        .ug-card .ug-eg b{color:#0F2A33;}
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.expander(f"ℹ️  How to use the {guide['title']} — {guide['tagline']}", expanded=expanded):
        st.markdown(
            f"""
            <div class="ug-card">
              <div class="ug-tag">What it does</div>
              <div class="ug-what">{guide['what']}</div>
              <div class="ug-tag">How to use it</div>
              <ol>{steps_html}</ol>
              <div class="ug-eg"><b>Example —</b> {example}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
