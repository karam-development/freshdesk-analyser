"""Source-level wiring tests for PR 21 — KB evidence on ticket detail.

These tests read app.py source and templates/ticket.html to assert that
the correct imports, wiring, and template constructs are present.
They do not start Flask or make HTTP requests.
"""
from __future__ import annotations

import ast
import re

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


APP_SRC = _read("app.py")
TEMPLATE_SRC = _read("templates/ticket.html")


# ── app.py: imports / uses build_kb_evidence_review ───────────────────────────


def test_app_imports_build_kb_evidence_review():
    assert "build_kb_evidence_review" in APP_SRC


def test_app_imports_retrieve_relevant_kb_entries_for_ticket_detail():
    # Should use retrieve_relevant_kb_entries inside ticket_detail wiring
    assert "retrieve_relevant_kb_entries" in APP_SRC


# ── app.py: ticket_detail sets kb_evidence_review ─────────────────────────────


def test_app_sets_kb_evidence_review_on_ticket_dict():
    assert 'ticket_dict["kb_evidence_review"]' in APP_SRC


def test_app_fallback_has_data_false():
    # Safe fallback sets has_data: False on exception
    assert '"has_data": False' in APP_SRC or "'has_data': False" in APP_SRC


def test_app_kb_evidence_review_inside_ticket_detail():
    # The wiring must appear after ticket_dict is constructed (ticket_detail route)
    ticket_detail_pos = APP_SRC.find("def ticket_detail(ticket_id):")
    assert ticket_detail_pos != -1, "ticket_detail function not found"

    kb_ev_pos = APP_SRC.find('ticket_dict["kb_evidence_review"]')
    assert kb_ev_pos != -1, "kb_evidence_review assignment not found"

    # Must appear AFTER the ticket_detail definition
    assert kb_ev_pos > ticket_detail_pos


def test_app_uses_subject_for_kb_retrieval():
    # retrieve_relevant_kb_entries call in ticket_detail uses subject=
    assert "subject=ticket_dict.get" in APP_SRC or 'subject=ticket_dict.get("subject")' in APP_SRC


def test_app_uses_template_name_for_kb_retrieval():
    assert "template_name=ticket_dict.get" in APP_SRC


def test_app_uses_workflow_name_for_kb_retrieval():
    assert "workflow_name=ticket_dict.get" in APP_SRC


# ── template: Relevant KB Evidence card ───────────────────────────────────────


def test_template_contains_kb_evidence_heading():
    assert "Relevant KB Evidence" in TEMPLATE_SRC


def test_template_no_relevant_kb_evidence_message():
    assert "No relevant KB evidence found for this ticket." in TEMPLATE_SRC


def test_template_references_kb_evidence_review():
    assert "kb_evidence_review" in TEMPLATE_SRC


def test_template_renders_has_data():
    assert "has_data" in TEMPLATE_SRC


def test_template_renders_evidence_type():
    # evidence_type is surfaced via badge_label in the template
    assert "badge_label" in TEMPLATE_SRC


def test_template_renders_badge_label():
    assert "badge_label" in TEMPLATE_SRC


def test_template_renders_title():
    # The table column for entry title
    assert "kbentry.title" in TEMPLATE_SRC


def test_template_renders_score():
    assert "kbentry.score" in TEMPLATE_SRC


def test_template_renders_snippet():
    assert "kbentry.snippet" in TEMPLATE_SRC


def test_template_renders_matched_terms():
    assert "matched_terms" in TEMPLATE_SRC


def test_template_renders_summary_count():
    assert "kbs.count" in TEMPLATE_SRC


def test_template_shows_legal_evidence_badge():
    assert "has_legal_evidence" in TEMPLATE_SRC
    assert "Legal evidence" in TEMPLATE_SRC


def test_template_shows_workaround_badge():
    assert "has_workaround_evidence" in TEMPLATE_SRC


def test_template_shows_existing_setting_badge():
    assert "has_existing_setting_evidence" in TEMPLATE_SRC


def test_template_shows_product_evidence_badge():
    assert "has_product_evidence" in TEMPLATE_SRC


# ── template: no form/save/edit controls in KB evidence card ──────────────────


def test_template_kb_card_has_no_form_submit():
    """The KB evidence card must not contain a <form> or <button type=submit>."""
    # Extract just the KB card section
    card_start = TEMPLATE_SRC.find("RELEVANT KB EVIDENCE CARD")
    card_end = TEMPLATE_SRC.find("STRUCTURED PM LESSONS USED CARD")
    assert card_start != -1, "KB evidence card comment not found"
    assert card_end != -1, "Structured PM lessons card comment not found"

    kb_card_section = TEMPLATE_SRC[card_start:card_end]

    # No <form> or submit button in KB card
    assert "<form" not in kb_card_section.lower()
    assert 'type="submit"' not in kb_card_section.lower()


