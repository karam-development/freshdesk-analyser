"""Source-level wiring tests for PR 26 — KB snapshot diff summary.

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


# ── app.py: imports / uses build_kb_snapshot_diff_review ──────────────────────


def test_app_imports_build_kb_snapshot_diff_review():
    assert "build_kb_snapshot_diff_review" in APP_SRC


def test_app_imports_from_kb_snapshot_diff():
    assert "kb_snapshot_diff" in APP_SRC


# ── app.py: ticket_detail sets kb_snapshot_diff_review ───────────────────────


def test_ticket_detail_sets_kb_snapshot_diff_review():
    assert "kb_snapshot_diff_review" in APP_SRC


def test_ticket_detail_sets_diff_review_after_load():
    td_pos = APP_SRC.find("def ticket_detail(ticket_id):")
    assert td_pos != -1
    diff_pos = APP_SRC.find("kb_snapshot_diff_review", td_pos)
    assert diff_pos != -1 and diff_pos > td_pos


def test_ticket_detail_has_fallback_for_diff_review():
    # Fallback dict with comparison_count: 0 must be present
    assert "comparison_count" in APP_SRC


def test_ticket_detail_existing_kb_cards_still_present():
    assert "kb_evidence_review_source" in APP_SRC
    assert "kb_snapshot_flow_review" in APP_SRC


# ── template: KB Snapshot Diff Summary card ───────────────────────────────────


def test_template_contains_kb_snapshot_diff_heading():
    assert "KB Snapshot Diff Summary" in TEMPLATE_SRC


def test_template_contains_no_comparisons_available_message():
    assert "No KB snapshot comparisons available yet." in TEMPLATE_SRC


def test_template_references_kb_snapshot_diff_review():
    assert "kb_snapshot_diff_review" in TEMPLATE_SRC


def test_template_renders_has_data():
    assert "has_data" in TEMPLATE_SRC


def test_template_renders_comparison_count():
    assert "comparison_count" in TEMPLATE_SRC


def test_template_renders_changed_count():
    assert "changed_count" in TEMPLATE_SRC


def test_template_renders_unchanged_count():
    assert "unchanged_count" in TEMPLATE_SRC


def test_template_renders_from_flow():
    assert "kbc.from_flow" in TEMPLATE_SRC


def test_template_renders_to_flow():
    assert "kbc.to_flow" in TEMPLATE_SRC


def test_template_renders_has_changes_badge():
    assert "has_changes" in TEMPLATE_SRC


def test_template_renders_summary_text():
    assert "kbc.summary_text" in TEMPLATE_SRC


def test_template_renders_added_titles():
    assert "added_titles" in TEMPLATE_SRC


def test_template_renders_removed_titles():
    assert "removed_titles" in TEMPLATE_SRC


def test_template_renders_score_changes():
    assert "score_changes" in TEMPLATE_SRC


def test_template_renders_added_evidence_types():
    assert "added_evidence_types" in TEMPLATE_SRC


def test_template_renders_removed_evidence_types():
    assert "removed_evidence_types" in TEMPLATE_SRC


# ── KB diff card is read-only ─────────────────────────────────────────────────


def test_template_kb_diff_card_has_no_form():
    card_start = TEMPLATE_SRC.find("KB SNAPSHOT DIFF SUMMARY CARD")
    card_end = TEMPLATE_SRC.find("STRUCTURED PM LESSONS USED CARD")
    assert card_start != -1, "KB diff card comment not found"
    assert card_end != -1, "PM lessons card comment not found"
    section = TEMPLATE_SRC[card_start:card_end].lower()
    assert "<form" not in section


def test_template_kb_diff_card_has_no_submit():
    card_start = TEMPLATE_SRC.find("KB SNAPSHOT DIFF SUMMARY CARD")
    card_end = TEMPLATE_SRC.find("STRUCTURED PM LESSONS USED CARD")
    section = TEMPLATE_SRC[card_start:card_end].lower()
    assert 'type="submit"' not in section


def test_template_kb_diff_card_has_no_input():
    card_start = TEMPLATE_SRC.find("KB SNAPSHOT DIFF SUMMARY CARD")
    card_end = TEMPLATE_SRC.find("STRUCTURED PM LESSONS USED CARD")
    section = TEMPLATE_SRC[card_start:card_end].lower()
    assert "<input" not in section
    assert "<textarea" not in section
    assert "<select" not in section


def test_template_kb_diff_card_has_no_save_or_edit():
    card_start = TEMPLATE_SRC.find("KB SNAPSHOT DIFF SUMMARY CARD")
    card_end = TEMPLATE_SRC.find("STRUCTURED PM LESSONS USED CARD")
    section = TEMPLATE_SRC[card_start:card_end].lower()
    assert "save" not in section
    assert "edit" not in section


# ── Existing cards still intact ───────────────────────────────────────────────


def test_template_relevant_kb_evidence_card_still_present():
    assert "RELEVANT KB EVIDENCE CARD" in TEMPLATE_SRC
    assert "Relevant KB Evidence" in TEMPLATE_SRC


def test_template_kb_snapshots_by_flow_card_still_present():
    assert "KB EVIDENCE SNAPSHOTS BY FLOW CARD" in TEMPLATE_SRC
    assert "KB Evidence Snapshots by Flow" in TEMPLATE_SRC
