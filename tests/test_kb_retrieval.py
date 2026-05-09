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


# ══════════════════════════════════════════════════════════════════════════════
# PR 22 — Improved scoring and filtering tests
# ══════════════════════════════════════════════════════════════════════════════


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_db22():
    """In-memory DB with knowledge_base table for PR 22 tests."""
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


def _ins22(db, category, title, content):
    cur = db.execute(
        "INSERT INTO knowledge_base (category, title, content) VALUES (?, ?, ?)",
        (category, title, content),
    )
    db.commit()
    return cur.lastrowid


# ── Keyword extraction: new generic stopwords ─────────────────────────────────


def test_keywords_issue_is_filtered():
    kws = extract_ticket_keywords(subject="there is an issue with the invoice")
    assert "issue" not in kws


def test_keywords_problem_is_filtered():
    kws = extract_ticket_keywords(subject="problem with the date format")
    assert "problem" not in kws


def test_keywords_client_is_filtered():
    kws = extract_ticket_keywords(subject="client wants different wording")
    assert "client" not in kws


def test_keywords_customer_is_filtered():
    kws = extract_ticket_keywords(subject="customer request for change")
    assert "customer" not in kws


def test_keywords_request_is_filtered():
    kws = extract_ticket_keywords(subject="request for invoice change")
    assert "request" not in kws


def test_keywords_display_is_filtered():
    kws = extract_ticket_keywords(subject="display the invoice amount differently")
    assert "display" not in kws


def test_keywords_show_is_filtered():
    kws = extract_ticket_keywords(subject="show different text in the note")
    assert "show" not in kws
    assert "note" not in kws


def test_keywords_wrong_is_filtered():
    kws = extract_ticket_keywords(subject="wrong wording on the invoice")
    assert "wrong" not in kws


def test_keywords_need_needs_filtered():
    kws = extract_ticket_keywords(subject="we need a different format")
    assert "need" not in kws
    assert "needs" not in kws


def test_keywords_want_wants_filtered():
    kws = extract_ticket_keywords(subject="they want the invoice to show VAT")
    assert "want" not in kws
    assert "wants" not in kws


def test_keywords_template_generic_filtered():
    kws = extract_ticket_keywords(subject="template is showing wrong label")
    assert "template" not in kws


def test_keywords_change_changes_filtered():
    kws = extract_ticket_keywords(subject="request changes to the invoice format")
    assert "change" not in kws
    assert "changes" not in kws


# ── Keyword extraction: meaningful domain terms preserved ─────────────────────


def test_keywords_invoice_preserved():
    kws = extract_ticket_keywords(subject="invoice date format wrong")
    assert "invoice" in kws


def test_keywords_vat_preserved():
    kws = extract_ticket_keywords(subject="VAT disclosure on invoice")
    assert "vat" in kws


def test_keywords_legal_preserved():
    kws = extract_ticket_keywords(subject="legal requirement for disclosure")
    assert "legal" in kws


def test_keywords_workaround_preserved():
    kws = extract_ticket_keywords(subject="is there a workaround available")
    assert "workaround" in kws


def test_keywords_wording_preserved():
    kws = extract_ticket_keywords(subject="custom wording for staff cost")
    assert "wording" in kws
    assert "custom" in kws


# ── Keyword extraction: template/workflow phrases preserved ───────────────────


def test_keywords_template_phrase_preserved():
    kws = extract_ticket_keywords(subject="", template_name="Staff Cost")
    assert "staff cost" in kws


def test_keywords_workflow_phrase_preserved():
    kws = extract_ticket_keywords(subject="", workflow_name="Payment Reminder")
    assert "payment reminder" in kws


def test_keywords_template_individual_tokens_also_added():
    kws = extract_ticket_keywords(subject="", template_name="Confirmation Invoice")
    assert "confirmation" in kws
    assert "invoice" in kws
    assert "confirmation invoice" in kws


def test_keywords_dedup_preserves_order():
    kws = extract_ticket_keywords(
        subject="staff cost wording",
        template_name="Staff Cost",
    )
    # "staff" and "cost" from subject appear before the template phrase
    staff_idx = kws.index("staff")
    phrase_idx = kws.index("staff cost")
    assert staff_idx < phrase_idx


# ── Scoring: title beats content ──────────────────────────────────────────────


def test_pr22_title_match_beats_content_only():
    db = _make_db22()
    id1 = _ins22(db, "General", "Invoice Format Guide", "Some general info.")
    id2 = _ins22(db, "General", "Unrelated Title", "You can configure the invoice format here.")

    result = retrieve_relevant_kb_entries(db, subject="invoice format")
    # id1 (title matches) should rank above id2 (content-only)
    assert len(result) >= 1
    assert result[0]["id"] == id1


