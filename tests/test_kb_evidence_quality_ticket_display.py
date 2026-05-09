"""Source-level wiring tests for PR 27 — KB evidence quality signals.

These tests read app.py source and templates/ticket.html to assert that
the correct imports, wiring, and template constructs are present.
They do not start Flask or make HTTP requests.
"""
from __future__ import annotations


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


APP_SRC = _read("app.py")
TEMPLATE_SRC = _read("templates/ticket.html")


# ── app.py: imports / uses assess_kb_evidence_quality ─────────────────────────


def test_app_imports_assess_kb_evidence_quality():
    assert "assess_kb_evidence_quality" in APP_SRC


def test_app_imports_from_kb_evidence_quality():
    assert "kb_evidence_quality" in APP_SRC


# ── app.py: ticket_detail sets kb_evidence_quality_review ─────────────────────


def test_ticket_detail_sets_kb_evidence_quality_review():
    assert "kb_evidence_quality_review" in APP_SRC


def test_ticket_detail_sets_quality_review_after_load():
    td_pos = APP_SRC.find("def ticket_detail(ticket_id):")
    assert td_pos != -1
    quality_pos = APP_SRC.find("kb_evidence_quality_review", td_pos)
    assert quality_pos != -1 and quality_pos > td_pos


def test_ticket_detail_passes_ticket_context_to_quality():
    assert "ticket_context" in APP_SRC


def test_ticket_detail_has_fallback_for_quality_review():
    assert "overall_quality" in APP_SRC
    assert '"none"' in APP_SRC or "'none'" in APP_SRC


def test_ticket_detail_existing_kb_cards_still_present():
    assert "kb_evidence_review_source" in APP_SRC
    assert "kb_snapshot_flow_review" in APP_SRC
    assert "kb_snapshot_diff_review" in APP_SRC


# ── template: KB Evidence Quality card ────────────────────────────────────────


def test_template_contains_kb_evidence_quality_heading():
    assert "KB Evidence Quality" in TEMPLATE_SRC


def test_template_contains_no_quality_signals_message():
    assert "No KB evidence quality signals available." in TEMPLATE_SRC


def test_template_references_kb_evidence_quality_review():
    assert "kb_evidence_quality_review" in TEMPLATE_SRC


def test_template_renders_overall_quality():
    assert "overall_quality" in TEMPLATE_SRC


def test_template_renders_quality_score():
    assert "quality_score" in TEMPLATE_SRC


def test_template_renders_signals():
    assert "kbq.signals" in TEMPLATE_SRC


def test_template_renders_signal_title():
    assert "sig.title" in TEMPLATE_SRC


def test_template_renders_signal_message():
    assert "sig.message" in TEMPLATE_SRC


def test_template_renders_signal_severity():
    assert "sig.severity" in TEMPLATE_SRC


def test_template_renders_entry_count():
    assert "entry_count" in TEMPLATE_SRC


def test_template_renders_max_score():
    assert "kbqs.max_score" in TEMPLATE_SRC


def test_template_renders_avg_score():
    assert "kbqs.avg_score" in TEMPLATE_SRC


def test_template_renders_evidence_types():
    assert "kbqs.evidence_types" in TEMPLATE_SRC


def test_template_renders_strong_badge():
    assert "Strong" in TEMPLATE_SRC


def test_template_renders_moderate_badge():
    assert "Moderate" in TEMPLATE_SRC


def test_template_renders_weak_badge():
    assert "Weak" in TEMPLATE_SRC


def test_template_renders_mixed_badge():
    assert "Mixed" in TEMPLATE_SRC


# ── KB quality card is read-only ──────────────────────────────────────────────


def test_template_kb_quality_card_has_no_form():
    card_start = TEMPLATE_SRC.find("KB EVIDENCE QUALITY CARD")
    card_end = TEMPLATE_SRC.find("RELEVANT KB EVIDENCE CARD")
    assert card_start != -1, "KB quality card comment not found"
    assert card_end != -1, "Relevant KB evidence card comment not found"
    section = TEMPLATE_SRC[card_start:card_end].lower()
    assert "<form" not in section


def test_template_kb_quality_card_has_no_submit():
    card_start = TEMPLATE_SRC.find("KB EVIDENCE QUALITY CARD")
    card_end = TEMPLATE_SRC.find("RELEVANT KB EVIDENCE CARD")
    section = TEMPLATE_SRC[card_start:card_end].lower()
    assert 'type="submit"' not in section


def test_template_kb_quality_card_has_no_input():
    card_start = TEMPLATE_SRC.find("KB EVIDENCE QUALITY CARD")
    card_end = TEMPLATE_SRC.find("RELEVANT KB EVIDENCE CARD")
    section = TEMPLATE_SRC[card_start:card_end].lower()
    assert "<input" not in section
    assert "<textarea" not in section
    assert "<select" not in section


def test_template_kb_quality_card_has_no_save_or_edit():
    card_start = TEMPLATE_SRC.find("KB EVIDENCE QUALITY CARD")
    card_end = TEMPLATE_SRC.find("RELEVANT KB EVIDENCE CARD")
    section = TEMPLATE_SRC[card_start:card_end].lower()
    assert "save" not in section
    assert "edit" not in section


# ── Existing cards still intact ───────────────────────────────────────────────


def test_template_relevant_kb_evidence_card_still_present():
    assert "RELEVANT KB EVIDENCE CARD" in TEMPLATE_SRC
    assert "Relevant KB Evidence" in TEMPLATE_SRC


def test_template_kb_snapshots_by_flow_card_still_present():
    assert "KB EVIDENCE SNAPSHOTS BY FLOW CARD" in TEMPLATE_SRC


def test_template_kb_snapshot_diff_card_still_present():
    assert "KB SNAPSHOT DIFF SUMMARY CARD" in TEMPLATE_SRC
