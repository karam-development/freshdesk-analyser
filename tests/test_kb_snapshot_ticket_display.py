"""Source-level wiring tests for PR 25 — KB evidence snapshots by flow.

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


# ── app.py: imports / uses build_kb_snapshot_flow_review ──────────────────────


def test_app_imports_build_kb_snapshot_flow_review():
    assert "build_kb_snapshot_flow_review" in APP_SRC


def test_app_imports_from_kb_snapshot_display():
    assert "kb_snapshot_display" in APP_SRC


# ── app.py: ticket_detail sets kb_snapshot_flow_review ────────────────────────


def test_ticket_detail_sets_kb_snapshot_flow_review():
    assert 'kb_snapshot_flow_review' in APP_SRC


def test_ticket_detail_sets_kb_snapshot_flow_review_after_load():
    td_pos = APP_SRC.find("def ticket_detail(ticket_id):")
    assert td_pos != -1
    flow_rev_pos = APP_SRC.find("kb_snapshot_flow_review", td_pos)
    assert flow_rev_pos != -1 and flow_rev_pos > td_pos


def test_ticket_detail_has_fallback_for_kb_snapshot_flow_review():
    # Fallback dict with has_data: False must be present
    assert '"has_data": False' in APP_SRC or "'has_data': False" in APP_SRC


def test_ticket_detail_existing_kb_evidence_review_still_present():
    # Existing snapshot-preferred latest card must not be removed
    assert "kb_evidence_review_source" in APP_SRC
    assert "kb_evidence_review" in APP_SRC


# ── template: KB Evidence Snapshots by Flow card ──────────────────────────────


def test_template_contains_kb_snapshots_by_flow_heading():
    assert "KB Evidence Snapshots by Flow" in TEMPLATE_SRC


def test_template_contains_no_stored_snapshots_message():
    assert "No stored KB evidence snapshots yet." in TEMPLATE_SRC


def test_template_references_kb_snapshot_flow_review():
    assert "kb_snapshot_flow_review" in TEMPLATE_SRC


def test_template_renders_has_data():
    assert "has_data" in TEMPLATE_SRC


def test_template_renders_flow_count():
    assert "flow_count" in TEMPLATE_SRC


def test_template_renders_flows_present():
    assert "flows_present" in TEMPLATE_SRC


def test_template_renders_has_different_flows():
    assert "has_different_flows" in TEMPLATE_SRC


def test_template_renders_flow_name_badge():
    # Flow name is rendered per-flow
    assert "kbflow.flow" in TEMPLATE_SRC


def test_template_renders_entry_count():
    assert "entry_count" in TEMPLATE_SRC


def test_template_renders_evidence_types_per_flow():
    assert "evidence_types" in TEMPLATE_SRC


def test_template_renders_matched_terms():
    assert "matched_terms" in TEMPLATE_SRC


def test_template_renders_score_reasons():
    assert "score_reasons" in TEMPLATE_SRC


def test_template_renders_entry_title():
    assert "kbfe.title" in TEMPLATE_SRC


def test_template_renders_entry_score():
    assert "kbfe.score" in TEMPLATE_SRC


def test_template_renders_entry_snippet():
    assert "kbfe.snippet" in TEMPLATE_SRC


def test_template_renders_entry_evidence_type():
    assert "kbfe.evidence_type" in TEMPLATE_SRC


def test_template_renders_created_at_per_flow():
    assert "kbflow.created_at" in TEMPLATE_SRC


# ── KB snapshot card is read-only ─────────────────────────────────────────────


def test_template_kb_snapshot_card_has_no_form():
    card_start = TEMPLATE_SRC.find("KB EVIDENCE SNAPSHOTS BY FLOW CARD")
    card_end = TEMPLATE_SRC.find("STRUCTURED PM LESSONS USED CARD")
    assert card_start != -1, "KB snapshots by flow card comment not found"
    assert card_end != -1, "PM lessons card comment not found"
    section = TEMPLATE_SRC[card_start:card_end].lower()
    assert "<form" not in section


def test_template_kb_snapshot_card_has_no_submit():
    card_start = TEMPLATE_SRC.find("KB EVIDENCE SNAPSHOTS BY FLOW CARD")
    card_end = TEMPLATE_SRC.find("STRUCTURED PM LESSONS USED CARD")
    section = TEMPLATE_SRC[card_start:card_end].lower()
    assert 'type="submit"' not in section


def test_template_kb_snapshot_card_has_no_input():
    card_start = TEMPLATE_SRC.find("KB EVIDENCE SNAPSHOTS BY FLOW CARD")
    card_end = TEMPLATE_SRC.find("STRUCTURED PM LESSONS USED CARD")
    section = TEMPLATE_SRC[card_start:card_end].lower()
    assert "<input" not in section
    assert "<textarea" not in section
    assert "<select" not in section


def test_template_kb_snapshot_card_has_no_save_or_edit():
    card_start = TEMPLATE_SRC.find("KB EVIDENCE SNAPSHOTS BY FLOW CARD")
    card_end = TEMPLATE_SRC.find("STRUCTURED PM LESSONS USED CARD")
    section = TEMPLATE_SRC[card_start:card_end].lower()
    assert "save" not in section
    assert "edit" not in section


# ── Existing KB evidence card still intact ────────────────────────────────────


def test_template_existing_kb_evidence_card_still_present():
    assert "RELEVANT KB EVIDENCE CARD" in TEMPLATE_SRC
    assert "Relevant KB Evidence" in TEMPLATE_SRC


def test_template_existing_source_labels_still_present():
    assert "Source: stored snapshot" in TEMPLATE_SRC
    assert "Source: live retrieval" in TEMPLATE_SRC
