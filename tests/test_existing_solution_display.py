"""Tests for ai/existing_solution_display.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.existing_solution_display import extract_existing_solution_from_pm_decision


# ── Helpers ───────────────────────────────────────────────────────────────────

_REQUIRED_KEYS = {
    "has_data", "has_existing_solution", "solution_type", "recommended_action",
    "confidence", "reason", "sources", "signals", "badge_label", "severity",
}


def _pm_with_gate(es_dict: dict) -> dict:
    """Build a minimal pm_decision with _gate_results.existing_solution."""
    return {"_gate_results": {"existing_solution": es_dict}}


def _full_es(**kwargs) -> dict:
    """Build a full existing_solution dict with sensible defaults."""
    base = {
        "has_existing_solution": True,
        "solution_type": "make_editable",
        "recommended_action": "make_editable",
        "confidence": 0.85,
        "reason": "Client preference and current behaviour is correct.",
        "sources": ["evidence", "current_behaviour"],
        "signals": {"evidence_custom_wording": True, "evidence_correct_behaviour": True,
                    "evidence_wrong_output": False},
    }
    base.update(kwargs)
    return base


# ── Return shape ─────────────────────────────────────────────────────────────

def test_returns_all_required_keys():
    result = extract_existing_solution_from_pm_decision({})
    for k in _REQUIRED_KEYS:
        assert k in result, f"Missing key: {k}"


def test_all_keys_present_with_full_data():
    result = extract_existing_solution_from_pm_decision(_pm_with_gate(_full_es()))
    for k in _REQUIRED_KEYS:
        assert k in result, f"Missing key with full data: {k}"


# ── Empty / None inputs → has_data=False ─────────────────────────────────────

def test_none_returns_has_data_false():
    result = extract_existing_solution_from_pm_decision(None)
    assert result["has_data"] is False


def test_empty_dict_returns_has_data_false():
    result = extract_existing_solution_from_pm_decision({})
    assert result["has_data"] is False


def test_non_dict_returns_has_data_false():
    result = extract_existing_solution_from_pm_decision("not a dict")  # type: ignore
    assert result["has_data"] is False


def test_pm_decision_without_gate_results_returns_has_data_false():
    result = extract_existing_solution_from_pm_decision({"decision": "make_editable"})
    assert result["has_data"] is False


def test_gate_results_without_existing_solution_returns_has_data_false():
    result = extract_existing_solution_from_pm_decision(
        {"_gate_results": {"complexity": {}, "development_need": {}}}
    )
    assert result["has_data"] is False


def test_empty_existing_solution_dict_returns_has_data_false():
    result = extract_existing_solution_from_pm_decision(_pm_with_gate({}))
    assert result["has_data"] is False


# ── Extraction from _gate_results.existing_solution ─────────────────────────

def test_extracts_from_gate_results():
    result = extract_existing_solution_from_pm_decision(_pm_with_gate(_full_es()))
    assert result["has_data"] is True


def test_has_existing_solution_preserved():
    result = extract_existing_solution_from_pm_decision(
        _pm_with_gate(_full_es(has_existing_solution=True))
    )
    assert result["has_existing_solution"] is True


def test_solution_type_preserved():
    result = extract_existing_solution_from_pm_decision(
        _pm_with_gate(_full_es(solution_type="existing_setting"))
    )
    assert result["solution_type"] == "existing_setting"


def test_recommended_action_preserved():
    result = extract_existing_solution_from_pm_decision(
        _pm_with_gate(_full_es(recommended_action="explain_existing_setting"))
    )
    assert result["recommended_action"] == "explain_existing_setting"


def test_confidence_preserved():
    result = extract_existing_solution_from_pm_decision(
        _pm_with_gate(_full_es(confidence=0.75))
    )
    assert abs(result["confidence"] - 0.75) < 0.001


def test_reason_preserved():
    result = extract_existing_solution_from_pm_decision(
        _pm_with_gate(_full_es(reason="Some reason text."))
    )
    assert result["reason"] == "Some reason text."


def test_sources_preserved_as_list():
    result = extract_existing_solution_from_pm_decision(
        _pm_with_gate(_full_es(sources=["kb_brief", "evidence"]))
    )
    assert result["sources"] == ["kb_brief", "evidence"]


def test_signals_dict_converted_to_list_of_truthy_keys():
    """signals stored as dict → only truthy keys returned as list."""
    es = _full_es(signals={
        "evidence_workaround": True,
        "evidence_wrong_output": False,
        "ticket_custom_wording": True,
    })
    result = extract_existing_solution_from_pm_decision(_pm_with_gate(es))
    assert "evidence_workaround" in result["signals"]
    assert "ticket_custom_wording" in result["signals"]
    assert "evidence_wrong_output" not in result["signals"]


def test_signals_list_preserved_directly():
    """signals already a list → returned as-is."""
    es = _full_es(signals=["sig_a", "sig_b"])
    result = extract_existing_solution_from_pm_decision(_pm_with_gate(es))
    assert result["signals"] == ["sig_a", "sig_b"]


# ── Fallback: top-level existing_solution key ─────────────────────────────────

def test_extracts_top_level_fallback():
    pm = {"existing_solution": _full_es(solution_type="existing_workaround")}
    result = extract_existing_solution_from_pm_decision(pm)
    assert result["has_data"] is True
    assert result["solution_type"] == "existing_workaround"


def test_gate_results_takes_priority_over_top_level():
    """_gate_results.existing_solution wins when both are present."""
    pm = {
        "_gate_results": {
            "existing_solution": _full_es(solution_type="existing_setting")
        },
        "existing_solution": _full_es(solution_type="make_editable"),
    }
    result = extract_existing_solution_from_pm_decision(pm)
    assert result["solution_type"] == "existing_setting"


# ── Severity mapping ──────────────────────────────────────────────────────────

def test_existing_setting_maps_to_success():
    result = extract_existing_solution_from_pm_decision(
        _pm_with_gate(_full_es(solution_type="existing_setting"))
    )
    assert result["severity"] == "success"


def test_existing_workaround_maps_to_success():
    result = extract_existing_solution_from_pm_decision(
        _pm_with_gate(_full_es(solution_type="existing_workaround"))
    )
    assert result["severity"] == "success"


def test_existing_template_pattern_maps_to_info():
    result = extract_existing_solution_from_pm_decision(
        _pm_with_gate(_full_es(solution_type="existing_template_pattern"))
    )
    assert result["severity"] == "info"


def test_make_editable_maps_to_warning():
    result = extract_existing_solution_from_pm_decision(
        _pm_with_gate(_full_es(solution_type="make_editable"))
    )
    assert result["severity"] == "warning"


def test_no_existing_solution_maps_to_neutral():
    result = extract_existing_solution_from_pm_decision(
        _pm_with_gate(_full_es(
            solution_type="no_existing_solution",
            has_existing_solution=False,
        ))
    )
    assert result["severity"] == "neutral"


def test_unclear_maps_to_neutral():
    result = extract_existing_solution_from_pm_decision(
        _pm_with_gate(_full_es(solution_type="unclear", has_existing_solution=False))
    )
    assert result["severity"] == "neutral"


# ── Badge label mapping ───────────────────────────────────────────────────────

def test_existing_setting_badge_label():
    result = extract_existing_solution_from_pm_decision(
        _pm_with_gate(_full_es(solution_type="existing_setting"))
    )
    assert result["badge_label"] == "Existing setting"


def test_existing_workaround_badge_label():
    result = extract_existing_solution_from_pm_decision(
        _pm_with_gate(_full_es(solution_type="existing_workaround"))
    )
    assert result["badge_label"] == "Existing workaround"


def test_existing_template_pattern_badge_label():
    result = extract_existing_solution_from_pm_decision(
        _pm_with_gate(_full_es(solution_type="existing_template_pattern"))
    )
    assert result["badge_label"] == "Existing template pattern"


def test_make_editable_badge_label():
    result = extract_existing_solution_from_pm_decision(
        _pm_with_gate(_full_es(solution_type="make_editable"))
    )
    assert result["badge_label"] == "Make editable"


def test_no_existing_solution_badge_label():
    result = extract_existing_solution_from_pm_decision(
        _pm_with_gate(_full_es(
            solution_type="no_existing_solution", has_existing_solution=False
        ))
    )
    assert result["badge_label"] == "No existing solution"


def test_unclear_badge_label():
    result = extract_existing_solution_from_pm_decision(
        _pm_with_gate(_full_es(solution_type="unclear", has_existing_solution=False))
    )
    assert result["badge_label"] == "Unclear"


# ── Defensive: invalid / missing fields ──────────────────────────────────────

def test_missing_confidence_defaults_to_zero():
    es = _full_es()
    del es["confidence"]
    result = extract_existing_solution_from_pm_decision(_pm_with_gate(es))
    assert result["confidence"] == 0.0


def test_none_confidence_defaults_to_zero():
    result = extract_existing_solution_from_pm_decision(
        _pm_with_gate(_full_es(confidence=None))
    )
    assert result["confidence"] == 0.0


def test_none_reason_defaults_to_empty_string():
    result = extract_existing_solution_from_pm_decision(
        _pm_with_gate(_full_es(reason=None))
    )
    assert result["reason"] == ""


def test_none_sources_defaults_to_empty_list():
    result = extract_existing_solution_from_pm_decision(
        _pm_with_gate(_full_es(sources=None))
    )
    assert result["sources"] == []


def test_none_signals_defaults_to_empty_list():
    result = extract_existing_solution_from_pm_decision(
        _pm_with_gate(_full_es(signals=None))
    )
    assert result["signals"] == []


def test_unknown_solution_type_gets_fallback_badge():
    result = extract_existing_solution_from_pm_decision(
        _pm_with_gate(_full_es(solution_type="custom_unknown_type"))
    )
    assert result["badge_label"] != ""
    assert result["severity"] == "neutral"


# ── Does NOT mutate inputs ────────────────────────────────────────────────────

def test_does_not_mutate_pm_decision():
    pm = _pm_with_gate(_full_es())
    original_pm = {"_gate_results": {"existing_solution": dict(pm["_gate_results"]["existing_solution"])}}
    extract_existing_solution_from_pm_decision(pm)
    assert pm["_gate_results"]["existing_solution"] == original_pm["_gate_results"]["existing_solution"]


# ── Acceptance scenario ───────────────────────────────────────────────────────

def test_acceptance_make_editable_full_scenario():
    """PR 17 acceptance scenario.

    PMDecision._gate_results.existing_solution = make_editable with confidence 0.85.
    Expected: has_data=True, badge_label='Make editable', severity='warning',
              reason preserved, sources/signals preserved.
    """
    pm_decision = {
        "_gate_results": {
            "existing_solution": {
                "has_existing_solution": True,
                "solution_type": "make_editable",
                "recommended_action": "make_editable",
                "confidence": 0.85,
                "reason": "Client preference and current behaviour is correct.",
                "sources": ["evidence", "current_behaviour"],
                "signals": {"custom_wording": True, "correct_current_behaviour": True},
            }
        }
    }

    result = extract_existing_solution_from_pm_decision(pm_decision)

    assert result["has_data"] is True, "has_data must be True"
    assert result["badge_label"] == "Make editable", (
        f"Expected 'Make editable', got '{result['badge_label']}'"
    )
    assert result["severity"] == "warning", (
        f"Expected severity='warning', got '{result['severity']}'"
    )
    assert "Client preference" in result["reason"], "reason must be preserved"
    assert "evidence" in result["sources"], "sources must be preserved"
    assert "current_behaviour" in result["sources"], "sources must be preserved"
    assert "custom_wording" in result["signals"], "truthy signals must be in list"
    assert "correct_current_behaviour" in result["signals"], "truthy signals must be in list"
