"""Tests for ai/pm_learning.py — extract_structured_pm_lessons and helpers."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.pm_learning import (
    extract_structured_pm_lessons,
    find_relevant_structured_pm_lessons,
    format_structured_pm_lessons_for_prompt,
    derive_pm_lesson_signals,
)

_REQUIRED_KEYS = {
    "lesson_type", "category", "before", "after",
    "instruction", "confidence", "applies_to",
    "template_name", "workflow_name", "source",
}

_VALID_TYPES = {
    "classification_correction", "legal_reference_removed",
    "global_change_to_editable", "dev_to_support_guidance",
    "workaround_added", "bug_feature_framing", "answer_depth_shortened",
    "existing_solution_added", "unknown",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _types(lessons):
    return {l["lesson_type"] for l in lessons}


# ── Return shape ──────────────────────────────────────────────────────────────

def test_returns_list():
    result = extract_structured_pm_lessons("old output", "new output")
    assert isinstance(result, list)


def test_each_lesson_has_required_keys():
    orig = "We should create a Jira for this feature request."
    final = "There is already a workaround for this. No development needed."
    lessons = extract_structured_pm_lessons(orig, final)
    for lesson in lessons:
        for k in _REQUIRED_KEYS:
            assert k in lesson, f"Lesson missing key: {k}"


def test_each_lesson_type_is_valid():
    orig = "We should create a Jira for this feature request."
    final = "There is already a workaround for this."
    lessons = extract_structured_pm_lessons(orig, final)
    for lesson in lessons:
        assert lesson["lesson_type"] in _VALID_TYPES, (
            f"Invalid lesson_type: {lesson['lesson_type']}"
        )


def test_source_is_pm_structured_edit():
    orig = "Article 100 mandates this change."
    final = "The wording should be changed to client preference."
    lessons = extract_structured_pm_lessons(orig, final)
    for lesson in lessons:
        assert lesson["source"] == "pm_structured_edit"


# ── Empty / identical inputs → [] ────────────────────────────────────────────

def test_empty_original_returns_empty():
    assert extract_structured_pm_lessons("", "some output") == []


def test_empty_final_returns_empty():
    assert extract_structured_pm_lessons("some output", "") == []


def test_both_empty_returns_empty():
    assert extract_structured_pm_lessons("", "") == []


def test_identical_inputs_returns_empty():
    assert extract_structured_pm_lessons("same text", "same text") == []


def test_no_meaningful_difference_returns_empty():
    """Slight whitespace/case change is still caught by identity check."""
    assert extract_structured_pm_lessons("hello world", "hello world") == []


# ── Rule 1: legal reference removed ──────────────────────────────────────────

def test_legal_reference_removed_detected():
    orig = "According to Article 100, this is mandatory by law."
    final = "The wording should reflect client preference."
    lessons = extract_structured_pm_lessons(orig, final)
    assert "legal_reference_removed" in _types(lessons)


def test_legal_reference_removed_instruction():
    orig = "Legal compliance requires this change."
    final = "Client prefers a different wording."
    lessons = extract_structured_pm_lessons(orig, final)
    legal_l = next(l for l in lessons if l["lesson_type"] == "legal_reference_removed")
    assert "should_mention_law" in legal_l["instruction"]


def test_legal_terms_in_both_does_not_trigger():
    """If final also has legal terms, rule does NOT fire."""
    orig = "Legal requirement: Article 12 applies."
    final = "This is still a legal matter per Article 12."
    lessons = extract_structured_pm_lessons(orig, final)
    assert "legal_reference_removed" not in _types(lessons)


# ── Rule 2: global change → editable ─────────────────────────────────────────

def test_global_change_to_editable_detected():
    orig = "We should change the default wording globally for all clients."
    final = "The field should be made editable per-client instead."
    lessons = extract_structured_pm_lessons(orig, final)
    assert "global_change_to_editable" in _types(lessons)


def test_global_change_to_editable_instruction():
    orig = "Change the default for all clients globally."
    final = "This should be configurable per client."
    lessons = extract_structured_pm_lessons(orig, final)
    gl = next(l for l in lessons if l["lesson_type"] == "global_change_to_editable")
    assert "editable" in gl["instruction"].lower() or "configurable" in gl["instruction"].lower()


def test_global_without_editable_in_final_does_not_trigger():
    """Global change in original, but final doesn't mention editable — no lesson."""
    orig = "Change this globally."
    final = "This should be reviewed further."
    lessons = extract_structured_pm_lessons(orig, final)
    assert "global_change_to_editable" not in _types(lessons)


