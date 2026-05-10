"""Tests for ai/support_explanation.py.

Source-level unit tests — no Flask, no DB, no network.
"""
from __future__ import annotations

import pytest

from ai.support_explanation import (
    build_support_explanation_context,
    _is_support_explanation_ticket,
)


# ── Activation tests ──────────────────────────────────────────────────────────


def test_activates_for_explain_workaround():
    pm = {"decision": "explain_workaround", "classification": "other"}
    assert build_support_explanation_context(pm_decision=pm) != ""


def test_activates_for_support_guidance():
    pm = {"decision": "support_guidance", "classification": "other"}
    assert build_support_explanation_context(pm_decision=pm) != ""


def test_activates_for_make_editable():
    pm = {"decision": "make_editable", "classification": "other"}
    assert build_support_explanation_context(pm_decision=pm) != ""


def test_activates_for_reuse_existing_pattern():
    pm = {"decision": "reuse_existing_pattern", "classification": "other"}
    assert build_support_explanation_context(pm_decision=pm) != ""


def test_activates_for_how_to_classification():
    pm = {"decision": "needs_analysis", "classification": "how_to"}
    assert build_support_explanation_context(pm_decision=pm) != ""


def test_activates_for_client_preference_classification():
    pm = {"decision": "needs_analysis", "classification": "client_preference"}
    assert build_support_explanation_context(pm_decision=pm) != ""


def test_activates_for_expected_behaviour_classification():
    pm = {"decision": "needs_analysis", "classification": "expected_behaviour"}
    assert build_support_explanation_context(pm_decision=pm) != ""


def test_activates_for_no_development_needed():
    pm = {"decision": "support_guidance", "classification": "other", "needs_development": False}
    assert build_support_explanation_context(pm_decision=pm) != ""


# ── Non-activation tests ──────────────────────────────────────────────────────


def test_returns_empty_for_feature_request():
    pm = {"decision": "feature_request", "classification": "feature_request", "needs_development": True}
    result = build_support_explanation_context(pm_decision=pm)
    assert result == ""


def test_returns_empty_for_refuse_global_change():
    pm = {"decision": "refuse_global_change", "classification": "bug", "needs_development": False}
    result = build_support_explanation_context(pm_decision=pm)
    assert result == ""


def test_returns_empty_for_none_input():
    assert build_support_explanation_context(pm_decision=None) == ""


def test_returns_empty_for_empty_dict():
    assert build_support_explanation_context(pm_decision={}) == ""


def test_returns_empty_for_needs_analysis_only():
    pm = {"decision": "needs_analysis", "classification": "needs_analysis", "needs_development": True}
    assert build_support_explanation_context(pm_decision=pm) == ""


# ── Content tests ─────────────────────────────────────────────────────────────


def test_output_contains_support_guidance_header():
    pm = {"decision": "support_guidance", "classification": "other"}
    result = build_support_explanation_context(pm_decision=pm)
    assert "SUPPORT EXPLANATION GUIDANCE" in result


def test_output_instructs_explain_behaviour():
    pm = {"decision": "support_guidance", "classification": "other"}
    result = build_support_explanation_context(pm_decision=pm)
    assert "current product behaviour" in result.lower() or "explain" in result.lower()


def test_output_instructs_avoid_bare_refuse():
    pm = {"decision": "explain_workaround", "classification": "other"}
    result = build_support_explanation_context(pm_decision=pm)
    lower = result.lower()
    assert "bso" in lower or "bare" in lower or "redirect" in lower


def test_output_mentions_next_step():
    pm = {"decision": "support_guidance", "classification": "how_to"}
    result = build_support_explanation_context(pm_decision=pm)
    assert "Next step" in result or "next step" in result.lower()


def test_reason_included_in_output():
    pm = {"decision": "support_guidance", "classification": "other", "reason": "Client prefers old layout"}
    result = build_support_explanation_context(pm_decision=pm)
    assert "Client prefers old layout" in result


def test_recommended_action_included():
    pm = {
        "decision": "make_editable",
        "classification": "other",
        "recommended_action": "guide_client_to_settings",
    }
    result = build_support_explanation_context(pm_decision=pm)
    assert "guide_client_to_settings" in result


# ── Safety tests ──────────────────────────────────────────────────────────────


def test_never_raises_on_bad_pm_decision():
    # Garbage input must not raise
    result = build_support_explanation_context(pm_decision={"decision": None, "classification": 123})
    assert isinstance(result, str)


def test_never_raises_on_unexpected_types():
    result = build_support_explanation_context(pm_decision="not a dict")  # type: ignore[arg-type]
    assert isinstance(result, str)


def test_existing_solution_included_when_provided():
    pm = {"decision": "make_editable", "classification": "other"}
    existing = {"summary": "The template already has an editable field.", "description": "Go to Template > Fields."}
    result = build_support_explanation_context(pm_decision=pm, existing_solution=existing)
    assert "editable field" in result or "Template" in result


def test_existing_solution_not_required():
    pm = {"decision": "support_guidance", "classification": "how_to"}
    result = build_support_explanation_context(pm_decision=pm, existing_solution=None)
    assert result != ""