def test_pr22_content_only_single_match_filtered_by_min_score():
    db = _make_db22()
    _ins22(db, "General", "Unrelated Title", "The invoice is processed monthly.")

    # "invoice" in content only → +1, below default min_score=3 → filtered
    result = retrieve_relevant_kb_entries(db, subject="invoice", min_score=3.0)
    assert result == []


def test_pr22_two_content_matches_still_filtered():
    db = _make_db22()
    _ins22(db, "General", "Unrelated",
           "The invoice format is set during configuration.")

    # "invoice" +1 "format" +1 → score 2, below min_score=3 → filtered
    result = retrieve_relevant_kb_entries(
        db, subject="invoice format", min_score=3.0
    )
    assert result == []


def test_pr22_three_content_matches_pass_min_score():
    db = _make_db22()
    _ins22(db, "General", "Unrelated",
           "The invoice date format is configurable.")

    # "invoice" +1 "date" +1 "format" +1 → score 3 = min_score → passes
    result = retrieve_relevant_kb_entries(
        db, subject="invoice date format", min_score=3.0
    )
    assert len(result) >= 1


def test_pr22_min_score_zero_returns_all_positive():
    db = _make_db22()
    _ins22(db, "General", "Unrelated", "The invoice is processed.")

    # With min_score=0, even single content match is returned
    result = retrieve_relevant_kb_entries(
        db, subject="invoice", min_score=0.0
    )
    assert len(result) >= 1


# ── Scoring: category keyword match ──────────────────────────────────────────


def test_pr22_category_match_contributes():
    db = _make_db22()
    id1 = _ins22(db, "Invoice settings", "Unrelated title", "Content.")
    id2 = _ins22(db, "General", "Unrelated title too", "Content.")

    result = retrieve_relevant_kb_entries(db, subject="invoice", min_score=0.0)
    # id1 has category match (+3), id2 has no match → id1 should rank higher
    assert len(result) >= 1
    assert result[0]["id"] == id1


def test_pr22_category_match_score_reason():
    db = _make_db22()
    _ins22(db, "Invoice configuration", "Some title", "Content.")

    result = retrieve_relevant_kb_entries(db, subject="invoice", min_score=0.0)
    assert len(result) >= 1
    reasons = result[0]["score_reasons"]
    assert any("category:invoice" in r for r in reasons)


# ── Scoring: template phrase boost ───────────────────────────────────────────


def test_pr22_template_phrase_strong_boost():
    db = _make_db22()
    id1 = _ins22(db, "Templates", "Staff Cost configuration",
                  "Settings for the staff cost template.")
    id2 = _ins22(db, "General", "Generic note", "Some unrelated content.")

    result = retrieve_relevant_kb_entries(
        db, subject="wording issue", template_name="Staff Cost"
    )
    assert any(r["id"] == id1 for r in result)
    entry = next(r for r in result if r["id"] == id1)
    assert any("template_phrase" in r for r in entry["score_reasons"])
    # Template phrase should give +5
    assert entry["score"] >= 5


def test_pr22_workflow_phrase_boost():
    db = _make_db22()
    id1 = _ins22(db, "Workflows", "Payment Reminder setup", "How to configure reminders.")

    result = retrieve_relevant_kb_entries(
        db, subject="configuration", workflow_name="Payment Reminder"
    )
    assert any(r["id"] == id1 for r in result)
    entry = next(r for r in result if r["id"] == id1)
    assert any("workflow_phrase" in r for r in entry["score_reasons"])


# ── Scoring: workaround/setting context boost ─────────────────────────────────


def test_pr22_workaround_boost_when_ticket_has_workaround_context():
    db = _make_db22()
    _ins22(db, "workaround", "Staff cost workaround",
           "Use the editable field instead.")

    # Ticket explicitly mentions "workaround"
    result = retrieve_relevant_kb_entries(
        db, subject="staff workaround available", template_name="Staff Cost"
    )
    assert len(result) >= 1
    entry = result[0]
    assert any("workaround_context" in r for r in entry["score_reasons"])
    assert entry["evidence_type"] == "workaround_evidence"


def test_pr22_workaround_boost_when_ticket_has_custom_wording():
    db = _make_db22()
    _ins22(db, "workaround", "Staff cost wording workaround",
           "Use the editable text field.")

    result = retrieve_relevant_kb_entries(
        db, subject="client wants custom wording in staff cost",
        template_name="Staff Cost",
    )
    assert len(result) >= 1
    entry = result[0]
    assert any("workaround_context" in r for r in entry["score_reasons"])


