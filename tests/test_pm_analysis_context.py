"""Tests for ai/pm_analysis_context.build_pm_analysis_prompt_block."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.pm_analysis_context import build_pm_analysis_prompt_block


# ── Empty / None inputs ───────────────────────────────────────────────────────

def test_empty_decision_returns_empty():
    assert build_pm_analysis_prompt_block(None) == ""


def test_empty_dict_returns_empty():
    assert build_pm_analysis_prompt_block({}) == ""


# ── Content checks ────────────────────────────────────────────────────────────

def test_includes_pm_analysis_instructions():
    result = build_pm_analysis_prompt_block({"decision": "make_editable"})
    assert "PM ANALYSIS INSTRUCTIONS:" in result


def test_includes_pm_decision_constraints():
    result = build_pm_analysis_prompt_block({"decision": "make_editable"})
    assert "PM DECISION CONSTRAINTS" in result


# ── Ordering: analysis instructions before decision constraints ───────────────

def test_analysis_instructions_before_decision_constraints():
    result = build_pm_analysis_prompt_block({"decision": "make_editable"})
    instr_pos = result.index("PM ANALYSIS INSTRUCTIONS:")
    ctx_pos = result.index("PM DECISION CONSTRAINTS")
    assert instr_pos < ctx_pos, \
        "PM ANALYSIS INSTRUCTIONS must come before PM DECISION CONSTRAINTS"


# ── Sections separated by blank line ─────────────────────────────────────────

def test_sections_separated_by_blank_line():
    result = build_pm_analysis_prompt_block({"decision": "make_editable"})
    assert "\n\n" in result


# ── Does not mutate pm_decision ───────────────────────────────────────────────

def test_does_not_mutate_pm_decision():
    pm = {"decision": "make_editable", "needs_prd": False}
    original = dict(pm)
    build_pm_analysis_prompt_block(pm)
    assert pm == original


# ── Acceptance: full make_editable decision ───────────────────────────────────

def test_acceptance_make_editable_full_block():
    pm_decision = {
        "decision": "make_editable",
        "classification": "client_preference",
        "answer_depth": "short",
        "max_words": 200,
        "needs_prd": False,
        "should_mention_law": False,
        "global_change_risk": "high",
        "recommended_action": "make_editable",
    }

    result = build_pm_analysis_prompt_block(pm_decision)

    assert "PM ANALYSIS INSTRUCTIONS:" in result
    assert "PM DECISION CONSTRAINTS" in result

    instr_pos = result.index("PM ANALYSIS INSTRUCTIONS:")
    ctx_pos = result.index("PM DECISION CONSTRAINTS")
    assert instr_pos < ctx_pos

    assert "short_client_preference_analysis" in result
    assert "editable" in result.lower() or "configurable" in result.lower()
