"""Tests for ai/kb_retrieval.py — deterministic KB evidence retrieval."""
from __future__ import annotations

import sqlite3

import pytest

from ai.kb_retrieval import (
    normalize_text,
    extract_ticket_keywords,
    retrieve_relevant_kb_entries,
    summarize_kb_evidence,
    derive_kb_evidence_signals,
)


# ── In-memory DB helpers ───────────────────────────────────────────────────────


def _make_db():
    """Return an in-memory SQLite connection with the knowledge_base schema."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("""
        CREATE TABLE knowledge_base (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL
        )
    """)
    return db


def _insert(db, category: str, title: str, content: str) -> int:
    cur = db.execute(
        "INSERT INTO knowledge_base (category, title, content) VALUES (?, ?, ?)",
        (category, title, content),
    )
    db.commit()
    return cur.lastrowid


# ── normalize_text ─────────────────────────────────────────────────────────────


def test_normalize_text_basic():
    assert normalize_text("Hello, World!") == "hello world"


def test_normalize_text_empty():
    assert normalize_text("") == ""


def test_normalize_text_special_chars():
    result = normalize_text("it's a test — item #1")
    assert "it" in result
    assert "test" in result
    assert "#" not in result


def test_normalize_text_numbers():
    result = normalize_text("Invoice #2024-01")
    assert "invoice" in result
    assert "2024" in result


# ── extract_ticket_keywords ────────────────────────────────────────────────────


def test_extract_keywords_basic():
    kws = extract_ticket_keywords(subject="invoice date format")
    assert "invoice" in kws
    assert "date" in kws
    assert "format" in kws


def test_extract_keywords_removes_stopwords():
    kws = extract_ticket_keywords(subject="the is a an")
    # all are stop words
    assert len(kws) == 0


def test_extract_keywords_deduplication():
    kws = extract_ticket_keywords(subject="invoice date", summary="invoice format date")
    assert kws.count("invoice") == 1
    assert kws.count("date") == 1


def test_extract_keywords_includes_template_name():
    kws = extract_ticket_keywords(
        subject="format issue",
        template_name="Confirmation Invoice",
    )
    assert "confirmation" in kws
    assert "invoice" in kws


def test_extract_keywords_includes_workflow_name():
    kws = extract_ticket_keywords(
        subject="label wrong",
        workflow_name="Payment Reminder",
    )
    assert "payment" in kws
    assert "reminder" in kws


def test_extract_keywords_short_words_filtered():
    kws = extract_ticket_keywords(subject="it is ok so go")
    assert "it" not in kws
    assert "is" not in kws
    assert "ok" not in kws


# ── retrieve_relevant_kb_entries ───────────────────────────────────────────────


def test_retrieve_empty_db():
    db = _make_db()
    result = retrieve_relevant_kb_entries(db, subject="invoice")
    assert result == []


def test_retrieve_basic_title_match():
    db = _make_db()
    _insert(db, "Settings", "Invoice Date Format", "Controls the date format on invoices.")
    _insert(db, "Settings", "Unrelated Topic", "Nothing relevant here.")

    result = retrieve_relevant_kb_entries(db, subject="invoice date format")
    assert len(result) == 1
    assert result[0]["title"] == "Invoice Date Format"


def test_retrieve_score_title_higher_than_content():
    db = _make_db()
    id1 = _insert(db, "General", "Invoice Format Guide", "Some general info.")
    id2 = _insert(db, "General", "Unrelated Title", "You can configure the invoice format here.")

    result = retrieve_relevant_kb_entries(db, subject="invoice format")
    # id1 has title match (score +3 per keyword) so should rank higher
    assert result[0]["id"] == id1


def test_retrieve_template_name_boost():
    db = _make_db()
    id1 = _insert(db, "Template", "Confirmation Invoice settings", "Template-specific content.")
    id2 = _insert(db, "General", "Generic guide", "General advice only.")

    result = retrieve_relevant_kb_entries(
        db, subject="display issue", template_name="Confirmation Invoice"
    )
    assert any(r["id"] == id1 for r in result)
    if len(result) > 1:
        assert result[0]["id"] == id1


def test_retrieve_workflow_name_boost():
    db = _make_db()
    id1 = _insert(db, "Workflow", "Payment Reminder configuration", "Reminder-specific settings.")
    id2 = _insert(db, "General", "Something else", "Unrelated content.")

    result = retrieve_relevant_kb_entries(
        db, subject="label issue", workflow_name="Payment Reminder"
    )
    assert any(r["id"] == id1 for r in result)


def test_retrieve_limit_respected():
    db = _make_db()
    for i in range(15):
        _insert(db, "Settings", f"Invoice topic {i}", f"invoice content for entry {i}")

    result = retrieve_relevant_kb_entries(db, subject="invoice", limit=5)
    assert len(result) <= 5


def test_retrieve_no_match_returns_empty():
    db = _make_db()
    _insert(db, "Settings", "Unrelated Topic A", "Content about something else entirely.")
    _insert(db, "Settings", "Unrelated Topic B", "Also nothing useful.")

    # very specific subject with no overlap
    result = retrieve_relevant_kb_entries(db, subject="xyzzy quux frob")
    assert result == []


def test_retrieve_returns_evidence_type():
    db = _make_db()
    _insert(db, "Legal requirements", "Mandatory legal disclosure", "Required by law.")
    result = retrieve_relevant_kb_entries(db, subject="legal disclosure mandatory")
    assert len(result) >= 1
    assert result[0]["evidence_type"] == "legal_evidence"


def test_retrieve_workaround_evidence_type():
    db = _make_db()
    _insert(db, "Workaround guides", "Invoice workaround", "workaround for invoice format issue.")
    result = retrieve_relevant_kb_entries(db, subject="invoice format")
    assert any(r["evidence_type"] == "workaround_evidence" for r in result)


def test_retrieve_existing_setting_evidence_type():
    db = _make_db()
    _insert(db, "Configuration options", "Date format setting", "you can configure the date format.")
    result = retrieve_relevant_kb_entries(db, subject="date format")
    assert any(r["evidence_type"] == "existing_setting_evidence" for r in result)


def test_retrieve_matched_terms_populated():
    db = _make_db()
    _insert(db, "General", "Invoice Date Guide", "Helps with invoice date display.")
    result = retrieve_relevant_kb_entries(db, subject="invoice date")
    assert len(result) >= 1
    assert len(result[0]["matched_terms"]) > 0


def test_retrieve_defensive_on_bad_db():
    """retrieve_relevant_kb_entries should return [] when the DB has no table."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    result = retrieve_relevant_kb_entries(db, subject="anything")
    assert result == []