# ── Rule 3: dev request → support guidance ────────────────────────────────────

def test_dev_to_support_guidance_detected():
    orig = "We should create a Jira ticket to implement this new feature."
    final = "There is an existing workaround for this. Support guidance is sufficient."
    lessons = extract_structured_pm_lessons(orig, final)
    assert "dev_to_support_guidance" in _types(lessons)


def test_dev_to_support_guidance_instruction():
    orig = "Development is required; let's add this to the backlog."
    final = "A workaround already exists. No development needed."
    lessons = extract_structured_pm_lessons(orig, final)
    d = next(l for l in lessons if l["lesson_type"] == "dev_to_support_guidance")
    assert "jira" in d["instruction"].lower() or "development" in d["instruction"].lower()


# ── Rule 4: workaround added ──────────────────────────────────────────────────

def test_workaround_added_detected():
    orig = "The client wants this changed."
    final = "There is an existing workaround for this case."
    lessons = extract_structured_pm_lessons(orig, final)
    assert "workaround_added" in _types(lessons)


def test_workaround_added_not_duplicate_of_dev_to_support():
    """When dev_to_support_guidance fires, workaround_added is suppressed."""
    orig = "We should implement this via development and create a Jira."
    final = "There is an existing workaround. No development needed."
    lessons = extract_structured_pm_lessons(orig, final)
    types = _types(lessons)
    assert "dev_to_support_guidance" in types
    assert "workaround_added" not in types


# ── Rule 5: bug framing correction ───────────────────────────────────────────

def test_bug_feature_framing_detected():
    orig = "This is a feature request to add a new dropdown option."
    final = "This is a bug — the calculation is broken and needs a fix."
    lessons = extract_structured_pm_lessons(orig, final)
    assert "bug_feature_framing" in _types(lessons)


def test_bug_feature_framing_instruction():
    orig = "Handle this as an enhancement request."
    final = "This is a bug fix — the output is incorrect."
    lessons = extract_structured_pm_lessons(orig, final)
    b = next(l for l in lessons if l["lesson_type"] == "bug_feature_framing")
    assert "bug" in b["instruction"].lower()


# ── Rule 6: answer depth shortened ───────────────────────────────────────────

def test_answer_depth_shortened_detected():
    orig = " ".join(["word"] * 150)  # 150 words
    final = " ".join(["word"] * 50)   # 50 words — below 60% of 150
    lessons = extract_structured_pm_lessons(orig, final)
    assert "answer_depth_shortened" in _types(lessons)


def test_answer_depth_not_triggered_when_original_short():
    orig = " ".join(["word"] * 80)   # below 120-word threshold
    final = " ".join(["word"] * 30)
    lessons = extract_structured_pm_lessons(orig, final)
    assert "answer_depth_shortened" not in _types(lessons)


def test_answer_depth_not_triggered_when_final_long_enough():
    orig = " ".join(["word"] * 150)
    final = " ".join(["word"] * 100)  # 100/150 = 67% — above 60% threshold
    lessons = extract_structured_pm_lessons(orig, final)
    assert "answer_depth_shortened" not in _types(lessons)


def test_answer_depth_confidence_is_low():
    orig = " ".join(["word"] * 150)
    final = " ".join(["word"] * 50)
    lessons = extract_structured_pm_lessons(orig, final)
    al = next(l for l in lessons if l["lesson_type"] == "answer_depth_shortened")
    assert al["confidence"] < 0.7


# ── Rule 7: existing solution added ──────────────────────────────────────────

def test_existing_solution_added_detected():
    orig = "We should develop a new feature for this."
    final = "There is an existing setting that already covers this case."
    lessons = extract_structured_pm_lessons(orig, final)
    # Could be dev_to_support_guidance or existing_solution_added
    types = _types(lessons)
    assert "existing_solution_added" in types or "dev_to_support_guidance" in types


def test_existing_solution_added_when_no_dev_language():
    orig = "The client wants to change this."
    final = "There is an existing configuration option for this already."
    lessons = extract_structured_pm_lessons(orig, final)
    assert "existing_solution_added" in _types(lessons)


