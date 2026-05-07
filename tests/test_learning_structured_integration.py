"""Integration tests for structured PM lesson extraction inside run_learning."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents import AgentOrchestrator

# ── In-memory DB factory ──────────────────────────────────────────────────────

_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS agent_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name TEXT,
    ticket_id INTEGER,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    duration_ms INTEGER DEFAULT 0,
    success INTEGER DEFAULT 1,
    error TEXT,
    estimated_cost REAL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER,
    lesson TEXT,
    category TEXT,
    importance TEXT DEFAULT 'medium',
    template_name TEXT,
    workflow_name TEXT,
    applies_to TEXT,
    rating INTEGER DEFAULT 0,
    active INTEGER DEFAULT 1,
    source_ticket_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS pm_structured_lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_ticket_id INTEGER,
    template_name TEXT DEFAULT '',
    workflow_name TEXT DEFAULT '',
    lesson_type TEXT NOT NULL,
    category TEXT DEFAULT '',
    before TEXT DEFAULT '',
    after TEXT DEFAULT '',
    instruction TEXT NOT NULL,
    confidence REAL DEFAULT 0,
    applies_to TEXT DEFAULT 'all',
    source TEXT DEFAULT 'pm_structured_edit',
    active INTEGER DEFAULT 1,
    hit_count INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_reinforced_at TEXT DEFAULT ''
);
"""


def _make_db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(_TABLES_SQL)
    return db


def _make_orchestrator(db):
    orch = AgentOrchestrator.__new__(AgentOrchestrator)
    orch.db = db
    orch.client = MagicMock()
    orch.llm_router = None
    orch._agent_log = []
    orch._batch_kb_cache = {}
    return orch


# ── run_learning stores structured lessons on meaningful edit ─────────────────

def test_run_learning_stores_structured_lesson_on_legal_edit():
    db = _make_db()
    orch = _make_orchestrator(db)

    orig = "According to Article 100, this is mandatory by law."
    final = "The wording should reflect client preference."

    # Patch learning_agent so no real API call is made
    with patch("agents.learning_agent", return_value=([], {"input_tokens": 0, "output_tokens": 0, "model": "test"})):
        orch.run_learning(1, "Test Ticket", "", "", orig, final)

    rows = db.execute("SELECT * FROM pm_structured_lessons").fetchall()
    assert len(rows) >= 1
    types = {r["lesson_type"] for r in rows}
    assert "legal_reference_removed" in types


def test_run_learning_stores_dev_to_support_lesson():
    db = _make_db()
    orch = _make_orchestrator(db)

    orig = "We should create a Jira ticket to implement this new feature."
    final = "There is an existing workaround for this. Support guidance is sufficient."

    with patch("agents.learning_agent", return_value=([], {"input_tokens": 0, "output_tokens": 0, "model": "test"})):
        orch.run_learning(2, "Dev ticket", "", "", orig, final)

    rows = db.execute("SELECT * FROM pm_structured_lessons").fetchall()
    types = {r["lesson_type"] for r in rows}
    assert "dev_to_support_guidance" in types


def test_run_learning_stores_global_change_lesson():
    db = _make_db()
    orch = _make_orchestrator(db)

    orig = "We should change the default wording globally for all clients."
    final = "The field should be made editable per-client instead."

    with patch("agents.learning_agent", return_value=([], {"input_tokens": 0, "output_tokens": 0, "model": "test"})):
        orch.run_learning(3, "Global ticket", "", "", orig, final)

    rows = db.execute("SELECT * FROM pm_structured_lessons").fetchall()
    types = {r["lesson_type"] for r in rows}
    assert "global_change_to_editable" in types


def test_run_learning_passes_template_and_workflow_to_lessons():
    db = _make_db()
    orch = _make_orchestrator(db)

    orig = "Article 100 mandates this change."
    final = "Client preference only."

    with patch("agents.learning_agent", return_value=([], {"input_tokens": 0, "output_tokens": 0, "model": "test"})):
        orch.run_learning(4, "Ticket", "payslip", "annuals", orig, final)

    rows = db.execute("SELECT * FROM pm_structured_lessons").fetchall()
    assert len(rows) >= 1
    for row in rows:
        assert row["template_name"] == "payslip"
        assert row["workflow_name"] == "annuals"


# ── Structured extraction failure does not break run_learning ─────────────────

