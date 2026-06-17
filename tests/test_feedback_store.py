"""Tests for GitHub-backed feedback persistence helpers."""

from __future__ import annotations

from utils.feedback_store import append_feedback, empty_feedback_db, normalize_entry


def test_empty_feedback_db_shape():
    db = empty_feedback_db()
    assert db["version"] == 1
    assert db["entries"] == []
    assert "updated_at" in db


def test_normalize_entry_defaults():
    entry = normalize_entry({"message": "  Great CRM list  "})
    assert entry["message"] == "Great CRM list"
    assert entry["category"] == "other"
    assert entry["page"] == "crm"
    assert entry["id"]
    assert entry["created_at"]


def test_append_feedback_requires_message():
    db = empty_feedback_db()
    updated, outcome = append_feedback(db, message="   ")
    assert outcome["ok"] is False
    assert updated["entries"] == []


def test_append_feedback_appends_entry():
    db = empty_feedback_db()
    updated, outcome = append_feedback(
        db,
        message="Bulk delete is handy",
        category="praise",
        page="crm",
        page_label="CRM",
        submitted_by="Tester",
    )
    assert outcome["ok"] is True
    assert len(updated["entries"]) == 1
    assert updated["entries"][0]["message"] == "Bulk delete is handy"
    assert updated["entries"][0]["category"] == "praise"
    assert updated["entries"][0]["page"] == "crm"
    assert updated["entries"][0]["page_label"] == "CRM"
    assert updated["entries"][0]["submitted_by"] == "Tester"
