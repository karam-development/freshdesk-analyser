"""Tests for ai/pm_po_summary.py.

Covers:
  - humanize_decision_label
  - humanize_classification_label
  - humanize_development_type
  - build_pm_po_review_summary (structure, correctness, edge cases)
  - build_next_action (decision tree paths)
  - All functions are defensive: never raise on bad input
"""
import pytest

from ai.pm_po_summary import (
    build_next_action,
    build_pm_po_review_summary,
    humanize_classification_label,
    humanize_decision_label,
    humanize_development_type,
)


# ── humanize_decision_label ────────────────────────────────────────────────────

class TestHumanizeDecisionLabel:
    def test_known_values(self):
        assert "global change" in humanize_decision_label("refuse_global_change").lower()
        assert "bug" in humanize_decision_label("accept_bug").lower()
        assert "feature" in humanize_decision_label("feature_request").lower()
        assert "workaround" in humanize_decision_label("explain_workaround").lower()
        assert "guidance" in humanize_decision_label("support_guidance").lower()

    def test_none_returns_safe_default(self):
        result = humanize_decision_label(None)
        assert result
        assert isinstance(result, str)

    def test_empty_string_returns_safe_default(self):
        result = humanize_decision_label("")
        assert result
        assert isinstance(result, str)

    def test_unknown_value_returns_something(self):
        result = humanize_decision_label("totally_unknown_key")
        assert result
        assert isinstance(result, str)

    def test_never_raises(self):
        for val in [None, "", 0, [], {}, object(), b"bytes", 42]:
            result = humanize_decision_label(val)  # type: ignore[arg-type]
            assert isinstance(result, str)


# ── humanize_classification_label ─────────────────────────────────────────────

class TestHumanizeClassificationLabel:
    def test_known_values(self):
        assert humanize_classification_label("bug") == "Bug"
        assert humanize_classification_label("feature_request") == "Feature request"
        assert humanize_classification_label("how_to") == "How-to / training"

    def test_none_returns_not_classified(self):
        assert humanize_classification_label(None) == "Not classified"

    def test_empty_returns_not_classified(self):
        assert humanize_classification_label("") == "Not classified"

    def test_never_raises(self):
        for val in [None, "", 0, [], {}, object()]:
            result = humanize_classification_label(val)  # type: ignore[arg-type]
            assert isinstance(result, str)


# ── humanize_development_type ─────────────────────────────────────────────────

class TestHumanizeDevelopmentType:
    def test_known_values(self):
        assert "no development" in humanize_development_type("no_dev").lower()
        assert "bug" in humanize_development_type("bug_fix").lower()
        assert "feature" in humanize_development_type("feature_request").lower()

    def test_none_returns_safe_default(self):
        result = humanize_development_type(None)
        assert result
        assert isinstance(result, str)

    def test_never_raises(self):
        for val in [None, "", 0, [], {}, object()]:
            result = humanize_development_type(val)  # type: ignore[arg-type]
            assert isinstance(result, str)


# ── build_pm_po_review_summary ────────────────────────────────────────────────

EXPECTED_KEYS = {
    "classification_raw", "classification_label",
    "decision_raw", "decision_label",
    "recommended_action",
    "development_needed", "development_type_label",
    "existing_solution_found", "existing_solution_type",
    "safe_to_send_status", "safe_to_send_score",
    "po_decision", "reason",
    "next_action",
    "has_pm_decision",
    "confidence",
    "needs_prd",
}


