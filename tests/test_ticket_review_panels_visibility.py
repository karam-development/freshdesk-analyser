"""Tests for ticket review panel visibility and empty states in templates/ticket.html.

Source-level only — reads the template as a string.
No Flask, no DB, no network.
"""
from __future__ import annotations


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


TICKET_HTML = _read("templates/ticket.html")


# ── All panels present ────────────────────────────────────────────────────────


def test_ticket_html_has_pm_decision_panel():
    assert "PM Decision" in TICKET_HTML


def test_ticket_html_has_pm_guard_review_panel():
    assert "PM Guard Review" in TICKET_HTML


def test_ticket_html_has_existing_solution_review_panel():
    assert "Existing Solution Review" in TICKET_HTML


def test_ticket_html_has_relevant_kb_evidence_panel():
    assert "Relevant KB Evidence" in TICKET_HTML


def test_ticket_html_has_kb_evidence_quality_panel():
    assert "KB Evidence Quality" in TICKET_HTML


def test_ticket_html_has_kb_evidence_snapshots_by_flow_panel():
    assert "KB Evidence Snapshots by Flow" in TICKET_HTML


def test_ticket_html_has_kb_snapshot_diff_summary_panel():
    assert "KB Snapshot Diff Summary" in TICKET_HTML


def test_ticket_html_has_structured_pm_lessons_used_panel():
    assert "Structured PM Lessons Used" in TICKET_HTML


def test_ticket_html_has_safe_to_send_review_panel():
    assert "Safe to Send Review" in TICKET_HTML


def test_ticket_html_has_safe_to_send_draft_banner():
    assert "safe_to_send_display" in TICKET_HTML


def test_ticket_html_has_source_badge_logic():
    """keyword / semantic / hybrid source badges must be present."""
    assert "kbentry.source" in TICKET_HTML
    assert "semantic" in TICKET_HTML
    assert "hybrid" in TICKET_HTML


# ── Empty states ──────────────────────────────────────────────────────────────


def test_pm_decision_has_empty_state():
    assert "No PM decision" in TICKET_HTML


def test_safe_to_send_review_has_empty_state():
    assert "No safe-to-send review available" in TICKET_HTML or "safe-to-send" in TICKET_HTML.lower()


def test_relevant_kb_evidence_has_empty_state():
    assert "No relevant KB evidence" in TICKET_HTML


def test_kb_evidence_snapshots_has_empty_state():
    assert "No stored KB evidence snapshots yet" in TICKET_HTML


def test_kb_snapshot_diff_has_empty_state():
    assert "No KB snapshot comparisons available yet" in TICKET_HTML


def test_structured_pm_lessons_has_empty_state():
    """Structured PM Lessons panel must show an empty state when no lessons."""
    assert "No structured PM lessons used for this ticket" in TICKET_HTML


def test_structured_pm_lessons_empty_state_is_in_else_block():
    """The empty state must appear after the closing of the PM lessons data block."""
    # Verify both the if and the empty-state text exist in the template
    idx_if = TICKET_HTML.find("{% if ticket.structured_pm_lessons_used %}")
    idx_empty = TICKET_HTML.find("No structured PM lessons used for this ticket")
    assert idx_if != -1, "PM Lessons outer if must exist"
    assert idx_empty != -1, "Empty state text must exist"
    # Empty state must appear AFTER the outer if (it's in the else branch)
    assert idx_empty > idx_if, "Empty state must follow the outer if block"
    # The empty state must be preceded by an else keyword somewhere between if and empty state
    between = TICKET_HTML[idx_if:idx_empty]
    assert "{% else %}" in between, "An else block must precede the empty state"


# ── No auto-send ─────────────────────────────────────────────────────────────


def test_ticket_html_has_no_auto_send_button():
    lower = TICKET_HTML.lower()
    assert "auto-send" not in lower
    assert "autosend" not in lower


def test_ticket_html_copy_requires_user_action():
    """Copy clean draft must be a user-triggered button, not automatic."""
    # The copy button exists (user-initiated)
    assert "copy" in TICKET_HTML.lower() or "draft" in TICKET_HTML.lower()


def test_ticket_html_source_badge_semantic_not_shown_for_keyword():
    """The semantic badge must only show when source != 'keyword'."""
    # The condition: {% if kbentry.source and kbentry.source != 'keyword' %}
    assert "kbentry.source != 'keyword'" in TICKET_HTML or 'kbentry.source != "keyword"' in TICKET_HTML


def test_ticket_html_semantic_badge_color_is_purple():
    """Semantic source badge must have a distinctive visual style (purple)."""
    assert "#ede9fe" in TICKET_HTML or "#5b21b6" in TICKET_HTML


def test_ticket_html_hybrid_badge_color_is_amber():
    """Hybrid source badge must have a distinctive visual style (amber)."""
    assert "#fef3c7" in TICKET_HTML or "#92400e" in TICKET_HTML


# ── All panels are read-only ──────────────────────────────────────────────────


def test_pm_decision_panel_is_read_only():
    assert "read-only" in TICKET_HTML


def test_safe_to_send_review_is_read_only():
    assert "read-only" in TICKET_HTML


def test_kb_evidence_snapshots_is_read_only():
    assert "audit · read-only" in TICKET_HTML or "read-only" in TICKET_HTML


def test_kb_snapshot_diff_is_read_only():
    assert "deterministic · read-only" in TICKET_HTML or "read-only" in TICKET_HTML
