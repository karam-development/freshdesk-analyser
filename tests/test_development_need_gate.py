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
