"""Source-level wiring tests for PR 24 — KB evidence snapshot persistence.

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


# ── DB migration ───────────────────────────────────────────────────────────────


def test_app_migration_includes_kb_evidence_json():
    assert "kb_evidence_json" in APP_SRC


def test_app_migration_default_is_empty_braces():
    # migration SQL sets DEFAULT '{}'
    assert "kb_evidence_json" in APP_SRC
    # The column default appears in the ALTER TABLE statement
    assert "kb_evidence_json" in APP_SRC and "'{}'" in APP_SRC


# ── app.py imports snapshot functions ─────────────────────────────────────────


def test_app_imports_build_kb_evidence_snapshot():
    assert "build_kb_evidence_snapshot" in APP_SRC


def test_app_imports_merge_kb_evidence_snapshot():
    assert "merge_kb_evidence_snapshot" in APP_SRC


def test_app_imports_load_kb_evidence_snapshot():
    assert "load_kb_evidence_snapshot" in APP_SRC


# ── app.py persists snapshots for each flow ───────────────────────────────────


def test_app_persists_snapshot_for_ingest_flow():
    assert 'flow="ingest"' in APP_SRC


def test_app_persists_snapshot_for_draft_flow():
    assert 'flow="draft"' in APP_SRC


def test_app_persists_snapshot_for_regeneration_flow():
    assert 'flow="regeneration"' in APP_SRC


def test_app_persists_snapshot_for_analysis_flow():
    assert 'flow="analysis"' in APP_SRC


def test_app_saves_kb_evidence_json_for_ingest():
    # UPDATE ... SET kb_evidence_json is used at ingest
    assert "kb_evidence_json" in APP_SRC
    # Must appear multiple times (once per flow)
    assert APP_SRC.count("kb_evidence_json") >= 4


def test_app_uses_json_dumps_for_snapshot_persistence():
    assert "json.dumps(_container_ingest" in APP_SRC or "json.dumps(_container_draft" in APP_SRC


# ── ticket_detail prefers snapshot ────────────────────────────────────────────


def test_ticket_detail_loads_kb_evidence_snapshot():
    td_pos = APP_SRC.find("def ticket_detail(ticket_id):")
    assert td_pos != -1
    load_pos = APP_SRC.find("load_kb_evidence_snapshot", td_pos)
    assert load_pos != -1 and load_pos > td_pos


def test_ticket_detail_sets_kb_evidence_review_source():
    assert 'kb_evidence_review_source' in APP_SRC


def test_ticket_detail_snapshot_source_value():
    assert '"snapshot"' in APP_SRC or "'snapshot'" in APP_SRC


def test_ticket_detail_live_source_value():
    assert '"live"' in APP_SRC or "'live'" in APP_SRC


def test_ticket_detail_sets_kb_evidence_snapshot():
    assert 'kb_evidence_snapshot' in APP_SRC


def test_ticket_detail_prefers_snapshot_before_live():
    # snapshot branch must come before live retrieval branch in ticket_detail
    td_pos = APP_SRC.find("def ticket_detail(ticket_id):")
    snap_branch_pos = APP_SRC.find('"snapshot"', td_pos)
    live_branch_pos = APP_SRC.find('"live"', td_pos)
    assert snap_branch_pos != -1
    assert live_branch_pos != -1
    assert snap_branch_pos < live_branch_pos


# ── template shows source and flow labels ─────────────────────────────────────


def test_template_shows_source_stored_snapshot():
    assert "Source: stored snapshot" in TEMPLATE_SRC


def test_template_shows_source_live_retrieval():
    assert "Source: live retrieval" in TEMPLATE_SRC


def test_template_shows_latest_flow():
    assert "Latest flow" in TEMPLATE_SRC


def test_template_references_kb_evidence_review_source():
    assert "kb_evidence_review_source" in TEMPLATE_SRC


def test_template_references_kb_evidence_snapshot():
    assert "kb_evidence_snapshot" in TEMPLATE_SRC


def test_template_kb_card_source_label_is_read_only():
    """Source/flow labels must not contain form/input/button elements."""
    card_start = TEMPLATE_SRC.find("RELEVANT KB EVIDENCE CARD")
    card_end = TEMPLATE_SRC.find("STRUCTURED PM LESSONS USED CARD")
    assert card_start != -1
    assert card_end != -1
    kb_section = TEMPLATE_SRC[card_start:card_end]
    assert "<form" not in kb_section.lower()
    assert "<input" not in kb_section.lower()
    assert 'type="submit"' not in kb_section.lower()