def test_pr22_workaround_boost_absent_without_context():
    db = _make_db22()
    _ins22(db, "workaround", "Staff cost workaround", "Use the editable field.")

    # Ticket has NO workaround context words
    result = retrieve_relevant_kb_entries(
        db, subject="staff cost", template_name="Staff Cost", min_score=0.0
    )
    if result:
        entry = result[0]
        assert not any("workaround_context" in r for r in entry["score_reasons"])


# ── Scoring: legal evidence conservative behaviour ────────────────────────────


def test_pr22_legal_entry_filtered_without_legal_ticket_context():
    db = _make_db22()
    _ins22(db, "legal", "Invoice VAT legal disclosure",
           "Required by law to display VAT number on invoices.")

    # Ticket is about staff cost wording — no legal terms at all
    result = retrieve_relevant_kb_entries(
        db,
        subject="client wants custom wording in staff cost",
        template_name="Staff Cost",
        min_score=3.0,
    )
    ids = [r["id"] for r in result]
    # Legal invoice entry should NOT appear — no match AND legal penalty
    assert 1 not in ids or all(r["evidence_type"] != "legal_evidence" for r in result)


def test_pr22_legal_entry_ranks_high_when_ticket_has_legal_terms():
    db = _make_db22()
    _ins22(db, "Legal requirements", "VAT mandatory disclosure",
           "Required by law to display VAT number.")

    result = retrieve_relevant_kb_entries(
        db, subject="VAT legal mandatory disclosure", min_score=3.0
    )
    assert len(result) >= 1
    assert result[0]["evidence_type"] == "legal_evidence"
    assert any("legal_context" in r for r in result[0]["score_reasons"])


def test_pr22_legal_entry_penalty_applied_in_score_reasons():
    db = _make_db22()
    _ins22(db, "legal", "Invoice VAT disclosure", "Required by law.")

    # Subject has "invoice" → title match (+4) - legal penalty (-2) = 2 < min_score
    # So it's filtered; use min_score=0 to see the penalty
    result = retrieve_relevant_kb_entries(
        db, subject="invoice format", min_score=0.0
    )
    assert len(result) >= 1
    reasons = result[0]["score_reasons"]
    assert any("legal_no_context_penalty" in r for r in reasons)


def test_pr22_generic_invoice_ticket_does_not_surface_legal_entry():
    """Core PR 22 goal: generic invoice ticket must not promote legal KB entries."""
    db = _make_db22()
    _ins22(db, "legal", "Invoice VAT legal disclosure",
           "Required by law to display VAT number on invoices.")
    _ins22(db, "Configuration", "Invoice date format setting",
           "You can configure the date format.")

    result = retrieve_relevant_kb_entries(
        db, subject="invoice date format wrong", min_score=3.0
    )
    # Legal entry should not appear at all, or rank below setting entry
    legal_entries = [r for r in result if r["evidence_type"] == "legal_evidence"]
    setting_entries = [r for r in result if r["evidence_type"] == "existing_setting_evidence"]
    if legal_entries and setting_entries:
        assert setting_entries[0]["score"] >= legal_entries[0]["score"]


# ── Evidence type classification ──────────────────────────────────────────────


def test_pr22_existing_setting_content_detected():
    db = _make_db22()
    _ins22(db, "General", "Date setting",
           "The date format is configurable via the settings panel.")

    result = retrieve_relevant_kb_entries(db, subject="date format", min_score=0.0)
    assert any(r["evidence_type"] == "existing_setting_evidence" for r in result)


def test_pr22_workaround_content_detected():
    db = _make_db22()
    _ins22(db, "General", "Date format",
           "There is a workaround: use a custom template variable.")

    result = retrieve_relevant_kb_entries(db, subject="date format", min_score=0.0)
    assert any(r["evidence_type"] == "workaround_evidence" for r in result)


def test_pr22_product_content_detected():
    db = _make_db22()
    _ins22(db, "General", "Staff cost field",
           "This is the current behaviour by design and product standard.")

    result = retrieve_relevant_kb_entries(db, subject="staff cost", min_score=0.0)
    assert any(r["evidence_type"] == "product_evidence" for r in result)


def test_pr22_legal_requires_strong_content_terms():
    db = _make_db22()
    # "must" alone should NOT classify as legal (removed weak terms)
    _ins22(db, "General", "Invoice note",
           "Must include the invoice number in the header.")

    result = retrieve_relevant_kb_entries(db, subject="invoice", min_score=0.0)
    # Without strong legal terms, should not be legal_evidence
    if result:
        assert result[0]["evidence_type"] != "legal_evidence"


