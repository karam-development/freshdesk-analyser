"""Tests for ai/pm_analysis_guard.apply_pm_analysis_guard."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.pm_analysis_guard import apply_pm_analysis_guard


_DEC_MAKE_EDITABLE = {
    "recommended_action": "make_editable",
    "should_mention_law": False,
    "global_change_risk": "high",
    "needs_prd": False,
    "answer_depth": "short",
    "max_words": 100,
}

_DEC_EMPTY = {}


# ── Clean / empty input ───────────────────────────────────────────────────────

def test_empty_output_returns_unchanged():
    out, warnings = apply_pm_analysis_guard("", _DEC_MAKE_EDITABLE)
    assert out == ""
    assert warnings == []


def test_none_output_returns_none():
    out, warnings = apply_pm_analysis_guard(None, _DEC_MAKE_EDITABLE)
    assert out is None
    assert warnings == []


def test_empty_pm_decision_returns_unchanged():
    out, warnings = apply_pm_analysis_guard("Some analysis.", _DEC_EMPTY)
    assert out == "Some analysis."
    assert warnings == []


def test_none_pm_decision_returns_unchanged():
    out, warnings = apply_pm_analysis_guard("Some analysis.", None)
    assert out == "Some analysis."
    assert warnings == []


def test_clean_output_returns_unchanged():
    clean = "The field can be made configurable per client as needed."
    out, warnings = apply_pm_analysis_guard(clean, _DEC_MAKE_EDITABLE)
    assert warnings == [], f"Expected no warnings for clean output, got: {warnings}"
    assert out == clean


# ── PRD heading guard ─────────────────────────────────────────────────────────

def test_prd_heading_triggers_warning_when_needs_prd_false():
    output = "Objective: Change the wording globally.\nUser Story: As a user..."
    _, warnings = apply_pm_analysis_guard(output, {"needs_prd": False})
    codes = [w for w in warnings if "PRD-style" in w]
    assert len(codes) >= 1


def test_prd_heading_no_warning_when_needs_prd_true():
    output = "Objective: Change the wording globally."
    _, warnings = apply_pm_analysis_guard(output, {"needs_prd": True})
    prd_warnings = [w for w in warnings if "PRD-style" in w]
    assert prd_warnings == []


def test_prd_heading_no_warning_when_needs_prd_not_set():
    output = "Objective: Change the wording globally."
    _, warnings = apply_pm_analysis_guard(output, {"recommended_action": "make_editable"})
    prd_warnings = [w for w in warnings if "PRD-style" in w]
    assert prd_warnings == []


# ── Legal reference guard ─────────────────────────────────────────────────────

def test_legal_reference_triggers_warning_when_should_mention_law_false():
    output = "Article 12 of the law requires this change."
    _, warnings = apply_pm_analysis_guard(output, {"should_mention_law": False})
    legal_warnings = [w for w in warnings if "legal reference" in w]
    assert len(legal_warnings) >= 1


def test_legal_reference_no_warning_when_should_mention_law_true():
    output = "Article 12 of the law requires this change."
    _, warnings = apply_pm_analysis_guard(output, {"should_mention_law": True})
    legal_warnings = [w for w in warnings if "legal reference" in w]
    assert legal_warnings == []


def test_law_of_pattern_triggers_legal_warning():
    output = "The Law of 1915 governs this."
    _, warnings = apply_pm_analysis_guard(output, {"should_mention_law": False})
    legal_warnings = [w for w in warnings if "legal reference" in w]
    assert len(legal_warnings) >= 1


# ── Global default guard ──────────────────────────────────────────────────────

def test_global_default_phrase_triggers_warning_when_high_risk():
    output = "We should change the default globally for all clients."
    _, warnings = apply_pm_analysis_guard(output, {"global_change_risk": "high"})
    global_warnings = [w for w in warnings if "global default change" in w]
    assert len(global_warnings) >= 1


def test_global_default_no_warning_when_risk_not_high():
    output = "We should change the default globally for all clients."
    _, warnings = apply_pm_analysis_guard(output, {"global_change_risk": "low"})
    global_warnings = [w for w in warnings if "global default change" in w]
    assert global_warnings == []


# ── Editability guard ─────────────────────────────────────────────────────────

def test_missing_editability_triggers_warning_when_make_editable():
    output = "The field works correctly."
    _, warnings = apply_pm_analysis_guard(output, {"recommended_action": "make_editable"})
    edit_warnings = [w for w in warnings if "editability" in w]
    assert len(edit_warnings) >= 1


def test_editability_present_no_warning():
    output = "The field can be made configurable per client."
    _, warnings = apply_pm_analysis_guard(output, {"recommended_action": "make_editable"})
    edit_warnings = [w for w in warnings if "editability" in w]
    assert edit_warnings == []


def test_editable_word_satisfies_editability_guard():
    output = "The text is editable for each client."
    _, warnings = apply_pm_analysis_guard(output, {"recommended_action": "make_editable"})
    edit_warnings = [w for w in warnings if "editability" in w]
    assert edit_warnings == []


def test_no_editability_warning_when_action_is_not_make_editable():
    output = "The field works correctly."
    _, warnings = apply_pm_analysis_guard(output, {"recommended_action": "support_guidance"})
    edit_warnings = [w for w in warnings if "editability" in w]
    assert edit_warnings == []


# ── Output length guard ───────────────────────────────────────────────────────

def test_long_output_triggers_warning_for_short_answer_depth():
    # max_words=10, output is 25 words → > 10*2 = 20 → triggers
    long_output = " ".join(["word"] * 25)
    _, warnings = apply_pm_analysis_guard(
        long_output, {"answer_depth": "short", "max_words": 10}
    )
    length_warnings = [w for w in warnings if "longer than recommended" in w]
    assert len(length_warnings) >= 1


def test_short_output_no_length_warning():
    short_output = "Brief analysis here."
    _, warnings = apply_pm_analysis_guard(
        short_output, {"answer_depth": "short", "max_words": 100}
    )
    length_warnings = [w for w in warnings if "longer than recommended" in w]
    assert length_warnings == []


def test_no_length_warning_when_answer_depth_not_short():
    long_output = " ".join(["word"] * 500)
    _, warnings = apply_pm_analysis_guard(
        long_output, {"answer_depth": "detailed", "max_words": 10}
    )
    length_warnings = [w for w in warnings if "longer than recommended" in w]
    assert length_warnings == []


# ── Return structure ──────────────────────────────────────────────────────────

def test_guarded_output_contains_marker_when_violation():
    output = "Article 12 of the law requires this."
    guarded, _ = apply_pm_analysis_guard(output, {"should_mention_law": False})
    assert "[PM analysis guard:" in guarded


def test_no_mutation_when_no_violations():
    clean = "The field can be made configurable per client."
    guarded, warnings = apply_pm_analysis_guard(clean, _DEC_MAKE_EDITABLE)
    assert guarded == clean
    assert warnings == []


def test_warnings_are_strings():
    output = "Article 12 of the law requires this."
    _, warnings = apply_pm_analysis_guard(output, {"should_mention_law": False})
    assert all(isinstance(w, str) for w in warnings)


# ── Acceptance scenario ───────────────────────────────────────────────────────

def test_acceptance_full_violation_scenario():
    """PMDecision: make_editable, no law, high global risk, no PRD.
    Input: 'Objective: change the default globally. Article 100 requires this.'
    Expected: PRD, legal, global-default, editability warnings all present.
    """
    pm_decision = {
        "decision": "make_editable",
        "classification": "client_preference",
        "complexity": "simple",
        "answer_depth": "short",
        "max_words": 200,
        "needs_prd": False,
        "should_mention_law": False,
        "global_change_risk": "high",
        "recommended_action": "make_editable",
    }
    output = "Objective: change the default globally. Article 100 requires this."

    guarded, warnings = apply_pm_analysis_guard(output, pm_decision)

    warning_text = " ".join(warnings)
    assert "PRD-style" in warning_text, f"Expected PRD warning, got: {warnings}"
    assert "legal reference" in warning_text, f"Expected legal warning, got: {warnings}"
    assert "global default change" in warning_text, f"Expected global warning, got: {warnings}"
    assert "editability" in warning_text, f"Expected editability warning, got: {warnings}"
    assert "[PM analysis guard:" in guarded