# ── summarize_kb_evidence ──────────────────────────────────────────────────────


def test_summarize_empty():
    assert summarize_kb_evidence([]) == ""


def test_summarize_header():
    entries = [
        {
            "title": "Invoice Setting",
            "content": "You can configure the invoice date.",
            "evidence_type": "existing_setting_evidence",
            "score": 5,
        }
    ]
    result = summarize_kb_evidence(entries)
    assert result.startswith("RELEVANT KB EVIDENCE:")


def test_summarize_contains_evidence_type_and_score():
    entries = [
        {
            "title": "Legal Disclosure",
            "content": "Required by law in France.",
            "evidence_type": "legal_evidence",
            "score": 8,
        }
    ]
    result = summarize_kb_evidence(entries)
    assert "legal_evidence" in result
    assert "score 8" in result
    assert "Legal Disclosure" in result


def test_summarize_content_snippet_truncated():
    long_content = "x" * 500
    entries = [
        {
            "title": "Long Entry",
            "content": long_content,
            "evidence_type": "general_evidence",
            "score": 3,
        }
    ]
    result = summarize_kb_evidence(entries)
    assert "..." in result


def test_summarize_respects_max_chars():
    entries = [
        {
            "title": f"Entry {i}",
            "content": "a" * 300,
            "evidence_type": "general_evidence",
            "score": 5 - i,
        }
        for i in range(20)
    ]
    result = summarize_kb_evidence(entries, max_chars=500)
    assert len(result) <= 600  # generous tolerance for header + line endings


