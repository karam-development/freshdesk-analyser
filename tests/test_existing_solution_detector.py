"""Tests for ai/existing_solution_detector.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.existing_solution_detector import detect_existing_solution


# ── Helpers ───────────────────────────────────────────────────────────────────

_REQUIRED_KEYS = {
    "has_existing_solution", "solution_type", "recommended_action",
    "confidence", "reason", "sources", "signals",
}

_VALID_SOLUTION_TYPES = {
    "existing_setting", "existing_workaround", "existing_template_pattern",
    "make_editable", "no_existing_solution", "unclear",
}

_VALID_RECOMMENDED_ACTIONS = {
    "explain_existing_setting", "explain_workaround",
    "reference_existing_template_pattern", "make_editable", "continue_analysis",
}


def _ev(**kwargs) -> dict:
    """Shorthand evidence builder."""
    return kwargs


# ── Return shape ─────────────────────────────────────────────────────────────

def test_returns_all_required_keys():
    result = detect_existing_solution()
    for k in _REQUIRED_KEYS:
        assert k in result, f"Missing key: {k}"


def test_solution_type_is_valid():
    result = detect_existing_solution()
    assert result["solution_type"] in _VALID_SOLUTION_TYPES


def test_recommended_action_is_valid():
    result = detect_existing_solution()
    assert result["recommended_action"] in _VALID_RECOMMENDED_ACTIONS


def test_confidence_is_float_between_0_and_1():
    result = detect_existing_solution()
    assert 0.0 <= result["confidence"] <= 1.0


def test_signals_is_dict():
    result = detect_existing_solution()
    assert isinstance(result["signals"], dict)


def test_sources_is_list():
    result = detect_existing_solution()
    assert isinstance(result["sources"], list)


# ── Empty / None inputs ───────────────────────────────────────────────────────

def test_no_inputs_returns_unclear():
    result = detect_existing_solution()
    assert result["solution_type"] == "unclear"
    assert result["has_existing_solution"] is False
    assert result["recommended_action"] == "continue_analysis"


def test_empty_strings_returns_unclear():
    result = detect_existing_solution(
        ticket_summary="", current_behaviour="",
        evidence={}, kb_brief="", code_brief="", research_brief=""
    )
    assert result["solution_type"] == "unclear"


# ── Priority 0: wrong output → no_existing_solution ─────────────────────────

def test_wrong_output_evidence_returns_no_existing_solution():
    result = detect_existing_solution(
        evidence=_ev(mentions_wrong_output=True)
    )
    assert result["solution_type"] == "no_existing_solution"
    assert result["has_existing_solution"] is False
    assert result["recommended_action"] == "continue_analysis"


def test_wrong_output_beats_workaround_evidence():
    """wrong_output (priority 0) wins over workaround (priority 1)."""
    result = detect_existing_solution(
        evidence=_ev(mentions_wrong_output=True, mentions_existing_workaround=True)
    )
    assert result["solution_type"] == "no_existing_solution"


# ── Priority 1: evidence workaround → existing_workaround ────────────────────

def test_evidence_workaround_returns_existing_workaround():
    result = detect_existing_solution(
        evidence=_ev(mentions_existing_workaround=True)
    )
    assert result["solution_type"] == "existing_workaround"
    assert result["has_existing_solution"] is True
    assert result["recommended_action"] == "explain_workaround"


def test_evidence_workaround_has_high_confidence():
    result = detect_existing_solution(
        evidence=_ev(mentions_existing_workaround=True)
    )
    assert result["confidence"] >= 0.8


def test_evidence_workaround_beats_context_setting():
    """Evidence workaround (priority 1) beats context existing_setting (priority 2)."""
    result = detect_existing_solution(
        evidence=_ev(mentions_existing_workaround=True),
        kb_brief="There is an existing setting you can configure.",
    )
    assert result["solution_type"] == "existing_workaround"


# ── Priority 2: context existing setting ─────────────────────────────────────

def test_kb_with_existing_setting_returns_existing_setting():
    result = detect_existing_solution(
        kb_brief="You can configure this via the existing setting in the admin panel."
    )
    assert result["solution_type"] == "existing_setting"
    assert result["has_existing_solution"] is True
    assert result["recommended_action"] == "explain_existing_setting"


def test_code_brief_with_configuration_option():
    result = detect_existing_solution(
        code_brief="The template has a configuration option that allows per-client customisation."
    )
    assert result["solution_type"] == "existing_setting"
    assert result["recommended_action"] == "explain_existing_setting"


def test_research_brief_with_already_available():
    result = detect_existing_solution(
        research_brief="This feature is already available via the settings menu."
    )
    assert result["solution_type"] == "existing_setting"


# ── Priority 3: context workaround ───────────────────────────────────────────

def test_kb_with_workaround_returns_existing_workaround():
    result = detect_existing_solution(
        kb_brief="A workaround exists: export the file and re-import with the adjusted values."
    )
    assert result["solution_type"] == "existing_workaround"
    assert result["has_existing_solution"] is True
    assert result["recommended_action"] == "explain_workaround"


# ── Priority 4: template pattern ─────────────────────────────────────────────

def test_kb_with_template_pattern_returns_existing_template_pattern():
    result = detect_existing_solution(
        kb_brief="There is an existing template pattern for this type of note."
    )
    assert result["solution_type"] == "existing_template_pattern"
    assert result["recommended_action"] == "reference_existing_template_pattern"


# ── Priority 5: client preference + correct behaviour → make_editable ────────

def test_evidence_custom_wording_and_correct_behaviour_returns_make_editable():
    result = detect_existing_solution(
        evidence=_ev(
            mentions_custom_wording=True,
            mentions_correct_current_behaviour=True,
        )
    )
    assert result["solution_type"] == "make_editable"
    assert result["has_existing_solution"] is True
    assert result["recommended_action"] == "make_editable"


def test_ticket_custom_wording_and_current_behaviour_text_returns_make_editable():
    """Custom wording detected in ticket text + 'correct' in current_behaviour."""
    result = detect_existing_solution(
        ticket_summary="We want our preferred wording in this field.",
        current_behaviour="The current wording is correct and standard.",
    )
    assert result["solution_type"] == "make_editable"
    assert result["recommended_action"] == "make_editable"


def test_custom_wording_without_correct_behaviour_returns_unclear():
    """Custom wording alone is not sufficient — need correct-behaviour confirmation."""
    result = detect_existing_solution(
        evidence=_ev(mentions_custom_wording=True)
    )
    assert result["solution_type"] == "unclear"


def test_correct_behaviour_without_custom_wording_returns_unclear():
    """Correct behaviour alone is not sufficient — need the preference signal too."""
    result = detect_existing_solution(
        evidence=_ev(mentions_correct_current_behaviour=True)
    )
    assert result["solution_type"] == "unclear"


def test_make_editable_has_high_confidence():
    result = detect_existing_solution(
        evidence=_ev(
            mentions_custom_wording=True,
            mentions_correct_current_behaviour=True,
        )
    )
    assert result["confidence"] >= 0.8


# ── Sources tracking ──────────────────────────────────────────────────────────

def test_kb_brief_in_sources():
    result = detect_existing_solution(kb_brief="Some KB content.")
    assert "kb_brief" in result["sources"]


def test_code_brief_in_sources():
    result = detect_existing_solution(code_brief="Template logic.")
    assert "code_brief" in result["sources"]


def test_research_brief_in_sources():
    result = detect_existing_solution(research_brief="Research findings.")
    assert "research_brief" in result["sources"]


def test_evidence_in_sources():
    result = detect_existing_solution(evidence=_ev(mentions_custom_wording=True))
    assert "evidence" in result["sources"]


def test_no_briefs_no_evidence_empty_sources():
    result = detect_existing_solution()
    assert result["sources"] == []


# ── Signals populated ─────────────────────────────────────────────────────────

def test_signals_reflect_evidence_flags():
    result = detect_existing_solution(
        evidence=_ev(
            mentions_existing_workaround=True,
            mentions_wrong_output=False,
            mentions_custom_wording=True,
            mentions_correct_current_behaviour=False,
        )
    )
    sigs = result["signals"]
    assert sigs["evidence_workaround"] is True
    assert sigs["evidence_wrong_output"] is False
    assert sigs["evidence_custom_wording"] is True
    assert sigs["evidence_correct_behaviour"] is False


def test_signals_reflect_context_text():
    result = detect_existing_solution(
        kb_brief="Use the existing setting in the configuration panel.",
    )
    sigs = result["signals"]
    assert sigs["context_existing_setting"] is True
    assert sigs["context_existing_workaround"] is False


# ── Does NOT mutate inputs ────────────────────────────────────────────────────

def test_does_not_mutate_evidence():
    ev = _ev(mentions_custom_wording=True, mentions_correct_current_behaviour=True)
    original = dict(ev)
    detect_existing_solution(evidence=ev)
    assert ev == original


# ── Acceptance scenario ───────────────────────────────────────────────────────

def test_acceptance_custom_wording_correct_behaviour_make_editable():
    """Acceptance: client wording preference on correct system behaviour → make_editable.

    Ticket:    "Client asks to change the default wording to their preferred wording."
    Behaviour: "Current wording is correct and standard."
    Evidence:  mentions_custom_wording=True, mentions_correct_current_behaviour=True,
               mentions_wrong_output=False
    Expected:  solution_type=make_editable, recommended_action=make_editable
    """
    result = detect_existing_solution(
        ticket_summary="Client asks to change the default wording to their preferred wording.",
        current_behaviour="Current wording is correct and standard.",
        evidence=_ev(
            mentions_custom_wording=True,
            mentions_correct_current_behaviour=True,
            mentions_wrong_output=False,
        ),
    )

    assert result["solution_type"] == "make_editable", (
        f"Expected make_editable, got {result['solution_type']}"
    )
    assert result["recommended_action"] == "make_editable", (
        f"Expected make_editable recommended_action, got {result['recommended_action']}"
    )
    assert result["has_existing_solution"] is True
    assert result["confidence"] >= 0.8
