"""Source-level wiring tests for PR 28 — safe-to-send review on ticket detail.

These tests read app.py source and templates/ticket.html to assert that
the correct imports, wiring, and template constructs are present.
They do not start Flask or make HTTP requests.
"""
from __future__ import annotations

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


APP_SRC = _read("app.py")
TEMPLATE_SRC = _read("templates/ticket.html")


# ── app.py: imports build_safe_to_send_review ─────────────────────────────────


def test_app_imports_build_safe_to_send_review():
    assert "build_safe_to_send_review" in APP_SRC


def test_app_imports_from_ai_safe_to_send_review():
    assert "from ai.safe_to_send_review import build_safe_to_send_review" in APP_SRC


# ── app.py: ticket_detail sets safe_to_send_review ────────────────────────────


def test_app_sets_safe_to_send_review_on_ticket_dict():
    assert 'ticket_dict["safe_to_send_review"]' in APP_SRC


def test_app_safe_to_send_review_inside_ticket_detail():
    ticket_detail_pos = APP_SRC.find("def ticket_detail(ticket_id):")
    assert ticket_detail_pos != -1, "ticket_detail function not found"
    sts_pos = APP_SRC.find('ticket_dict["safe_to_send_review"]')
    assert sts_pos != -1, "safe_to_send_review assignment not found"
    assert sts_pos > ticket_detail_pos


def test_app_passes_pm_decision_to_safe_to_send():
    assert 'pm_decision=ticket_dict.get("pm_decision")' in APP_SRC


def test_app_passes_pm_guard_warnings_to_safe_to_send():
    assert 'pm_guard_warnings=ticket_dict.get("pm_guard_warnings")' in APP_SRC


def test_app_passes_kb_evidence_quality_review_to_safe_to_send():
    assert 'kb_evidence_quality_review=ticket_dict.get("kb_evidence_quality_review")' in APP_SRC


def test_app_passes_kb_snapshot_diff_review_to_safe_to_send():
    assert 'kb_snapshot_diff_review=ticket_dict.get("kb_snapshot_diff_review")' in APP_SRC


def test_app_passes_draft_text_to_safe_to_send():
    assert 'draft_text=ticket_dict.get("draft_response_clean")' in APP_SRC


def test_app_safe_to_send_fallback_has_data_false():
    assert '"has_data": False' in APP_SRC or "'has_data': False" in APP_SRC


def test_app_safe_to_send_fallback_has_status_needs_review():
    assert '"status": "needs_review"' in APP_SRC or "'status': 'needs_review'" in APP_SRC


def test_app_safe_to_send_is_after_kb_evidence_quality():
    kb_quality_pos = APP_SRC.find('ticket_dict["kb_evidence_quality_review"]')
    sts_pos = APP_SRC.find('ticket_dict["safe_to_send_review"]')
    assert kb_quality_pos != -1 and sts_pos != -1
    assert sts_pos > kb_quality_pos


def test_app_safe_to_send_is_before_render_template():
    sts_pos = APP_SRC.find('ticket_dict["safe_to_send_review"]')
    render_pos = APP_SRC.find('return render_template("ticket.html"')
    assert sts_pos != -1 and render_pos != -1
    assert sts_pos < render_pos


# ── template: Safe to Send Review card ───────────────────────────────────────


def test_template_contains_safe_to_send_review_heading():
    assert "Safe to Send Review" in TEMPLATE_SRC


def test_template_contains_safe_to_send_card_comment():
    assert "SAFE TO SEND REVIEW CARD" in TEMPLATE_SRC


def test_template_references_safe_to_send_review():
    assert "safe_to_send_review" in TEMPLATE_SRC


def test_template_renders_has_data():
    assert "has_data" in TEMPLATE_SRC


def test_template_renders_status():
    assert "sts.status" in TEMPLATE_SRC


def test_template_renders_risk_level():
    assert "sts.risk_level" in TEMPLATE_SRC


def test_template_renders_score():
    assert "sts.score" in TEMPLATE_SRC


def test_template_renders_reasons():
    assert "sts.reasons" in TEMPLATE_SRC


def test_template_renders_reason_severity():
    assert "reason.severity" in TEMPLATE_SRC