class TestBuildPmPoReviewSummary:
    def test_returns_all_expected_keys_on_empty_input(self):
        result = build_pm_po_review_summary()
        assert EXPECTED_KEYS.issubset(result.keys()), (
            f"Missing keys: {EXPECTED_KEYS - result.keys()}"
        )

    def test_all_fields_have_correct_types_on_empty_input(self):
        result = build_pm_po_review_summary()
        assert isinstance(result["classification_raw"], str)
        assert isinstance(result["classification_label"], str)
        assert isinstance(result["decision_raw"], str)
        assert isinstance(result["decision_label"], str)
        assert isinstance(result["development_needed"], bool)
        assert isinstance(result["existing_solution_found"], bool)
        assert isinstance(result["has_pm_decision"], bool)
        assert isinstance(result["needs_prd"], bool)
        assert isinstance(result["next_action"], str)

    def test_pm_decision_fields_merged(self):
        pm_decision = {
            "decision": "accept_bug",
            "classification": "bug",
            "needs_development": True,
            "development_type": "bug_fix",
            "reason": "Confirmed bug in template X",
            "confidence": 0.9,
            "needs_prd": False,
            "recommended_action": "Fix in next sprint",
        }
        result = build_pm_po_review_summary(pm_decision=pm_decision)
        assert result["decision_raw"] == "accept_bug"
        assert result["classification_raw"] == "bug"
        assert result["development_needed"] is True
        assert "bug" in result["development_type_label"].lower()
        assert result["reason"] == "Confirmed bug in template X"
        assert result["confidence"] == 0.9
        assert result["has_pm_decision"] is True

    def test_safe_to_send_merged(self):
        sts = {"status": "safe_to_send", "score": 87}
        result = build_pm_po_review_summary(safe_to_send=sts)
        assert result["safe_to_send_status"] == "safe_to_send"
        assert result["safe_to_send_score"] == 87

    def test_existing_solution_merged(self):
        es = {"found": True, "type": "setting"}
        result = build_pm_po_review_summary(existing_solution=es)
        assert result["existing_solution_found"] is True
        assert result["existing_solution_type"] == "setting"

    def test_ticket_po_decision_merged(self):
        ticket = {"po_decision": "Approved", "classification": "bug"}
        result = build_pm_po_review_summary(ticket=ticket)
        assert result["po_decision"] == "approved"
        assert result["classification_raw"] == "bug"

    def test_never_raises_on_garbage_input(self):
        garbage_inputs = [
            (None, None, None, None, None),
            ({}, {}, {}, {}, {}),
            ("str", "str", "str", "str", "str"),
            ([], [], [], [], []),
            ({"decision": ""}, {"status": None}, {"found": None}, {}, {}),
        ]
        for ticket, pm, sts, es, kb in garbage_inputs:
            result = build_pm_po_review_summary(
                ticket=ticket, pm_decision=pm,
                safe_to_send=sts, existing_solution=es, kb_quality=kb,
            )
            assert isinstance(result, dict)
            assert "next_action" in result


# ── build_next_action ─────────────────────────────────────────────────────────

class TestBuildNextAction:
    def _summary(self, **kwargs):
        """Start from a valid minimal summary and override fields."""
        base = {
            "po_decision": "",
            "safe_to_send_status": "",
            "safe_to_send_score": None,
            "decision_raw": "needs_analysis",
            "development_needed": False,
            "has_pm_decision": False,
        }
        base.update(kwargs)
        return base

    def test_no_pm_decision_prompts_analysis(self):
        result = build_next_action(self._summary(has_pm_decision=False))
        assert "analysis" in result.lower() or "run" in result.lower()

    def test_no_po_decision_feature_request(self):
        result = build_next_action(self._summary(
            has_pm_decision=True,
            decision_raw="feature_request",
        ))
        assert "feature" in result.lower() or "approve" in result.lower()

    def test_no_po_decision_accept_bug(self):
        result = build_next_action(self._summary(
            has_pm_decision=True,
            decision_raw="accept_bug",
        ))
        assert "bug" in result.lower() or "fix" in result.lower()

    def test_approved_no_draft_generates(self):
        result = build_next_action(self._summary(po_decision="approved"))
        assert "generate" in result.lower() or "draft" in result.lower()

    def test_approved_draft_safe_to_send(self):
        result = build_next_action(self._summary(
            po_decision="approved",
            safe_to_send_status="safe_to_send",
        ))
        assert "freshdesk" in result.lower() or "ready" in result.lower() or "copy" in result.lower()

    def test_approved_draft_needs_review(self):
        result = build_next_action(self._summary(
            po_decision="approved",
            safe_to_send_status="needs_review",
        ))
        assert "warn" in result.lower() or "review" in result.lower() or "safe" in result.lower()

    def test_declined_no_draft(self):
        result = build_next_action(self._summary(po_decision="declined"))
        assert "decline" in result.lower() or "generate" in result.lower()

    def test_declined_with_draft(self):
        result = build_next_action(self._summary(
            po_decision="declined",
            safe_to_send_status="safe_to_send",
        ))
        assert result  # non-empty string

    def test_never_raises_on_garbage(self):
        for val in [None, "", 0, [], "random_string", {"po_decision": object()}]:
            result = build_next_action(val)  # type: ignore[arg-type]
            assert isinstance(result, str)
            assert result  # non-empty fallback
