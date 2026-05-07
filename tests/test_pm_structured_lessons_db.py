"""Tests for upsert_structured_pm_lesson() with in-memory SQLite."""
import sys
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.pm_learning import upsert_structured_pm_lesson

# ── Schema helper ─────────────────────────────────────────────────────────────

_TABLE_SQL = """
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
CREATE INDEX IF NOT EXISTS idx_pm_struct_lesson_type ON pm_structured_lessons(lesson_type);
CREATE INDEX IF NOT EXISTS idx_pm_struct_template ON pm_structured_lessons(template_name);
CREATE INDEX IF NOT EXISTS idx_pm_struct_active ON pm_structured_lessons(active);
"""


def _make_db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(_TABLE_SQL)
    return db


def _sample_lesson(**overrides):
    base = {
        "lesson_type": "legal_reference_removed",
        "category": "legal",
        "before": "Article 100 says this is mandatory.",
        "after": "Client prefers different wording.",
        "instruction": (
            "Do not cite law or legal obligation unless PMDecision says "
            "should_mention_law=true or evidence explicitly supports it."
        ),
        "confidence": 0.85,
        "applies_to": "all",
        "template_name": "",
        "workflow_name": "",
        "source": "pm_structured_edit",
    }
    base.update(overrides)
    return base


# ── Table creation ────────────────────────────────────────────────────────────

def test_table_created():
    db = _make_db()
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "pm_structured_lessons" in tables


def test_table_has_expected_columns():
    db = _make_db()
    cols = {row[1] for row in db.execute("PRAGMA table_info(pm_structured_lessons)").fetchall()}
    for expected in (
        "id", "source_ticket_id", "template_name", "workflow_name",
        "lesson_type", "category", "before", "after", "instruction",
        "confidence", "applies_to", "source", "active", "hit_count",
        "created_at", "last_reinforced_at",
    ):
        assert expected in cols, f"Missing column: {expected}"


def test_active_column_default_is_1():
    db = _make_db()
    lesson = _sample_lesson()
    lesson_id, _ = upsert_structured_pm_lesson(db, 1, lesson)
    row = db.execute("SELECT active FROM pm_structured_lessons WHERE id = ?", (lesson_id,)).fetchone()
    assert row["active"] == 1


def test_indexes_created():
    db = _make_db()
    indexes = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
    assert "idx_pm_struct_lesson_type" in indexes
    assert "idx_pm_struct_template" in indexes
    assert "idx_pm_struct_active" in indexes


# ── Insert new lesson ─────────────────────────────────────────────────────────

def test_insert_returns_id_and_not_duplicate():
    db = _make_db()
    lesson = _sample_lesson()
    lesson_id, was_dup = upsert_structured_pm_lesson(db, 42, lesson)
    assert lesson_id is not None
    assert was_dup is False


def test_insert_persists_row():
    db = _make_db()
    lesson = _sample_lesson()
    lesson_id, _ = upsert_structured_pm_lesson(db, 42, lesson)
    row = db.execute("SELECT * FROM pm_structured_lessons WHERE id = ?", (lesson_id,)).fetchone()
    assert row is not None
    assert row["lesson_type"] == "legal_reference_removed"
    assert row["source_ticket_id"] == 42


def test_insert_stores_all_fields():
    db = _make_db()
    lesson = _sample_lesson(
        template_name="reconciliation_note",
        workflow_name="annuals",
        confidence=0.9,
        applies_to="reconciliation_note",
    )
    lesson_id, _ = upsert_structured_pm_lesson(db, 7, lesson)
    row = db.execute("SELECT * FROM pm_structured_lessons WHERE id = ?", (lesson_id,)).fetchone()
    assert row["template_name"] == "reconciliation_note"
    assert row["workflow_name"] == "annuals"
    assert abs(row["confidence"] - 0.9) < 0.001
    assert row["applies_to"] == "reconciliation_note"


def test_insert_sets_hit_count_to_1():
    db = _make_db()
    lesson = _sample_lesson()
    lesson_id, _ = upsert_structured_pm_lesson(db, 1, lesson)
    row = db.execute("SELECT hit_count FROM pm_structured_lessons WHERE id = ?", (lesson_id,)).fetchone()
    assert row["hit_count"] == 1


def test_insert_sets_source_pm_structured_edit():
    db = _make_db()
    lesson = _sample_lesson()
    lesson_id, _ = upsert_structured_pm_lesson(db, 1, lesson)
    row = db.execute("SELECT source FROM pm_structured_lessons WHERE id = ?", (lesson_id,)).fetchone()
    assert row["source"] == "pm_structured_edit"


# ── Duplicate detection ───────────────────────────────────────────────────────

def test_duplicate_returns_was_duplicate_true():
    db = _make_db()
    lesson = _sample_lesson()
    upsert_structured_pm_lesson(db, 1, lesson)
    _, was_dup = upsert_structured_pm_lesson(db, 2, lesson)
    assert was_dup is True