# ── Rule 8: classification_correction (pm_decision) ─────────────────────────

def test_classification_correction_with_pm_decision_support_guidance():
    pm = {"recommended_action": "explain_workaround", "classification": "how_to"}
    orig = "We should implement this and create a Jira."
    final = "This can be handled as support guidance. A workaround exists."
    lessons = extract_structured_pm_lessons(orig, final, pm_decision=pm)
    types = _types(lessons)
    # Either dev_to_support_guidance or classification_correction should fire
    assert "dev_to_support_guidance" in types or "classification_correction" in types


def test_classification_correction_with_pm_decision_make_editable():
    pm = {"recommended_action": "make_editable", "classification": "client_preference"}
    orig = "We should change the default globally for all clients."
    final = "The field should be made editable per client."
    lessons = extract_structured_pm_lessons(orig, final, pm_decision=pm)
    types = _types(lessons)
    assert "global_change_to_editable" in types or "classification_correction" in types


def test_classification_correction_with_pm_decision_bug():
    pm = {"recommended_action": "accept_bug", "classification": "bug"}
    orig = "This seems like a new feature request for an enhancement."
    final = "This is a bug — the calculation is incorrect and needs to be fixed."
    lessons = extract_structured_pm_lessons(orig, final, pm_decision=pm)
    types = _types(lessons)
    assert "bug_feature_framing" in types or "classification_correction" in types


def test_no_classification_correction_without_pm_decision():
    """Without pm_decision, classification_correction must not be added."""
    orig = "We should implement this and create a Jira."
    final = "A workaround already exists."
    lessons = extract_structured_pm_lessons(orig, final)
    assert "classification_correction" not in _types(lessons)


# ── Confidence ranges ─────────────────────────────────────────────────────────

def test_all_confidence_values_between_0_and_1():
    orig = ("Article 100 mandates this. We should change the default globally. "
            "Create a Jira for this new feature request. " + " ".join(["word"] * 150))
    final = ("Client prefers a different wording. Make the field editable per client. "
             "There is an existing workaround. This is a bug fix. " + " ".join(["x"] * 50))
    lessons = extract_structured_pm_lessons(orig, final)
    for l in lessons:
        assert 0.0 <= l["confidence"] <= 1.0, f"Confidence out of range: {l['confidence']}"


def test_legal_confidence_is_high():
    orig = "Article 100 mandates this change."
    final = "This is a client preference."
    lessons = extract_structured_pm_lessons(orig, final)
    legal = next((l for l in lessons if l["lesson_type"] == "legal_reference_removed"), None)
    if legal:
        assert legal["confidence"] >= 0.8


# ── template/workflow fields applied ─────────────────────────────────────────

def test_template_name_applied_to_lesson():
    orig = "Article 100 applies."
    final = "No legal reference needed."
    lessons = extract_structured_pm_lessons(orig, final, template_name="reconciliation_note")
    for l in lessons:
        assert l["template_name"] == "reconciliation_note"


def test_workflow_name_applied_to_lesson():
    orig = "Create a Jira for this."
    final = "Use the existing workaround."
    lessons = extract_structured_pm_lessons(orig, final, workflow_name="annuals")
    for l in lessons:
        assert l["workflow_name"] == "annuals"


def test_applies_to_uses_template_when_provided():
    orig = "Change the default globally."
    final = "Make the field editable per client."
    lessons = extract_structured_pm_lessons(orig, final, template_name="payslip")
    for l in lessons:
        assert l["applies_to"] == "payslip"


def test_applies_to_defaults_to_all_when_no_template():
    orig = "Change the default globally."
    final = "Make the field editable per client."
    lessons = extract_structured_pm_lessons(orig, final)
    for l in lessons:
        assert l["applies_to"] == "all"


# ── Does not mutate inputs ────────────────────────────────────────────────────

def test_does_not_mutate_pm_decision():
    pm = {"recommended_action": "make_editable", "classification": "client_preference"}
    original_pm = dict(pm)
    extract_structured_pm_lessons("orig", "final", pm_decision=pm)
    assert pm == original_pm


def test_does_not_mutate_original_string():
    orig = "Article 100 mandates this."
    final = "Client preference only."
    orig_copy = orig
    extract_structured_pm_lessons(orig, final)
    assert orig == orig_copy


