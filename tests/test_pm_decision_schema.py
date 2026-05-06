"""Tests for the PMDecision schema and safe defaults."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.schemas import PMDecision, REQUIRED_FIELDS, SAFE_DEFAULTS


def test_pm_decision_to_dict_has_all_required_fields():
    d = PMDecision().to_dict()
    for field in REQUIRED_FIELDS:
        assert field in d, f"Missing required field: {field}"


def test_pm_decision_default_values_are_safe():
    d = PMDecision().to_dict()
    # Safe defaults: never over-confident, never commits to law
    assert d["decision"] == "needs_analysis"
    assert d["should_mention_law"] is False
    assert d["needs_prd"] is False
    assert d["answer_depth"] == "short"
    assert d["max_words"] <= 250
    assert d["confidence"] <= 0.5
    assert isinstance(d["evidence_used"], list)


def test_pm_decision_fields_match_safe_defaults():
    d = PMDecision().to_dict()
    for key, val in SAFE_DEFAULTS.items():
        if key == "evidence_used":
            assert d[key] == [], f"evidence_used default should be []"
        else:
            assert d[key] == val, f"Default for {key}: expected {val!r}, got {d[key]!r}"


def test_pm_decision_can_be_overridden():
    pm = PMDecision(
        decision="accept_bug",
        classification="bug",
        complexity="simple",
        answer_depth="short",
        max_words=150,
        needs_prd=False,
        needs_development=True,
        development_type="bug_fix",
        legal_status="product_standard",
        should_mention_law=False,
        global_change_risk="low",
        recommended_action="accept_bug",
        reason="Reproducible bug confirmed.",
        confidence=0.9,
    )
    d = pm.to_dict()
    assert d["decision"] == "accept_bug"
    assert d["classification"] == "bug"
    assert d["needs_development"] is True
    assert d["development_type"] == "bug_fix"
    assert d["should_mention_law"] is False
