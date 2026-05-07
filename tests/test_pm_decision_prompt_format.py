"""Tests for format_pm_decision_for_prompt."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.pm_decision_formatter import format_pm_decision_for_prompt


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_editable_decision():
    return {
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
        "reason": "Client preference on correct wording.",
    }


def _bug_decision():
    return {
        "decision": "accept_bug",
        "classification": "bug",
        "complexity": "simple",
        "answer_depth": "short",
        "max_words": 200,
        "needs_prd": False,
        "needs_development": True,
        "development_type": "bug_fix",
        "legal_status": "product_standard",
        "should_mention_law": False,
        "global_change_risk": "low",
        "recommended_action": "accept_bug",
        "reason": "Wrong output detected.",
    }


# ── Field coverage ────────────────────────────────────────────────────────────

def test_format_includes_all_key_constraints():
    text = format_pm_decision_for_prompt(_make_editable_decision())
    for keyword in (
        "Decision:", "Classification:", "Complexity:", "Answer depth:",
        "Max words:", "Needs PRD:", "Legal status:", "Mention law:",
        "Global change risk:", "Recommended action:",
    ):
        assert keyword in text, f"Expected '{keyword}' in formatted prompt"


def test_format_includes_reason_when_present():
    text = format_pm_decision_for_prompt(_make_editable_decision())
    assert "Client preference on correct wording" in text


def test_format_omits_reason_when_empty():
    dec = _make_editable_decision()
    dec["reason"] = ""
    text = format_pm_decision_for_prompt(dec)
    assert "Reason:" not in text


# ── should_mention_law handling ───────────────────────────────────────────────

def test_should_mention_law_false_is_explicitly_stated():
    text = format_pm_decision_for_prompt(_make_editable_decision())
    assert "should_mention_law is false" in text.lower() or "mention law" in text.lower()
    assert "do NOT cite law" in text or "not cite law" in text.lower()


def test_should_mention_law_true_does_not_add_law_rule():
    dec = _make_editable_decision()
    dec["should_mention_law"] = True
    text = format_pm_decision_for_prompt(dec)
    assert "do NOT cite law" not in text


# ── make_editable / refuse_global_change handling ────────────────────────────

def test_make_editable_recommendation_is_explicitly_stated():
    text = format_pm_decision_for_prompt(_make_editable_decision())
    assert "make_editable" in text or "make editable" in text.lower()
    assert "per-client" in text or "editable" in text


def test_refuse_global_change_rule_is_stated():
    dec = _make_editable_decision()
    dec["decision"] = "refuse_global_change"
    text = format_pm_decision_for_prompt(dec)
    assert "refuse_global_change" in text or "global default change" in text.lower()


# ── global change risk handling ───────────────────────────────────────────────

def test_high_global_risk_warns_about_global_change():
    text = format_pm_decision_for_prompt(_make_editable_decision())
    assert "global_change_risk is HIGH" in text or "HIGH" in text
    assert "NOT recommend" in text or "do NOT" in text


def test_low_global_risk_does_not_add_global_warning():
    text = format_pm_decision_for_prompt(_bug_decision())
    assert "global_change_risk is HIGH" not in text


# ── needs_prd handling ────────────────────────────────────────────────────────

def test_needs_prd_false_rule_is_stated():
    text = format_pm_decision_for_prompt(_make_editable_decision())
    assert "needs_prd is false" in text.lower() or "not produce PRD" in text


def test_needs_prd_true_does_not_add_no_prd_rule():
    dec = _make_editable_decision()
    dec["needs_prd"] = True
    text = format_pm_decision_for_prompt(dec)
    assert "do NOT produce PRD" not in text


# ── answer depth handling ─────────────────────────────────────────────────────

def test_short_answer_depth_rule_is_stated():
    text = format_pm_decision_for_prompt(_make_editable_decision())
    assert "SHORT" in text or "short" in text.lower()
    assert "200" in text or "concise" in text.lower()


# ── edge cases ────────────────────────────────────────────────────────────────

def test_empty_pm_decision_returns_empty_string():
    assert format_pm_decision_for_prompt({}) == ""
    assert format_pm_decision_for_prompt(None) == ""


def test_formatted_prompt_has_rules_section():
    text = format_pm_decision_for_prompt(_make_editable_decision())
    assert "Rules for this response" in text or "non-negotiable" in text