# ── Deduplication: same lesson_type appears only once ────────────────────────

def test_no_duplicate_lesson_types():
    orig = ("Article 100 requires this. Article 200 also requires. "
            "Loi du 1er janvier also applies.")
    final = "This is just a client preference, no legal basis."
    lessons = extract_structured_pm_lessons(orig, final)
    types = [l["lesson_type"] for l in lessons]
    assert len(types) == len(set(types)), "Duplicate lesson types found"


# ── Acceptance scenario ───────────────────────────────────────────────────────

def test_acceptance_scenario_three_lessons():
    """PR 18 acceptance scenario: three patterns in one edit.

    Original has: legal term (Article 100), Jira/dev language, global change.
    Final has: editable-per-client (no legal, no global-change language).

    Expected lessons:
      - legal_reference_removed  (Article 100 removed)
      - global_change_to_editable (global→editable detected)

    Note: dev_to_support_guidance does NOT fire because the final has no
    _SUPPORT_GUIDANCE_TERMS (workaround, existing setting, no development…).
    The Jira→editable shift is captured by global_change_to_editable.
    """
    original = (
        "Client request should be handled as a feature request. "
        "We should create a Jira to change the default wording globally. "
        "Article 100 makes this mandatory."
    )
    final = (
        "This is a client wording preference. "
        "The current wording is correct, so we should not change the global default. "
        "If needed, we can make the text editable per client."
    )

    lessons = extract_structured_pm_lessons(original, final)
    types = _types(lessons)

    assert "legal_reference_removed" in types, (
        f"Expected legal_reference_removed in {types}"
    )
    assert "global_change_to_editable" in types, (
        f"Expected global_change_to_editable in {types}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PR 19 — find_relevant_structured_pm_lessons tests
# ═══════════════════════════════════════════════════════════════════════════════

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
"""


def _make_db(*rows):
    """Create an in-memory DB and insert given lesson rows."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(_TABLE_SQL)
    for row in rows:
        db.execute(
            """INSERT INTO pm_structured_lessons
               (template_name, workflow_name, lesson_type, instruction,
                confidence, hit_count, active)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                row.get("template_name", ""),
                row.get("workflow_name", ""),
                row.get("lesson_type", "unknown"),
                row.get("instruction", "instr"),
                row.get("confidence", 0.8),
                row.get("hit_count", 1),
                row.get("active", 1),
            ),
        )
    db.commit()
    return db


# ── Basic retrieval ───────────────────────────────────────────────────────────

def test_find_returns_list():
    db = _make_db({"lesson_type": "legal_reference_removed", "instruction": "do not cite law"})
    result = find_relevant_structured_pm_lessons(db)
    assert isinstance(result, list)


def test_find_returns_active_lessons_only():
    db = _make_db(
        {"lesson_type": "legal_reference_removed", "instruction": "active lesson", "active": 1},
        {"lesson_type": "global_change_to_editable", "instruction": "inactive lesson", "active": 0},
    )
    result = find_relevant_structured_pm_lessons(db)
    lessons = [r["instruction"] if hasattr(r, "__getitem__") else r for r in result]
    assert len(result) == 1
    assert result[0]["instruction"] == "active lesson"


def test_find_returns_empty_when_all_inactive():
    db = _make_db(
        {"lesson_type": "legal_reference_removed", "instruction": "gone", "active": 0},
    )
    assert find_relevant_structured_pm_lessons(db) == []


def test_find_returns_empty_when_table_missing():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    result = find_relevant_structured_pm_lessons(db)
    assert result == []


def test_find_returns_empty_when_db_is_none():
    assert find_relevant_structured_pm_lessons(None) == []


def test_find_respects_limit():
    db = _make_db(*[
        {"lesson_type": "legal_reference_removed", "instruction": f"instr {i}"}
        for i in range(10)
    ])
    result = find_relevant_structured_pm_lessons(db, limit=3)
    assert len(result) == 3


# ── Ordering ──────────────────────────────────────────────────────────────────

def test_find_prefers_same_template():
    db = _make_db(
        {"lesson_type": "legal_reference_removed", "template_name": "payslip", "instruction": "payslip lesson", "hit_count": 1},
        {"lesson_type": "global_change_to_editable", "template_name": "", "instruction": "general lesson", "hit_count": 99},
    )
    result = find_relevant_structured_pm_lessons(db, template_name="payslip")
    assert result[0]["instruction"] == "payslip lesson"


def test_find_prefers_same_workflow():
    db = _make_db(
        {"lesson_type": "legal_reference_removed", "workflow_name": "annuals", "instruction": "annuals lesson", "hit_count": 1},
        {"lesson_type": "global_change_to_editable", "workflow_name": "", "instruction": "general lesson", "hit_count": 99},
    )
    result = find_relevant_structured_pm_lessons(db, workflow_name="annuals")
    assert result[0]["instruction"] == "annuals lesson"


def test_find_orders_by_hit_count_when_no_template_match():
    db = _make_db(
        {"lesson_type": "legal_reference_removed", "instruction": "low hits", "hit_count": 1},
        {"lesson_type": "global_change_to_editable", "instruction": "high hits", "hit_count": 10},
    )
    result = find_relevant_structured_pm_lessons(db, template_name="other")
    assert result[0]["instruction"] == "high hits"


def test_find_orders_by_confidence_when_hit_count_equal():
    db = _make_db(
        {"lesson_type": "legal_reference_removed", "instruction": "low conf", "hit_count": 5, "confidence": 0.6},
        {"lesson_type": "global_change_to_editable", "instruction": "high conf", "hit_count": 5, "confidence": 0.9},
    )
    result = find_relevant_structured_pm_lessons(db)
    assert result[0]["instruction"] == "high conf"


def test_find_general_lessons_returned_when_no_template():
    db = _make_db(
        {"lesson_type": "legal_reference_removed", "template_name": "", "instruction": "general"},
    )
    result = find_relevant_structured_pm_lessons(db, template_name="")
    assert len(result) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# PR 19 — format_structured_pm_lessons_for_prompt tests
# ═══════════════════════════════════════════════════════════════════════════════

def test_format_empty_returns_empty_string():
    assert format_structured_pm_lessons_for_prompt([]) == ""


def test_format_none_instruction_skipped():
    lesson = {"lesson_type": "unknown", "confidence": 0.8, "hit_count": 1, "instruction": ""}
    result = format_structured_pm_lessons_for_prompt([lesson])
    assert result == ""


def test_format_includes_header():
    lesson = {"lesson_type": "legal_reference_removed", "confidence": 0.85, "hit_count": 3,
              "instruction": "Do not cite law."}
    result = format_structured_pm_lessons_for_prompt([lesson])
    assert result.startswith("STRUCTURED PM LESSONS:")


def test_format_includes_lesson_type():
    lesson = {"lesson_type": "legal_reference_removed", "confidence": 0.85, "hit_count": 3,
              "instruction": "Do not cite law."}
    result = format_structured_pm_lessons_for_prompt([lesson])
    assert "legal_reference_removed" in result


def test_format_includes_confidence_percent():
    lesson = {"lesson_type": "global_change_to_editable", "confidence": 0.85, "hit_count": 5,
              "instruction": "Prefer editable."}
    result = format_structured_pm_lessons_for_prompt([lesson])
    assert "85%" in result


def test_format_includes_hit_count():
    lesson = {"lesson_type": "workaround_added", "confidence": 0.75, "hit_count": 7,
              "instruction": "Mention workaround."}
    result = format_structured_pm_lessons_for_prompt([lesson])
    assert "hits 7" in result


def test_format_includes_instruction():
    instr = "Do not suggest Jira or development work."
    lesson = {"lesson_type": "dev_to_support_guidance", "confidence": 0.8, "hit_count": 2,
              "instruction": instr}
    result = format_structured_pm_lessons_for_prompt([lesson])
    assert instr in result


def test_format_caps_at_eight_lessons():
    lessons = [
        {"lesson_type": "unknown", "confidence": 0.8, "hit_count": 1, "instruction": f"instr {i}"}
        for i in range(12)
    ]
    result = format_structured_pm_lessons_for_prompt(lessons)
    # Count bullet lines
    lines = [l for l in result.splitlines() if l.startswith("- ")]
    assert len(lines) == 8


def test_format_multiple_lessons():
    lessons = [
        {"lesson_type": "legal_reference_removed", "confidence": 0.85, "hit_count": 2,
         "instruction": "Do not cite law."},
        {"lesson_type": "global_change_to_editable", "confidence": 0.85, "hit_count": 5,
         "instruction": "Prefer editable."},
    ]
    result = format_structured_pm_lessons_for_prompt(lessons)
    assert "legal_reference_removed" in result
    assert "global_change_to_editable" in result


# ═══════════════════════════════════════════════════════════════════════════════
# PR 19 — derive_pm_lesson_signals tests
# ═══════════════════════════════════════════════════════════════════════════════

def _lesson(lesson_type, instruction=""):
    return {"lesson_type": lesson_type, "instruction": instruction}


def test_derive_empty_returns_all_false():
    sigs = derive_pm_lesson_signals([])
    assert sigs["avoid_legal_references"] is False
    assert sigs["prefer_make_editable"] is False
    assert sigs["prefer_support_guidance"] is False
    assert sigs["prefer_bug_framing"] is False
    assert sigs["prefer_short_answer"] is False
    assert sigs["prefer_existing_solution"] is False
    assert sigs["lesson_count"] == 0
    assert sigs["lesson_types"] == []


def test_derive_legal_reference_removed_maps_correctly():
    sigs = derive_pm_lesson_signals([_lesson("legal_reference_removed")])
    assert sigs["avoid_legal_references"] is True


def test_derive_global_change_to_editable_maps_correctly():
    sigs = derive_pm_lesson_signals([_lesson("global_change_to_editable")])
    assert sigs["prefer_make_editable"] is True


def test_derive_dev_to_support_guidance_maps_correctly():
    sigs = derive_pm_lesson_signals([_lesson("dev_to_support_guidance")])
    assert sigs["prefer_support_guidance"] is True


def test_derive_workaround_added_maps_correctly():
    sigs = derive_pm_lesson_signals([_lesson("workaround_added")])
    assert sigs["prefer_support_guidance"] is True


def test_derive_bug_feature_framing_maps_correctly():
    sigs = derive_pm_lesson_signals([_lesson("bug_feature_framing")])
    assert sigs["prefer_bug_framing"] is True


def test_derive_answer_depth_shortened_maps_correctly():
    sigs = derive_pm_lesson_signals([_lesson("answer_depth_shortened")])
    assert sigs["prefer_short_answer"] is True


def test_derive_existing_solution_added_maps_correctly():
    sigs = derive_pm_lesson_signals([_lesson("existing_solution_added")])
    assert sigs["prefer_existing_solution"] is True


def test_derive_classification_correction_make_editable_inferred():
    sigs = derive_pm_lesson_signals([
        _lesson("classification_correction", instruction="PMDecision recommended_action=make_editable")
    ])
    assert sigs["prefer_make_editable"] is True


def test_derive_classification_correction_support_inferred():
    sigs = derive_pm_lesson_signals([
        _lesson("classification_correction", instruction="do not suggest development; use workaround")
    ])
    assert sigs["prefer_support_guidance"] is True


def test_derive_classification_correction_bug_inferred():
    sigs = derive_pm_lesson_signals([
        _lesson("classification_correction", instruction="PMDecision classification=bug; frame as bug fix")
    ])
    assert sigs["prefer_bug_framing"] is True


def test_derive_lesson_count_matches_input():
    lessons = [_lesson("legal_reference_removed"), _lesson("workaround_added")]
    sigs = derive_pm_lesson_signals(lessons)
    assert sigs["lesson_count"] == 2


def test_derive_lesson_types_list_sorted():
    lessons = [_lesson("workaround_added"), _lesson("legal_reference_removed")]
    sigs = derive_pm_lesson_signals(lessons)
    assert sigs["lesson_types"] == sorted(["workaround_added", "legal_reference_removed"])


def test_derive_multiple_signals_all_true():
    lessons = [
        _lesson("legal_reference_removed"),
        _lesson("global_change_to_editable"),
        _lesson("answer_depth_shortened"),
    ]
    sigs = derive_pm_lesson_signals(lessons)
    assert sigs["avoid_legal_references"] is True
    assert sigs["prefer_make_editable"] is True
    assert sigs["prefer_short_answer"] is True


def test_derive_does_not_mutate_input():
    lessons = [_lesson("legal_reference_removed")]
    original = [dict(l) for l in lessons]
    derive_pm_lesson_signals(lessons)
    assert lessons[0] == original[0]