def test_structured_extraction_failure_does_not_break_run_learning():
    """If extract_structured_pm_lessons raises, run_learning still returns LLM result."""
    db = _make_db()
    orch = _make_orchestrator(db)

    orig = "Article 100 mandates this."
    final = "Client preference."

    fake_llm_result = [{"lesson": "some llm lesson", "category": "general"}]

    with patch("agents.learning_agent", return_value=(fake_llm_result, {"input_tokens": 0, "output_tokens": 0, "model": "test"})):
        with patch("ai.pm_learning.extract_structured_pm_lessons", side_effect=RuntimeError("boom")):
            result = orch.run_learning(5, "Ticket", "", "", orig, final)

    # run_learning should return the LLM result regardless
    assert result == fake_llm_result


def test_structured_upsert_failure_does_not_break_run_learning():
    """If upsert_structured_pm_lesson raises, run_learning still returns normally."""
    db = _make_db()
    orch = _make_orchestrator(db)

    orig = "Article 100 mandates this."
    final = "Client preference."

    with patch("agents.learning_agent", return_value=([], {"input_tokens": 0, "output_tokens": 0, "model": "test"})):
        with patch("ai.pm_learning.upsert_structured_pm_lesson", side_effect=RuntimeError("db exploded")):
            result = orch.run_learning(6, "Ticket", "", "", orig, final)

    # Should still return without raising
    assert isinstance(result, list)


# ── No structured lesson when no meaningful change ────────────────────────────

def test_no_structured_lessons_when_no_meaningful_change():
    """should_learn returns False for identical outputs → run_learning returns [] early."""
    db = _make_db()
    orch = _make_orchestrator(db)

    same = "The client wants to change this."
    result = orch.run_learning(7, "Ticket", "", "", same, same)

    assert result == []
    count = db.execute("SELECT COUNT(*) FROM pm_structured_lessons").fetchone()[0]
    assert count == 0


def test_no_structured_lessons_when_empty_inputs():
    db = _make_db()
    orch = _make_orchestrator(db)

    result = orch.run_learning(8, "Ticket", "", "", "", "some output")

    assert result == []
    count = db.execute("SELECT COUNT(*) FROM pm_structured_lessons").fetchone()[0]
    assert count == 0


# ── Deduplication across multiple run_learning calls ─────────────────────────

def test_duplicate_lesson_increments_hit_count():
    """Same edit twice → hit_count=2, not two separate rows."""
    db = _make_db()
    orch = _make_orchestrator(db)

    orig = "Article 100 mandates this change."
    final = "Client preference only."

    with patch("agents.learning_agent", return_value=([], {"input_tokens": 0, "output_tokens": 0, "model": "test"})):
        orch.run_learning(9, "T1", "", "", orig, final)
        orch.run_learning(10, "T2", "", "", orig, final)

    rows = db.execute(
        "SELECT hit_count FROM pm_structured_lessons WHERE lesson_type = 'legal_reference_removed'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["hit_count"] == 2


# ── LLM failure still allows structured extraction ───────────────────────────

def test_structured_extraction_runs_even_when_llm_fails():
    """If learning_agent raises, structured extraction still runs."""
    db = _make_db()
    orch = _make_orchestrator(db)

    orig = "We should create a Jira for this feature request."
    final = "There is an existing workaround. No development needed."

    with patch("agents.learning_agent", side_effect=Exception("API down")):
        result = orch.run_learning(11, "T", "", "", orig, final)

    # LLM failed so result is []
    assert result == []

    # But structured lessons were still extracted
    count = db.execute("SELECT COUNT(*) FROM pm_structured_lessons").fetchone()[0]
    assert count >= 1


def test_run_learning_returns_llm_result_alongside_structured():
    """Structured extraction is additive — LLM result still returned."""
    db = _make_db()
    orch = _make_orchestrator(db)

    orig = "Article 100 mandates this."
    final = "Client preference."

    llm_lessons = [{"lesson": "llm lesson", "category": "legal"}]

    with patch("agents.learning_agent", return_value=(llm_lessons, {"input_tokens": 5, "output_tokens": 5, "model": "test"})):
        result = orch.run_learning(12, "Ticket", "", "", orig, final)

    assert result == llm_lessons
    # Also structured lessons stored
    count = db.execute("SELECT COUNT(*) FROM pm_structured_lessons").fetchone()[0]
    assert count >= 1


# ── No DB — graceful return ───────────────────────────────────────────────────

def test_run_learning_returns_empty_when_no_db():
    orch = _make_orchestrator(None)
    result = orch.run_learning(1, "T", "", "", "orig", "final changed significantly")
    assert result == []