def test_duplicate_does_not_insert_new_row():
    db = _make_db()
    lesson = _sample_lesson()
    upsert_structured_pm_lesson(db, 1, lesson)
    upsert_structured_pm_lesson(db, 2, lesson)
    count = db.execute("SELECT COUNT(*) FROM pm_structured_lessons").fetchone()[0]
    assert count == 1


def test_duplicate_increments_hit_count():
    db = _make_db()
    lesson = _sample_lesson()
    lesson_id, _ = upsert_structured_pm_lesson(db, 1, lesson)
    upsert_structured_pm_lesson(db, 2, lesson)
    row = db.execute("SELECT hit_count FROM pm_structured_lessons WHERE id = ?", (lesson_id,)).fetchone()
    assert row["hit_count"] == 2


def test_duplicate_increments_hit_count_multiple_times():
    db = _make_db()
    lesson = _sample_lesson()
    lesson_id, _ = upsert_structured_pm_lesson(db, 1, lesson)
    for _ in range(4):
        upsert_structured_pm_lesson(db, 1, lesson)
    row = db.execute("SELECT hit_count FROM pm_structured_lessons WHERE id = ?", (lesson_id,)).fetchone()
    assert row["hit_count"] == 5


def test_duplicate_returns_original_id():
    db = _make_db()
    lesson = _sample_lesson()
    first_id, _ = upsert_structured_pm_lesson(db, 1, lesson)
    second_id, _ = upsert_structured_pm_lesson(db, 2, lesson)
    assert first_id == second_id


# ── Different template → separate row ────────────────────────────────────────

def test_different_template_inserts_separate_row():
    db = _make_db()
    lesson_a = _sample_lesson(template_name="payslip")
    lesson_b = _sample_lesson(template_name="reconciliation_note")
    id_a, dup_a = upsert_structured_pm_lesson(db, 1, lesson_a)
    id_b, dup_b = upsert_structured_pm_lesson(db, 2, lesson_b)
    assert id_a != id_b
    assert dup_a is False
    assert dup_b is False
    count = db.execute("SELECT COUNT(*) FROM pm_structured_lessons").fetchone()[0]
    assert count == 2


def test_different_workflow_inserts_separate_row():
    db = _make_db()
    lesson_a = _sample_lesson(workflow_name="annuals")
    lesson_b = _sample_lesson(workflow_name="monthlies")
    id_a, _ = upsert_structured_pm_lesson(db, 1, lesson_a)
    id_b, _ = upsert_structured_pm_lesson(db, 2, lesson_b)
    assert id_a != id_b


def test_different_instruction_inserts_separate_row():
    db = _make_db()
    lesson_a = _sample_lesson(instruction="instruction A")
    lesson_b = _sample_lesson(instruction="instruction B")
    id_a, _ = upsert_structured_pm_lesson(db, 1, lesson_a)
    id_b, _ = upsert_structured_pm_lesson(db, 2, lesson_b)
    assert id_a != id_b


def test_different_lesson_type_inserts_separate_row():
    db = _make_db()
    lesson_a = _sample_lesson(lesson_type="legal_reference_removed")
    lesson_b = _sample_lesson(lesson_type="workaround_added")
    id_a, _ = upsert_structured_pm_lesson(db, 1, lesson_a)
    id_b, _ = upsert_structured_pm_lesson(db, 2, lesson_b)
    assert id_a != id_b


# ── Defensive handling ────────────────────────────────────────────────────────

def test_does_not_crash_on_missing_optional_fields():
    db = _make_db()
    lesson = {"lesson_type": "unknown", "instruction": "some instruction"}
    lesson_id, was_dup = upsert_structured_pm_lesson(db, None, lesson)
    assert lesson_id is not None
    assert was_dup is False


def test_returns_none_false_on_bad_db():
    """Passing None as db should not raise — returns (None, False) defensively."""
    lesson = _sample_lesson()
    result = upsert_structured_pm_lesson(None, 1, lesson)
    assert result == (None, False)


def test_does_not_crash_on_none_ticket_id():
    db = _make_db()
    lesson = _sample_lesson()
    lesson_id, was_dup = upsert_structured_pm_lesson(db, None, lesson)
    assert lesson_id is not None


def test_does_not_mutate_lesson_dict():
    db = _make_db()
    lesson = _sample_lesson()
    original = dict(lesson)
    upsert_structured_pm_lesson(db, 1, lesson)
    assert lesson == original


def test_lesson_type_defaults_to_unknown_when_missing():
    db = _make_db()
    lesson = {"instruction": "test"}
    lesson_id, _ = upsert_structured_pm_lesson(db, 1, lesson)
    row = db.execute("SELECT lesson_type FROM pm_structured_lessons WHERE id = ?", (lesson_id,)).fetchone()
    assert row["lesson_type"] == "unknown"
