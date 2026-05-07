"""Tests for ai/pm_analysis_instructions."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.pm_analysis_instructions import get_pm_analysis_mode, build_pm_analysis_instructions


# ── get_pm_analysis_mode ──────────────────────────────────────────────────────

def test_mode_none_returns_normal():
    assert get_pm_analysis_mode(None) == "normal_analysis"


def test_mode_empty_returns_normal():
    assert get_pm_analysis_mode({}) == "normal_analysis"


def test_mode_make_editable_returns_short_client_preference():
    assert get_pm_analysis_mode({"decision": "make_editable"}) == "short_client_preference_analysis"


def test_mode_refuse_global_change_returns_short_client_preference():
    assert get_pm_analysis_mode({"decision": "refuse_global_change"}) == "short_client_preference_analysis"


def test_mode_client_preference_classification_returns_short_client():
    assert get_pm_analysis_mode({"classification": "client_preference"}) == "short_client_preference_analysis"


def test_mode_product_standard_classification_returns_short_client():
    assert get_pm_analysis_mode({"classification": "product_standard"}) == "short_client_preference_analysis"


def test_mode_expected_behaviour_classification_returns_short_client():
    assert get_pm_analysis_mode({"classification": "expected_behaviour"}) == "short_client_preference_analysis"


def test_mode_explain_workaround_returns_workaround():
    assert get_pm_analysis_mode({"decision": "explain_workaround"}) == "workaround_analysis"


def test_mode_support_guidance_decision_returns_workaround():
    assert get_pm_analysis_mode({"decision": "support_guidance"}) == "workaround_analysis"


def test_mode_support_guidance_dev_type_returns_workaround():
    assert get_pm_analysis_mode({"development_type": "support_guidance"}) == "workaround_analysis"


def test_mode_no_dev_dev_type_returns_workaround():
    assert get_pm_analysis_mode({"development_type": "no_dev"}) == "workaround_analysis"


def test_mode_accept_bug_returns_bug():
    assert get_pm_analysis_mode({"decision": "accept_bug"}) == "bug_analysis"


def test_mode_bug_fix_dev_type_returns_bug():
    assert get_pm_analysis_mode({"development_type": "bug_fix"}) == "bug_analysis"


def test_mode_feature_request_decision_returns_feature_request():
    assert get_pm_analysis_mode({"decision": "feature_request"}) == "feature_request_analysis"


def test_mode_feature_request_dev_type_returns_feature_request():
    assert get_pm_analysis_mode({"development_type": "feature_request"}) == "feature_request_analysis"


def test_mode_needs_analysis_decision_returns_needs_analysis():
    assert get_pm_analysis_mode({"decision": "needs_analysis"}) == "needs_analysis"


def test_mode_needs_analysis_complexity_returns_needs_analysis():
    assert get_pm_analysis_mode({"complexity": "needs_analysis"}) == "needs_analysis"


def test_mode_unknown_returns_normal():
    assert get_pm_analysis_mode({"decision": "something_unrecognised"}) == "normal_analysis"


# ── build_pm_analysis_instructions ───────────────────────────────────────────

def test_empty_decision_returns_empty():
    assert build_pm_analysis_instructions(None) == ""


def test_empty_dict_returns_empty():
    assert build_pm_analysis_instructions({}) == ""


def test_title_always_present():
    result = build_pm_analysis_instructions({"decision": "make_editable"})
    assert "PM ANALYSIS INSTRUCTIONS:" in result


def test_mode_included_in_output():
    result = build_pm_analysis_instructions({"decision": "make_editable"})
    assert "short_client_preference_analysis" in result


def test_needs_prd_false_produces_no_prd_instruction():
    result = build_pm_analysis_instructions({"needs_prd": False})
    assert "PRD" in result
    assert "Objective" in result or "User Story" in result or "Acceptance Criteria" in result


def test_needs_prd_true_does_not_produce_no_prd_instruction():
    result = build_pm_analysis_instructions({"needs_prd": True})
    # When needs_prd is True, no instruction to avoid PRD
    assert "Do NOT produce PRD" not in result


def test_should_mention_law_false_produces_no_law_instruction():
    result = build_pm_analysis_instructions({"should_mention_law": False})
    assert "law" in result.lower() or "article" in result.lower() or "legal" in result.lower()
    assert "Do NOT mention" in result


def test_should_mention_law_true_does_not_produce_no_law_instruction():
    result = build_pm_analysis_instructions({"should_mention_law": True})
    assert "Do NOT mention law" not in result


def test_global_change_risk_high_produces_no_global_instruction():
    result = build_pm_analysis_instructions({"global_change_risk": "high"})
    assert "global default" in result.lower()
    assert "Do NOT recommend" in result


def test_global_change_risk_low_does_not_produce_no_global_instruction():
    result = build_pm_analysis_instructions({"global_change_risk": "low"})
    assert "Do NOT recommend changing the global default" not in result


def test_make_editable_produces_editability_instruction():
    result = build_pm_analysis_instructions({"recommended_action": "make_editable"})
    assert "configurable" in result.lower() or "editable" in result.lower()


def test_support_guidance_dev_type_produces_no_dev_instruction():
    result = build_pm_analysis_instructions({"development_type": "support_guidance"})
    assert "development" in result.lower() or "backlog" in result.lower()
    assert "Do NOT create" in result


def test_no_dev_dev_type_produces_no_dev_instruction():
    result = build_pm_analysis_instructions({"development_type": "no_dev"})
    assert "Do NOT create" in result


def test_bug_fix_produces_bug_not_feature_instruction():
    result = build_pm_analysis_instructions({"development_type": "bug_fix"})
    assert "bug" in result.lower() or "defect" in result.lower()
    assert "NOT" in result


def test_accept_bug_produces_bug_not_feature_instruction():
    result = build_pm_analysis_instructions({"decision": "accept_bug"})
    assert "bug" in result.lower() or "defect" in result.lower()


def test_short_answer_depth_produces_concise_instruction():
    result = build_pm_analysis_instructions({"answer_depth": "short"})
    assert "concise" in result.lower()


def test_does_not_mutate_pm_decision():
    pm = {"decision": "make_editable", "needs_prd": False}
    original = dict(pm)
    build_pm_analysis_instructions(pm)
    assert pm == original


# ── Acceptance scenario ───────────────────────────────────────────────────────

def test_acceptance_make_editable_full_decision():
    pm_decision = {
        "decision": "make_editable",
        "classification": "client_preference",
        "complexity": "simple",
        "answer_depth": "short",
        "max_words": 200,
        "needs_prd": False,
        "needs_development": True,
        "development_type": "small_improvement",
        "legal_status": "client_preference",
        "should_mention_law": False,
        "global_change_risk": "high",
        "recommended_action": "make_editable",
        "reason": "Client preference and current behaviour is correct.",
    }

    result = build_pm_analysis_instructions(pm_decision)

    assert "PM ANALYSIS INSTRUCTIONS:" in result
    assert "short_client_preference_analysis" in result
    assert "concise" in result.lower()                     # answer_depth=short
    assert "PRD" in result                                  # needs_prd=false
    assert "Do NOT mention" in result                       # should_mention_law=false
    assert "global default" in result.lower()               # global_change_risk=high
    assert "configurable" in result.lower() or "editable" in result.lower()  # make_editable
