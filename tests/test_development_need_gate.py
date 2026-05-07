"""Tests for the development need gate."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.gates.development_need_gate import evaluate_development_need


def test_workaround_means_no_dev():
    result = evaluate_development_need(
        "Client asks how to use an existing workaround for the reconciliation note"
    )
    assert result["needs_development"] is False
    assert result["development_type"] in ("support_guidance", "no_dev")
    assert result["recommended_action"] in ("explain_workaround", "support_guidance")


def test_support_question_means_no_dev():
    result = evaluate_development_need(
        "Client wants guidance on how to set up the template correctly"
    )
    assert result["needs_development"] is False


def test_correct_wording_editable_means_small_improvement():
    result = evaluate_development_need(
        "Client wants the field to be editable so they can customise the wording"
    )
    assert result["needs_development"] is True
    assert result["development_type"] == "small_improvement"
    assert result["recommended_action"] == "make_editable"


def test_make_editable_request_is_small_improvement():
    result = evaluate_development_need(
        "Please make this field editable for the client"
    )
    assert result["needs_development"] is True
    assert result["development_type"] == "small_improvement"
    assert result["recommended_action"] == "make_editable"


def test_wrong_output_is_bug_fix():
    result = evaluate_development_need(
        "The template is producing the wrong output for account 601"
    )
    assert result["needs_development"] is True
    assert result["development_type"] == "bug_fix"
    assert result["recommended_action"] == "accept_bug"


def test_broken_behaviour_is_bug_fix():
    result = evaluate_development_need(
        "The calculation is incorrect and the result is wrong"
    )
    assert result["needs_development"] is True
    assert result["development_type"] == "bug_fix"


def test_context_make_editable_triggers_small_improvement():
    result = evaluate_development_need(
        "Client has a wording preference",
        decision_context={"recommended_action": "make_editable"},
    )
    assert result["needs_development"] is True
    assert result["development_type"] == "small_improvement"


def test_optional_feature_is_feature_request():
    result = evaluate_development_need(
        "Client requests a new dropdown option to be added to the template"
    )
    assert result["needs_development"] is True
    assert result["development_type"] == "feature_request"


# ── PR #9: evidence signal tests ─────────────────────────────────────────────

def test_evidence_workaround_beats_keyword_detection():
    """evidence['mentions_existing_workaround']=True → support_guidance (priority 1)."""
    result = evaluate_development_need(
        "Client question with no workaround keywords",
        decision_context={"evidence": {"mentions_existing_workaround": True}},
    )
    assert result["needs_development"] is False
    assert result["development_type"] == "support_guidance"
    assert result["recommended_action"] == "explain_workaround"


def test_evidence_wrong_output_triggers_bug_fix():
    """evidence['mentions_wrong_output']=True → bug_fix (priority 2)."""
    result = evaluate_development_need(
        "Something is off with the template",
        decision_context={"evidence": {"mentions_wrong_output": True}},
    )
    assert result["needs_development"] is True
    assert result["development_type"] == "bug_fix"
    assert result["recommended_action"] == "accept_bug"


def test_client_preference_and_high_risk_triggers_make_editable():
    """legal_status=client_preference + global_change_risk=high → make_editable (priority 3)."""
    result = evaluate_development_need(
        "Client has a styling preference",
        decision_context={
            "evidence": {},
            "legal_status": "client_preference",
            "global_change_risk": "high",
        },
    )
    assert result["needs_development"] is True
    assert result["development_type"] == "small_improvement"
    assert result["recommended_action"] == "make_editable"


def test_product_standard_and_high_risk_triggers_make_editable():
    """legal_status=product_standard + global_change_risk=high → make_editable (priority 3)."""
    result = evaluate_development_need(
        "Client wants a deviation from the standard behaviour",
        decision_context={
            "evidence": {},
            "legal_status": "product_standard",
            "global_change_risk": "high",
        },
    )
    assert result["needs_development"] is True
    assert result["development_type"] == "small_improvement"
    assert result["recommended_action"] == "make_editable"


# ── PR #16: existing_solution context tests ───────────────────────────────────

def test_existing_solution_setting_triggers_explain_existing_setting():
    """existing_solution.solution_type=existing_setting → explain_existing_setting (priority 1.5)."""
    result = evaluate_development_need(
        "Client asks how to configure the reconciliation note wording.",
        decision_context={
            "evidence": {},
            "existing_solution": {"solution_type": "existing_setting"},
        },
    )
    assert result["needs_development"] is False
    assert result["development_type"] == "support_guidance"
    assert result["recommended_action"] == "explain_existing_setting"


def test_existing_solution_setting_beats_bug_keywords():
    """existing_setting (priority 1.5) beats bug keyword fallback."""
    result = evaluate_development_need(
        "This seems wrong but there is an existing setting",
        decision_context={
            "evidence": {},
            "existing_solution": {"solution_type": "existing_setting"},
        },
    )
    assert result["recommended_action"] == "explain_existing_setting"


def test_existing_solution_make_editable_triggers_make_editable():
    """existing_solution.solution_type=make_editable → make_editable (priority 3.5)."""
    result = evaluate_development_need(
        "Client has a custom wording preference",
        decision_context={
            "evidence": {},
            "existing_solution": {"solution_type": "make_editable"},
        },
    )
    assert result["needs_development"] is True
    assert result["development_type"] == "small_improvement"
    assert result["recommended_action"] == "make_editable"


def test_existing_solution_workaround_enrichment_triggers_explain_workaround():
    """When enriched evidence sets mentions_existing_workaround=True,
    the gate returns explain_workaround via priority 1."""
    result = evaluate_development_need(
        "Client question with no direct workaround keywords",
        decision_context={
            "evidence": {"mentions_existing_workaround": True},
            "existing_solution": {"solution_type": "existing_workaround"},
        },
    )
    assert result["needs_development"] is False
    assert result["recommended_action"] == "explain_workaround"


def test_existing_solution_unclear_does_not_change_normal_flow():
    """existing_solution=unclear should not override normal keyword detection."""
    result = evaluate_development_need(
        "Client requests a new dropdown option to be added",
        decision_context={
            "evidence": {},
            "existing_solution": {"solution_type": "unclear"},
        },
    )
    # keyword detection: "new dropdown" → feature_request
    assert result["development_type"] == "feature_request"