def test_summarize_multiple_entries():
    entries = [
        {"title": "Entry A", "content": "First content.", "evidence_type": "legal_evidence", "score": 7},
        {"title": "Entry B", "content": "Second content.", "evidence_type": "workaround_evidence", "score": 4},
    ]
    result = summarize_kb_evidence(entries)
    assert "Entry A" in result
    assert "Entry B" in result


# ── derive_kb_evidence_signals ─────────────────────────────────────────────────


def test_derive_empty():
    result = derive_kb_evidence_signals([])
    assert result["has_legal_evidence"] is False
    assert result["has_workaround_evidence"] is False
    assert result["has_existing_setting_evidence"] is False
    assert result["has_product_evidence"] is False
    assert result["has_terminology_evidence"] is False
    assert result["kb_evidence_count"] == 0
    assert result["kb_evidence_types"] == []
    assert result["matched_terms"] == []


def test_derive_legal_evidence():
    entries = [{"evidence_type": "legal_evidence", "matched_terms": ["title:legal"]}]
    result = derive_kb_evidence_signals(entries)
    assert result["has_legal_evidence"] is True
    assert result["has_workaround_evidence"] is False


def test_derive_workaround_evidence():
    entries = [{"evidence_type": "workaround_evidence", "matched_terms": ["title:workaround"]}]
    result = derive_kb_evidence_signals(entries)
    assert result["has_workaround_evidence"] is True


def test_derive_existing_setting_evidence():
    entries = [{"evidence_type": "existing_setting_evidence", "matched_terms": []}]
    result = derive_kb_evidence_signals(entries)
    assert result["has_existing_setting_evidence"] is True


def test_derive_product_evidence():
    entries = [{"evidence_type": "product_evidence", "matched_terms": []}]
    result = derive_kb_evidence_signals(entries)
    assert result["has_product_evidence"] is True


def test_derive_terminology_evidence():
    entries = [{"evidence_type": "terminology_evidence", "matched_terms": []}]
    result = derive_kb_evidence_signals(entries)
    assert result["has_terminology_evidence"] is True


def test_derive_multiple_types():
    entries = [
        {"evidence_type": "legal_evidence", "matched_terms": ["title:legal"]},
        {"evidence_type": "workaround_evidence", "matched_terms": ["title:workaround"]},
    ]
    result = derive_kb_evidence_signals(entries)
    assert result["has_legal_evidence"] is True
    assert result["has_workaround_evidence"] is True
    assert result["kb_evidence_count"] == 2
    assert "legal_evidence" in result["kb_evidence_types"]
    assert "workaround_evidence" in result["kb_evidence_types"]


def test_derive_matched_terms_deduped():
    entries = [
        {"evidence_type": "legal_evidence", "matched_terms": ["title:legal", "title:invoice"]},
        {"evidence_type": "workaround_evidence", "matched_terms": ["title:legal", "title:workaround"]},
    ]
    result = derive_kb_evidence_signals(entries)
    # "title:legal" should appear only once
    assert result["matched_terms"].count("title:legal") == 1


def test_derive_kb_evidence_count():
    entries = [
        {"evidence_type": "legal_evidence", "matched_terms": []},
        {"evidence_type": "general_evidence", "matched_terms": []},
        {"evidence_type": "product_evidence", "matched_terms": []},
    ]
    result = derive_kb_evidence_signals(entries)
    assert result["kb_evidence_count"] == 3


