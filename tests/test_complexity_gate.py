"""Tests for the complexity gate."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.gates.complexity_gate import evaluate_complexity


def test_wording_preference_is_simple():
    result = evaluate_complexity(
        "Client asks to change the wording of a dropdown label",
        requested_change="Replace 'Director' with 'Manager'",
    )
    assert result["complexity"] == "simple"
    assert result["answer_depth"] == "short"
    assert result["max_words"] <= 250
    assert result["needs_prd"] is False


def test_typo_is_simple():
    result = evaluate_complexity(
        "There is a typo in the template text: 'Gérantt' should be 'Gérant'",
    )
    assert result["complexity"] == "simple"
    assert result["answer_depth"] == "short"
    assert result["max_words"] <= 250
    assert result["needs_prd"] is False


def test_make_editable_is_simple():
    result = evaluate_complexity(
        "Client would like the field to be editable so they can customise it",
    )
    assert result["complexity"] == "simple"
    assert result["answer_depth"] == "short"
    assert result["max_words"] <= 250
    assert result["needs_prd"] is False


def test_workaround_is_simple():
    result = evaluate_complexity(
        "Client asks how to add a workaround for the reconciliation note",
    )
    assert result["complexity"] == "simple"
    assert result["needs_prd"] is False


def test_multi_template_calculation_is_complex():
    result = evaluate_complexity(
        "Change the calculation across multiple templates affecting accounts 600-699",
        requested_change="Update formula in 3 templates to match IFRS standard",
    )
    assert result["complexity"] == "complex"
    assert result["needs_prd"] is True
    assert result["max_words"] > 250


def test_legal_uncertainty_is_needs_analysis():
    result = evaluate_complexity(
        "Unclear whether this accounting standard is legally mandatory in Luxembourg",
    )
    assert result["complexity"] == "needs_analysis"
    assert result["needs_prd"] is False


def test_visibility_condition_is_medium():
    result = evaluate_complexity(
        "Add a visibility condition to the dropdown in a single template",
    )
    assert result["complexity"] == "medium"
    assert result["answer_depth"] == "normal"
    assert result["max_words"] <= 500
    assert result["needs_prd"] is False