def test_pr22_existing_setting_priority_over_workaround():
    """When both setting and workaround signals present: setting wins (new priority)."""
    from ai.kb_retrieval import _classify_evidence_type
    # Category has "configuration" (setting) and content has "workaround"
    result = _classify_evidence_type(
        category="configuration guides",
        content="there is a workaround: use the configuration option.",
    )
    assert result == "existing_setting_evidence"


def test_pr22_legal_priority_over_existing_setting():
    from ai.kb_retrieval import _classify_evidence_type
    result = _classify_evidence_type(
        category="legal configuration",
        content="required by law to display this.",
    )
    assert result == "legal_evidence"


# ── score_reasons metadata ────────────────────────────────────────────────────


def test_pr22_score_reasons_present_in_matched_entries():
    db = _make_db22()
    _ins22(db, "Settings", "Invoice Date Format", "Controls the date format.")

    result = retrieve_relevant_kb_entries(db, subject="invoice date format")
    assert len(result) >= 1
    assert "score_reasons" in result[0]
    assert isinstance(result[0]["score_reasons"], list)
    assert len(result[0]["score_reasons"]) > 0


def test_pr22_score_reasons_title_annotation():
    db = _make_db22()
    _ins22(db, "General", "Staff Cost guide", "About staff costs.")

    result = retrieve_relevant_kb_entries(db, subject="staff cost")
    assert len(result) >= 1
    reasons = result[0]["score_reasons"]
    assert any("+4" in r for r in reasons)


def test_pr22_score_reasons_template_phrase_annotation():
    db = _make_db22()
    _ins22(db, "Templates", "Staff Cost settings", "Specific settings.")

    result = retrieve_relevant_kb_entries(
        db, subject="wording", template_name="Staff Cost"
    )
    assert len(result) >= 1
    reasons = result[0]["score_reasons"]
    assert any("template_phrase" in r for r in reasons)


# ── summarize_kb_evidence: backward-compatible with score_reasons ─────────────


def test_pr22_summarize_works_with_score_reasons_key():
    entries = [
        {
            "title": "Staff workaround",
            "content": "Use the editable field.",
            "evidence_type": "workaround_evidence",
            "score": 12,
            "matched_terms": ["title:staff"],
            "score_reasons": ["title:staff +4", "template_phrase:match +5"],
        }
    ]
    result = summarize_kb_evidence(entries)
    assert "RELEVANT KB EVIDENCE:" in result
    assert "Staff workaround" in result


# ── derive_kb_evidence_signals: unaffected by score_reasons ──────────────────


def test_pr22_derive_signals_unaffected_by_score_reasons():
    entries = [
        {
            "evidence_type": "workaround_evidence",
            "matched_terms": ["title:staff"],
            "score_reasons": ["title:staff +4"],
        }
    ]
    result = derive_kb_evidence_signals(entries)
    assert result["has_workaround_evidence"] is True
    assert result["kb_evidence_count"] == 1


# ── Full acceptance scenario ──────────────────────────────────────────────────


def test_pr22_acceptance_scenario():
    """
    KB entries:
      1. Workaround for staff cost wording (workaround category)
      2. Invoice VAT legal disclosure (legal category)

    Ticket: "Client wants custom wording in staff cost note"
    Template: "Staff Cost"

    Expected:
      - Workaround entry ranked above legal entry (or legal filtered entirely)
      - has_workaround_evidence=True
      - has_legal_evidence=False (legal entry filtered)
    """
    db = _make_db22()
    id_wa = _ins22(
        db, "workaround",
        "Existing workaround for staff cost wording",
        "Use the editable text field instead of changing the global default.",
    )
    id_lg = _ins22(
        db, "legal",
        "Invoice VAT legal disclosure",
        "Required by law to display VAT number on invoices.",
    )

    entries = retrieve_relevant_kb_entries(
        db,
        subject="Client wants custom wording in staff cost note",
        template_name="Staff Cost",
        min_score=3.0,
    )

    # Workaround entry must be present
    assert any(r["id"] == id_wa for r in entries), "Workaround entry missing from results"

    # Workaround entry must rank first (or legal must be absent)
    if any(r["id"] == id_lg for r in entries):
        wa_score = next(r["score"] for r in entries if r["id"] == id_wa)
        lg_score = next(r["score"] for r in entries if r["id"] == id_lg)
        assert wa_score > lg_score, "Workaround should rank above legal entry"
    else:
        pass  # Legal filtered entirely — ideal case

    signals = derive_kb_evidence_signals(entries)
    assert signals["has_workaround_evidence"] is True
    assert signals["has_legal_evidence"] is False

    summary = summarize_kb_evidence(entries)
    assert "RELEVANT KB EVIDENCE:" in summary
    assert "workaround" in summary.lower()