# ── Integration: retrieve → derive → summarize ────────────────────────────────


def test_full_pipeline_legal():
    db = _make_db()
    _insert(
        db,
        "Legal requirements",
        "VAT mandatory disclosure",
        "Required by law to display VAT number on all invoices.",
    )

    entries = retrieve_relevant_kb_entries(db, subject="VAT invoice legal")
    assert len(entries) >= 1

    signals = derive_kb_evidence_signals(entries)
    assert signals["has_legal_evidence"] is True

    summary = summarize_kb_evidence(entries)
    assert "legal_evidence" in summary
    assert "VAT mandatory disclosure" in summary


def test_full_pipeline_workaround():
    db = _make_db()
    _insert(
        db,
        "Workaround guides",
        "Custom date format workaround",
        "There is a workaround: use a custom template variable.",
    )

    entries = retrieve_relevant_kb_entries(db, subject="date format custom")
    signals = derive_kb_evidence_signals(entries)
    assert signals["has_workaround_evidence"] is True

    summary = summarize_kb_evidence(entries)
    assert "workaround_evidence" in summary


def test_existing_solution_detector_uses_kb_signals():
    """KB workaround signal propagates into detect_existing_solution via evidence."""
    from ai.existing_solution_detector import detect_existing_solution

    evidence = {
        "kb_evidence_signals": {
            "has_workaround_evidence": True,
            "has_existing_setting_evidence": False,
        }
    }
    result = detect_existing_solution(
        ticket_summary="Can we change the date format on invoice?",
        evidence=evidence,
    )
    assert result["has_existing_solution"] is True
    assert result["solution_type"] == "existing_workaround"


def test_existing_solution_detector_uses_kb_setting_signal():
    """KB existing_setting signal propagates into detect_existing_solution via evidence."""
    from ai.existing_solution_detector import detect_existing_solution

    evidence = {
        "kb_evidence_signals": {
            "has_workaround_evidence": False,
            "has_existing_setting_evidence": True,
        }
    }
    result = detect_existing_solution(
        ticket_summary="We need a different date format",
        evidence=evidence,
    )
    assert result["has_existing_solution"] is True
    assert result["solution_type"] == "existing_setting"


def test_kb_signal_does_not_override_wrong_output_bug():
    """KB workaround signal must NOT fire when evidence_wrong_output is True (bug wins)."""
    from ai.existing_solution_detector import detect_existing_solution

    evidence = {
        "mentions_wrong_output": True,
        "kb_evidence_signals": {
            "has_workaround_evidence": True,
        },
    }
    result = detect_existing_solution(
        ticket_summary="The invoice total is displayed incorrectly.",
        evidence=evidence,
    )
    assert result["has_existing_solution"] is False
    assert result["solution_type"] == "no_existing_solution"


def test_legal_gate_kb_legal_boosts_confidence():
    """KB legal evidence should boost confidence in legal_preference_gate."""
    from ai.gates.legal_preference_gate import evaluate_legal_preference

    evidence = {
        "kb_evidence_signals": {"has_legal_evidence": True},
    }
    result = evaluate_legal_preference(
        ticket_summary="client wants different wording on document",
        evidence=evidence,
    )
    # KB legal evidence alone cannot set should_mention_law=True
    assert result["should_mention_law"] is False
    # But confidence should be ≥ 0.4 (nudge to 0.55)
    assert result["confidence"] >= 0.4


def test_legal_gate_kb_legal_never_sets_should_mention_law():
    """KB legal evidence alone must NEVER set should_mention_law=True."""
    from ai.gates.legal_preference_gate import evaluate_legal_preference

    evidence = {
        "mentions_legal_terms": True,
        "kb_evidence_signals": {"has_legal_evidence": True},
    }
    result = evaluate_legal_preference(
        ticket_summary="there is a legal requirement in the contract",
        evidence=evidence,
    )
    assert result["should_mention_law"] is False
