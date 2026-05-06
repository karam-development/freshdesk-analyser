"""Tests for the PM decision builder — including the critical acceptance scenario."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.pm_decision_builder import build_pm_decision_from_gates
from ai.schemas import REQUIRED_FIELDS


# ── Helpers ───────────────────────────────────────────────────────────────────

def _wording_preference_gates():
    """Gate results for the canonical wording-preference scenario:
    client wants custom wording, current wording is correct, no legal evidence."""
    return {
        "complexity": {
            "complexity": "simple",
            "answer_depth": "short",
            "max_words": 200,
            "needs_prd": False,
            "reason": "Simple wording request.",
        },
        "legal_preference": {
            "legal_status": "client_preference",
            "should_mention_law": False,
            "reason": "Client wording preference; no legal evidence.",
            "confidence": 0.85,
        },
        "global_change_risk": {
            "global_change_risk": "high",
            "safe_to_change_default": False,
            "recommended_action": "make_editable",
            "reason": "Current wording is correct; high global-change risk.",
        },
        "development_need": {
            "needs_development": False,
            "development_type": "no_dev",
            "recommended_action": "needs_analysis",
            "reason": "No development needed for wording preference.",
        },
    }


# ── Critical acceptance scenario ──────────────────────────────────────────────

def test_wording_preference_critical_scenario():
    """The most important acceptance test:
    Client asks to change wording → correct current wording → no legal evidence.
    Expected: short/no-PRD/no-law/high-global-risk decision."""
    result = build_pm_decision_from_gates(
        ticket_summary="Client wants to change the wording to match their company preference",
        gate_results=_wording_preference_gates(),
        evidence_used=["ticket_text", "current_behaviour"],
    )

    # Classification must reflect client preference
    assert result["classification"] == "client_preference", (
        f"Expected client_preference, got {result['classification']}"
    )

    # Legal status must remain client-preference or product-standard (NOT mandatory)
    assert result["legal_status"] in ("client_preference", "product_standard"), (
        f"Expected client_preference or product_standard, got {result['legal_status']}"
    )

    # High global-change risk
    assert result["global_change_risk"] == "high", (
        f"Expected high global_change_risk, got {result['global_change_risk']}"
    )

    # Decision must be refuse or make_editable (not accept or pass through)
    assert result["decision"] in ("refuse_global_change", "make_editable"), (
        f"Expected refuse_global_change or make_editable, got {result['decision']}"
    )

    # Response constraints
    assert result["answer_depth"] == "short", (
        f"Expected answer_depth=short, got {result['answer_depth']}"
    )
    assert result["max_words"] <= 250, (
        f"Expected max_words <= 250, got {result['max_words']}"
    )
    assert result["needs_prd"] is False, (
        f"Expected needs_prd=False, got {result['needs_prd']}"
    )

    # Never cite law for a client preference
    assert result["should_mention_law"] is False, (
        f"Expected should_mention_law=False, got {result['should_mention_law']}"
    )


# ── Field completeness ────────────────────────────────────────────────────────

def test_builder_returns_all_required_fields():
    result = build_pm_decision_from_gates(
        ticket_summary="Some ticket",
        gate_results={},
    )
    for field in REQUIRED_FIELDS:
        assert field in result, f"Missing required field: {field}"


def test_empty_gate_results_produce_safe_defaults():
    result = build_pm_decision_from_gates("Any ticket", gate_results={})
    assert result["decision"] == "needs_analysis"
    assert result["should_mention_law"] is False
    assert result["needs_prd"] is False
    assert result["max_words"] <= 250


# ── Bug scenario ──────────────────────────────────────────────────────────────

def test_bug_scenario():
    gates = {
        "complexity": {"complexity": "simple", "answer_depth": "short", "max_words": 200, "needs_prd": False},
        "legal_preference": {"legal_status": "product_standard", "should_mention_law": False, "confidence": 0.7},
        "global_change_risk": {"global_change_risk": "low", "safe_to_change_default": True, "recommended_action": "accept_global_fix"},
        "development_need": {"needs_development": True, "development_type": "bug_fix", "recommended_action": "accept_bug"},
    }
    result = build_pm_decision_from_gates("The output is wrong", gates)
    assert result["decision"] == "accept_bug"
    assert result["classification"] == "bug"
    assert result["needs_development"] is True


# ── Support guidance scenario ─────────────────────────────────────────────────

def test_support_guidance_scenario():
    gates = {
        "complexity": {"complexity": "simple", "answer_depth": "short", "max_words": 200, "needs_prd": False},
        "legal_preference": {"legal_status": "unclear", "should_mention_law": False, "confidence": 0.4},
        "global_change_risk": {"global_change_risk": "unclear", "safe_to_change_default": False, "recommended_action": "needs_analysis"},
        "development_need": {"needs_development": False, "development_type": "support_guidance", "recommended_action": "explain_workaround"},
    }
    result = build_pm_decision_from_gates("How do I use the workaround?", gates)
    assert result["decision"] in ("explain_workaround", "support_guidance")
    assert result["needs_development"] is False


# ── Complex PRD scenario ──────────────────────────────────────────────────────

def test_complex_scenario_has_prd():
    gates = {
        "complexity": {"complexity": "complex", "answer_depth": "prd", "max_words": 800, "needs_prd": True},
        "legal_preference": {"legal_status": "product_standard", "should_mention_law": False, "confidence": 0.7},
        "global_change_risk": {"global_change_risk": "medium", "safe_to_change_default": False, "recommended_action": "needs_analysis"},
        "development_need": {"needs_development": True, "development_type": "feature_request", "recommended_action": "feature_request"},
    }
    result = build_pm_decision_from_gates("Complex multi-template feature", gates)
    assert result["needs_prd"] is True
    assert result["complexity"] == "complex"


# ── should_mention_law never set by preference alone ─────────────────────────

def test_should_mention_law_stays_false_for_preference():
    gates = {
        "legal_preference": {
            "legal_status": "client_preference",
            "should_mention_law": False,  # gate explicitly said False
        },
    }
    result = build_pm_decision_from_gates("Wording change", gates)
    assert result["should_mention_law"] is False
