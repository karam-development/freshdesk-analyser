"""Tests for docs/ROADMAP_UI_AUDIT.md — roadmap-ui-visibility-audit branch.

Source-level only — reads files as strings, no Flask, no DB.
"""
from __future__ import annotations

import os


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


AUDIT_DOC = _read("docs/ROADMAP_UI_AUDIT.md")


# ── Audit doc exists and has required structure ───────────────────────────────


def test_audit_doc_exists():
    assert os.path.isfile("docs/ROADMAP_UI_AUDIT.md")


def test_audit_doc_has_table_column_feature():
    assert "Feature" in AUDIT_DOC


def test_audit_doc_has_table_column_backend_exists():
    assert "Backend exists" in AUDIT_DOC


def test_audit_doc_has_table_column_visible_in_ui():
    assert "Visible in UI" in AUDIT_DOC


def test_audit_doc_has_table_column_configurable_in_ui():
    assert "Configurable in UI" in AUDIT_DOC


def test_audit_doc_has_table_column_location():
    assert "Location" in AUDIT_DOC


def test_audit_doc_has_table_column_status():
    assert "Status" in AUDIT_DOC


def test_audit_doc_has_table_column_gap():
    assert "Gap" in AUDIT_DOC


def test_audit_doc_has_table_column_fix_in_this_pr():
    assert "Fix in this PR" in AUDIT_DOC


def test_audit_doc_has_table_column_deferred_reason():
    assert "Deferred reason" in AUDIT_DOC


# ── Audit doc covers all required feature areas ──────────────────────────────


def test_audit_doc_covers_llm_provider():
    assert "llm_provider" in AUDIT_DOC


def test_audit_doc_covers_llm_api_key():
    assert "llm_api_key" in AUDIT_DOC


def test_audit_doc_covers_llmrouter():
    assert "LLMRouter" in AUDIT_DOC or "llm_provider" in AUDIT_DOC


def test_audit_doc_covers_semantic_rag_enabled():
    assert "semantic_rag_enabled" in AUDIT_DOC


def test_audit_doc_covers_semantic_rag_provider():
    assert "semantic_rag_provider" in AUDIT_DOC


def test_audit_doc_covers_semantic_embedding_model():
    assert "semantic_embedding_model" in AUDIT_DOC


def test_audit_doc_covers_kb_embedding_cache():
    assert "kb_embedding_cache" in AUDIT_DOC


def test_audit_doc_covers_source_badges():
    lower = AUDIT_DOC.lower()
    assert "source badge" in lower or "keyword" in lower and "semantic" in lower and "hybrid" in lower


def test_audit_doc_covers_safe_to_send_review():
    assert "Safe to Send" in AUDIT_DOC or "safe_to_send" in AUDIT_DOC


def test_audit_doc_covers_kb_snapshots():
    assert "Snapshot" in AUDIT_DOC or "snapshot" in AUDIT_DOC


def test_audit_doc_covers_kb_snapshot_diff():
    assert "Diff" in AUDIT_DOC or "diff" in AUDIT_DOC


def test_audit_doc_covers_structured_pm_lessons():
    assert "Structured PM Lessons" in AUDIT_DOC or "structured_pm_lessons" in AUDIT_DOC


def test_audit_doc_covers_agent_model_config():
    assert "agent_model_config" in AUDIT_DOC


def test_audit_doc_covers_system_readiness():
    assert "System Readiness" in AUDIT_DOC


def test_audit_doc_covers_security_readiness():
    assert "Security Readiness" in AUDIT_DOC


def test_audit_doc_has_summary_section():
    assert "Summary" in AUDIT_DOC
