"""Tests for ai/pm_context.build_pm_prompt_block."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.pm_context import build_pm_prompt_block


# ── Empty / None inputs ───────────────────────────────────────────────────────

def test_empty_decision_no_regen_returns_empty():
    assert build_pm_prompt_block(None) == ""


def test_empty_dict_no_regen_returns_empty():
    assert build_pm_prompt_block({}) == ""


def test_none_decision_empty_regen_returns_empty():
    assert build_pm_prompt_block(None, regeneration_instruction="") == ""


def test_whitespace_regen_only_returns_empty():
    assert build_pm_prompt_block(None, regeneration_instruction="   ") == ""


# ── Regeneration instruction appears first ────────────────────────────────────

def test_regen_instruction_before_drafting_instructions():
    result = build_pm_prompt_block(
        {"decision": "make_editable"},
        regeneration_instruction="PM REGENERATION INSTRUCTIONS:\nCorrect X.",
    )
    regen_pos = result.index("PM REGENERATION INSTRUCTIONS:")
    draft_pos = result.index("PM DRAFTING INSTRUCTIONS")
    assert regen_pos < draft_pos, "regeneration block must come before drafting instructions"


def test_regen_instruction_before_decision_constraints():
    result = build_pm_prompt_block(
        {"decision": "make_editable"},
        regeneration_instruction="PM REGENERATION INSTRUCTIONS:\nCorrect X.",
    )
    regen_pos = result.index("PM REGENERATION INSTRUCTIONS:")
    ctx_pos = result.index("PM DECISION CONSTRAINTS")
    assert regen_pos < ctx_pos, "regeneration block must come before decision constraints"


# ── Drafting instructions appear second ──────────────────────────────────────

def test_drafting_instructions_before_decision_constraints():
    result = build_pm_prompt_block({"decision": "make_editable"})
    draft_pos = result.index("PM DRAFTING INSTRUCTIONS")
    ctx_pos = result.index("PM DECISION CONSTRAINTS")
    assert draft_pos < ctx_pos, "drafting instructions must come before decision constraints"


# ── Content checks ────────────────────────────────────────────────────────────

def test_pm_drafting_instructions_present():
    result = build_pm_prompt_block({"decision": "make_editable"})
    assert "PM DRAFTING INSTRUCTIONS" in result


def test_pm_decision_constraints_present():
    result = build_pm_prompt_block({"decision": "make_editable"})
    assert "PM DECISION CONSTRAINTS" in result


def test_regen_instruction_present_in_output():
    regen = "PM REGENERATION INSTRUCTIONS:\n- Fix legal references."
    result = build_pm_prompt_block({"decision": "make_editable"}, regeneration_instruction=regen)
    assert "Fix legal references." in result


def test_regen_only_no_decision():
    result = build_pm_prompt_block(None, regeneration_instruction="REGEN BLOCK")
    assert "REGEN BLOCK" in result
    assert "PM DRAFTING INSTRUCTIONS" not in result
    assert "PM DECISION CONSTRAINTS" not in result


# ── make_editable scenario ────────────────────────────────────────────────────

def test_make_editable_includes_editability_instruction():
    result = build_pm_prompt_block({"recommended_action": "make_editable"})
    assert "editable" in result.lower()


def test_make_editable_includes_decision_constraints():
    result = build_pm_prompt_block({"recommended_action": "make_editable"})
    assert "PM DECISION CONSTRAINTS" in result


# ── Blank-line separation ─────────────────────────────────────────────────────

def test_sections_separated_by_blank_line():
    regen = "REGEN_MARKER"
    result = build_pm_prompt_block({"decision": "make_editable"}, regeneration_instruction=regen)
    # Sections are joined with "\n\n"
    assert "\n\n" in result


# ── Does not mutate pm_decision ───────────────────────────────────────────────

def test_does_not_mutate_pm_decision():
    pm = {"decision": "make_editable", "recommended_action": "make_editable"}
    original = dict(pm)
    build_pm_prompt_block(pm)
    assert pm == original


# ── Acceptance: full scenario ─────────────────────────────────────────────────

def test_acceptance_make_editable_full_block():
    """make_editable decision → all three sections present in correct order."""
    pm_decision = {
        "decision": "make_editable",
        "recommended_action": "make_editable",
        "answer_depth": "short",
        "max_words": 80,
        "should_mention_law": False,
        "global_change_risk": "high",
        "needs_prd": False,
    }
    regen = (
        "PM REGENERATION INSTRUCTIONS:\n"
        "- [editability_missing] Explicitly mention editable.\n"
        "\nRegenerate the draft respecting these corrections. "
        "Do not mention PM guard warnings to the client."
    )

    result = build_pm_prompt_block(pm_decision, regeneration_instruction=regen)

    # All three sections present
    assert "PM REGENERATION INSTRUCTIONS:" in result
    assert "PM DRAFTING INSTRUCTIONS" in result
    assert "PM DECISION CONSTRAINTS" in result

    # Ordering
    assert result.index("PM REGENERATION INSTRUCTIONS:") \
        < result.index("PM DRAFTING INSTRUCTIONS") \
        < result.index("PM DECISION CONSTRAINTS")

    # Key content
    assert "editable" in result.lower()
    assert "make_editable=80" not in result  # sanity: not garbled
