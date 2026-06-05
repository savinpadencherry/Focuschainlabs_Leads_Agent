"""Reach-path helpers for turning contact data into SDR action."""

from __future__ import annotations


def _clean(value) -> str:
    text = str(value or "").strip()
    low = text.lower()
    if low in {"n/a", "na", "none", "unknown", "not available", "not applicable"}:
        return ""
    if low.startswith("n/a") or low.startswith("not a company"):
        return ""
    return text


def contact_label(lead: dict) -> str:
    name = _clean(lead.get("contact_name"))
    title = _clean(lead.get("contact_title") or lead.get("responsible_owner"))
    if name and title:
        return f"{name} ({title})"
    return name or title or "the responsible decision maker"


def best_reach_channel(lead: dict) -> str:
    email = _clean(lead.get("email"))
    phone = _clean(lead.get("phone"))
    if email and phone:
        return "Email + phone"
    if email:
        return "Email"
    if phone:
        return "Phone"
    if _clean(lead.get("linkedin_url")):
        return "LinkedIn"
    if _clean(lead.get("website")):
        return "Website"
    return "Manual lookup"


def how_to_reach(lead: dict) -> str:
    target = contact_label(lead)
    email = _clean(lead.get("email"))
    phone = _clean(lead.get("phone"))
    linkedin = _clean(lead.get("linkedin_url"))
    website = _clean(lead.get("website"))
    signal = _clean(lead.get("reason_to_reach") or lead.get("primary_signal"))

    tail = f" Anchor the opener to: {signal}" if signal else ""
    if email and phone:
        return f"Email {target} at {email}, then follow up by phone at {phone}.{tail}"
    if email:
        return f"Email {target} at {email}.{tail}"
    if phone:
        return f"Call {phone} and ask for {target}.{tail}"
    if linkedin:
        return f"Reach {target} via LinkedIn; use the company signal as the opener.{tail}"
    if website:
        return f"Use the website contact path and ask for {target}.{tail}"
    return f"Manually verify the current owner for {target} before outreach.{tail}"