def test_template_kb_card_has_no_input_elements():
    """KB evidence card is read-only — no input/textarea/select."""
    card_start = TEMPLATE_SRC.find("RELEVANT KB EVIDENCE CARD")
    card_end = TEMPLATE_SRC.find("STRUCTURED PM LESSONS USED CARD")
    kb_card_section = TEMPLATE_SRC[card_start:card_end]

    assert "<input" not in kb_card_section.lower()
    assert "<textarea" not in kb_card_section.lower()
    assert "<select" not in kb_card_section.lower()


def test_template_kb_card_has_no_save_button():
    """KB evidence card must not have a Save button."""
    card_start = TEMPLATE_SRC.find("RELEVANT KB EVIDENCE CARD")
    card_end = TEMPLATE_SRC.find("STRUCTURED PM LESSONS USED CARD")
    kb_card_section = TEMPLATE_SRC[card_start:card_end]

    assert "save" not in kb_card_section.lower()
    assert "edit" not in kb_card_section.lower()


# ── ai/kb_evidence_display.py is importable and returns correct structure ──────


def test_build_kb_evidence_review_importable():
    from ai.kb_evidence_display import build_kb_evidence_review
    assert callable(build_kb_evidence_review)


def test_build_kb_evidence_review_returns_has_data_key():
    from ai.kb_evidence_display import build_kb_evidence_review
    result = build_kb_evidence_review([])
    assert "has_data" in result


def test_build_kb_evidence_review_returns_entries_key():
    from ai.kb_evidence_display import build_kb_evidence_review
    result = build_kb_evidence_review([])
    assert "entries" in result


def test_build_kb_evidence_review_returns_summary_key():
    from ai.kb_evidence_display import build_kb_evidence_review
    result = build_kb_evidence_review([])
    assert "summary" in result


def test_build_kb_evidence_review_summary_has_count():
    from ai.kb_evidence_display import build_kb_evidence_review
    result = build_kb_evidence_review([])
    assert "count" in result["summary"]


# ══════════════════════════════════════════════════════════════════════════════
# PR 23 — score_reasons template and wiring tests
# ══════════════════════════════════════════════════════════════════════════════


def test_template_contains_why_matched_label():
    assert "Why matched" in TEMPLATE_SRC


def test_template_renders_score_reasons():
    assert "kbentry.score_reasons" in TEMPLATE_SRC


def test_template_contains_no_score_reasons_fallback():
    assert "No score reasons available" in TEMPLATE_SRC


def test_template_score_reasons_uses_for_loop():
    assert "for reason in kbentry.score_reasons" in TEMPLATE_SRC


def test_template_renders_reason_variable():
    assert "{{ reason }}" in TEMPLATE_SRC


def test_template_kb_card_still_has_no_form_after_pr23():
    card_start = TEMPLATE_SRC.find("RELEVANT KB EVIDENCE CARD")
    card_end = TEMPLATE_SRC.find("STRUCTURED PM LESSONS USED CARD")
    kb_section = TEMPLATE_SRC[card_start:card_end]
    assert "<form" not in kb_section.lower()
    assert 'type="submit"' not in kb_section.lower()


def test_template_kb_card_still_has_no_input_after_pr23():
    card_start = TEMPLATE_SRC.find("RELEVANT KB EVIDENCE CARD")
    card_end = TEMPLATE_SRC.find("STRUCTURED PM LESSONS USED CARD")
    kb_section = TEMPLATE_SRC[card_start:card_end]
    assert "<input" not in kb_section.lower()
    assert "<textarea" not in kb_section.lower()
    assert "<select" not in kb_section.lower()


def test_template_kb_card_still_has_no_save_after_pr23():
    card_start = TEMPLATE_SRC.find("RELEVANT KB EVIDENCE CARD")
    card_end = TEMPLATE_SRC.find("STRUCTURED PM LESSONS USED CARD")
    kb_section = TEMPLATE_SRC[card_start:card_end]
    assert "save" not in kb_section.lower()
    assert "edit" not in kb_section.lower()


def test_score_reasons_key_in_display_helper_return():
    from ai.kb_evidence_display import build_kb_evidence_review
    entry = {
        "title": "T", "category": "G", "content": "c",
        "score": 5, "matched_terms": [], "evidence_type": "general_evidence",
        "score_reasons": ["title:x +4"],
    }
    result = build_kb_evidence_review([entry])
    assert "score_reasons" in result["entries"][0]


def test_score_reasons_missing_does_not_crash_helper():
    from ai.kb_evidence_display import build_kb_evidence_review
    entry = {
        "title": "T", "category": "G", "content": "c",
        "score": 5, "matched_terms": [], "evidence_type": "general_evidence",
    }
    result = build_kb_evidence_review([entry])
    assert result["entries"][0]["score_reasons"] == []


def test_app_route_unchanged_no_kb_evidence_review_changes_needed():
    """ticket_detail route should not need changes for PR 23 — score_reasons
    flow from kb_retrieval through kb_evidence_display automatically."""
    # Confirm build_kb_evidence_review is still called in app.py
    assert "build_kb_evidence_review" in APP_SRC
    assert "retrieve_relevant_kb_entries" in APP_SRC