def test_template_renders_reason_title():
    assert "reason.title" in TEMPLATE_SRC


def test_template_renders_reason_message():
    assert "reason.message" in TEMPLATE_SRC


def test_template_renders_blocker_count():
    assert "blocker_count" in TEMPLATE_SRC


def test_template_shows_safe_to_send_status():
    assert "safe_to_send" in TEMPLATE_SRC
    assert "Safe to send" in TEMPLATE_SRC


def test_template_shows_needs_review_status():
    assert "needs_review" in TEMPLATE_SRC
    assert "Needs review" in TEMPLATE_SRC


def test_template_shows_do_not_send_status():
    assert "do_not_send" in TEMPLATE_SRC
    assert "Do not send" in TEMPLATE_SRC


def test_template_no_relevant_kb_evidence_message():
    """Original test from PR 21/23 — still passes after PR 28 additions."""
    assert "No relevant KB evidence found for this ticket." in TEMPLATE_SRC


# ── template: safe-to-send card is read-only (no forms / inputs) ─────────────


def test_template_safe_to_send_card_has_no_form_submit():
    card_start = TEMPLATE_SRC.find("SAFE TO SEND REVIEW CARD")
    card_end = TEMPLATE_SRC.find("PM GUARD REVIEW CARD")
    assert card_start != -1, "SAFE TO SEND REVIEW CARD comment not found"
    assert card_end != -1, "PM GUARD REVIEW CARD comment not found"

    section = TEMPLATE_SRC[card_start:card_end]
    assert "<form" not in section.lower()
    assert 'type="submit"' not in section.lower()


def test_template_safe_to_send_card_has_no_input_elements():
    card_start = TEMPLATE_SRC.find("SAFE TO SEND REVIEW CARD")
    card_end = TEMPLATE_SRC.find("PM GUARD REVIEW CARD")
    section = TEMPLATE_SRC[card_start:card_end]

    assert "<input" not in section.lower()
    assert "<textarea" not in section.lower()
    assert "<select" not in section.lower()


def test_template_safe_to_send_card_has_no_save_or_edit():
    card_start = TEMPLATE_SRC.find("SAFE TO SEND REVIEW CARD")
    card_end = TEMPLATE_SRC.find("PM GUARD REVIEW CARD")
    section = TEMPLATE_SRC[card_start:card_end]

    assert "save" not in section.lower()
    assert "edit" not in section.lower()


# ── Existing KB evidence tests still pass ────────────────────────────────────


def test_existing_relevant_kb_evidence_card_present():
    """RELEVANT KB EVIDENCE CARD from PR 21 must still be present."""
    assert "RELEVANT KB EVIDENCE CARD" in TEMPLATE_SRC


def test_existing_kb_evidence_quality_card_present():
    """KB EVIDENCE QUALITY CARD from PR 27 must still be present."""
    assert "KB EVIDENCE QUALITY CARD" in TEMPLATE_SRC


# ── ai/safe_to_send_review.py is importable ──────────────────────────────────


def test_build_safe_to_send_review_importable():
    from ai.safe_to_send_review import build_safe_to_send_review
    assert callable(build_safe_to_send_review)


def test_build_safe_to_send_review_returns_has_data_key():
    from ai.safe_to_send_review import build_safe_to_send_review
    result = build_safe_to_send_review()
    assert "has_data" in result


def test_build_safe_to_send_review_returns_status_key():
    from ai.safe_to_send_review import build_safe_to_send_review
    result = build_safe_to_send_review(draft_text="Hello this is a test draft reply.")
    assert "status" in result


def test_build_safe_to_send_review_returns_score_key():
    from ai.safe_to_send_review import build_safe_to_send_review
    result = build_safe_to_send_review(draft_text="Hello this is a test draft reply.")
    assert "score" in result


def test_build_safe_to_send_review_returns_reasons_key():
    from ai.safe_to_send_review import build_safe_to_send_review
    result = build_safe_to_send_review(draft_text="Hello this is a test draft reply.")
    assert "reasons" in result


def test_build_safe_to_send_review_returns_summary_key():
    from ai.safe_to_send_review import build_safe_to_send_review
    result = build_safe_to_send_review(draft_text="Hello this is a test draft reply.")
    assert "summary" in result
