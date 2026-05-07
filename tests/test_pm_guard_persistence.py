"""Tests for ai/pm_guard_persistence helpers."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.pm_guard_persistence import (
    apply_pm_guard_and_collect,
    merge_pm_guard_warnings_into_qa_issues,
)


# ── apply_pm_guard_and_collect ────────────────────────────────────────────────

_MAKE_EDITABLE_DEC = {
    "recommended_action": "make_editable",
    "should_mention_law": False,
    "global_change_risk": "high",
    "needs_prd": False,
    "development_type": "unclear",
}

_LEGAL_OUTPUT = "The Law of 1915 governs this. Please note Article 12 applies."
_GLOBAL_OUTPUT = "We should change the default globally for all clients."
_CLEAN_OUTPUT = "We can make this field configurable per client."


def test_empty_pm_decision_returns_original():
    out, warnings = apply_pm_guard_and_collect("Some draft.", {})
    assert out == "Some draft."
    assert warnings == []


def test_none_pm_decision_returns_original():
    out, warnings = apply_pm_guard_and_collect("Some draft.", None)
    assert out == "Some draft."
    assert warnings == []


def test_empty_output_returns_empty():
    out, warnings = apply_pm_guard_and_collect("", _MAKE_EDITABLE_DEC)
    assert out == ""
    assert warnings == []


def test_legal_reference_warning_collected():
    out, warnings = apply_pm_guard_and_collect(_LEGAL_OUTPUT, _MAKE_EDITABLE_DEC)
    codes = {w["code"] for w in warnings}
    assert "legal_reference_blocked" in codes


def test_global_default_warning_collected():
    out, warnings = apply_pm_guard_and_collect(_GLOBAL_OUTPUT, _MAKE_EDITABLE_DEC)
    codes = {w["code"] for w in warnings}
    assert "global_default_change_blocked" in codes


def test_editability_missing_warning_when_no_editable_mention():
    # Output does not mention 'editable' or 'configurable'
    output = "The field works as expected."
    out, warnings = apply_pm_guard_and_collect(output, _MAKE_EDITABLE_DEC)
    codes = {w["code"] for w in warnings}
    assert "editability_missing" in codes


def test_no_warnings_for_compliant_output():
    out, warnings = apply_pm_guard_and_collect(_CLEAN_OUTPUT, _MAKE_EDITABLE_DEC)
    # Clean output is configurable per client → no editability_missing
    # No legal refs, no global default → minimal or zero warnings
    editable_warn = [w for w in warnings if w["code"] == "editability_missing"]
    assert editable_warn == [], "Compliant output must not trigger editability_missing"


def test_guarded_output_contains_marker_when_violation():
    out, warnings = apply_pm_guard_and_collect(_LEGAL_OUTPUT, _MAKE_EDITABLE_DEC)
    assert "[PM guard:" in out


def test_warnings_have_required_keys():
    _, warnings = apply_pm_guard_and_collect(_LEGAL_OUTPUT, _MAKE_EDITABLE_DEC)
    assert len(warnings) > 0
    for w in warnings:
        for key in ("code", "severity", "title", "message", "raw"):
            assert key in w, f"Missing key '{key}' in warning dict"


def test_does_not_raise_on_invalid_pm_decision():
    # Deliberately broken decision dict — should not crash
    out, warnings = apply_pm_guard_and_collect("Some draft.", {"bad_key": object()})
    assert isinstance(out, str)
    assert isinstance(warnings, list)


# ── merge_pm_guard_warnings_into_qa_issues ───────────────────────────────────

_RAW_LEGAL = "[PM guard: legal reference detected although PM decision says should_mention_law=false.]"
_RAW_GLOBAL = "[PM guard: global default change suggested although global_change_risk=high.]"
_RAW_EDITABLE = "[PM guard: recommended_action=make_editable but output does not mention editability/configurability.]"


def _w(raw: str, code: str = "unknown") -> dict:
    return {"code": code, "severity": "medium", "title": code, "message": "", "raw": raw}


def test_merge_empty_existing_returns_valid_json():
    result = merge_pm_guard_warnings_into_qa_issues("", [_w(_RAW_LEGAL)])
    parsed = json.loads(result)
    assert isinstance(parsed, list)
    assert _RAW_LEGAL in parsed


def test_merge_none_existing_returns_valid_json():
    result = merge_pm_guard_warnings_into_qa_issues(None, [_w(_RAW_LEGAL)])
    parsed = json.loads(result)
    assert _RAW_LEGAL in parsed


def test_merge_preserves_existing_entries():
    existing = json.dumps(["existing issue 1", "existing issue 2"])
    result = merge_pm_guard_warnings_into_qa_issues(existing, [_w(_RAW_LEGAL)])
    parsed = json.loads(result)
    assert "existing issue 1" in parsed
    assert "existing issue 2" in parsed
    assert _RAW_LEGAL in parsed


def test_merge_existing_list_input():
    existing = ["existing issue"]
    result = merge_pm_guard_warnings_into_qa_issues(existing, [_w(_RAW_GLOBAL)])
    parsed = json.loads(result)
    assert "existing issue" in parsed
    assert _RAW_GLOBAL in parsed


def test_merge_invalid_json_does_not_crash():
    result = merge_pm_guard_warnings_into_qa_issues("not valid json {{{", [_w(_RAW_LEGAL)])
    parsed = json.loads(result)
    assert isinstance(parsed, list)
    assert _RAW_LEGAL in parsed


def test_merge_deduplicates_warnings():
    """Same raw marker already in existing — should not be added again."""
    existing = json.dumps([_RAW_LEGAL])
    result = merge_pm_guard_warnings_into_qa_issues(existing, [_w(_RAW_LEGAL)])
    parsed = json.loads(result)
    assert parsed.count(_RAW_LEGAL) == 1


def test_merge_deduplicates_multiple_warnings():
    warnings = [_w(_RAW_LEGAL), _w(_RAW_LEGAL), _w(_RAW_GLOBAL)]
    result = merge_pm_guard_warnings_into_qa_issues("", warnings)
    parsed = json.loads(result)
    assert parsed.count(_RAW_LEGAL) == 1
    assert parsed.count(_RAW_GLOBAL) == 1


def test_merge_caps_at_ten_items():
    existing = json.dumps([f"issue {i}" for i in range(9)])
    warnings = [_w(_RAW_LEGAL), _w(_RAW_GLOBAL), _w(_RAW_EDITABLE)]
    result = merge_pm_guard_warnings_into_qa_issues(existing, warnings)
    parsed = json.loads(result)
    assert len(parsed) <= 10


def test_merge_returns_json_string():
    result = merge_pm_guard_warnings_into_qa_issues("", [])
    assert isinstance(result, str)
    json.loads(result)  # must not raise


def test_merge_empty_warnings_list_preserves_existing():
    existing = json.dumps(["existing item"])
    result = merge_pm_guard_warnings_into_qa_issues(existing, [])
    parsed = json.loads(result)
    assert "existing item" in parsed


def test_merge_warning_with_empty_raw_ignored():
    result = merge_pm_guard_warnings_into_qa_issues("", [{"code": "x", "raw": ""}])
    parsed = json.loads(result)
    assert parsed == []


# ── Acceptance scenario ────────────────────────────────────────────────────────

def test_acceptance_full_pipeline():
    """PMDecision with make_editable + should_mention_law=False + global_change_risk=high.

    Output: "The Law of 1915 requires this. We should change the default globally."

    Expected:
    - legal_reference_blocked warning
    - global_default_change_blocked warning
    - editability_missing warning (output does not mention editable/configurable)
    - merge produces valid JSON containing those raw markers
    """
    pm_decision = {
        "recommended_action": "make_editable",
        "should_mention_law": False,
        "global_change_risk": "high",
        "needs_prd": False,
        "development_type": "unclear",
    }
    output = "The Law of 1915 requires this. We should change the default globally."

    guarded, warnings = apply_pm_guard_and_collect(output, pm_decision)

    codes = {w["code"] for w in warnings}
    assert "legal_reference_blocked" in codes, f"Expected legal warning, got codes: {codes}"
    assert "global_default_change_blocked" in codes, f"Expected global warning, got codes: {codes}"
    assert "editability_missing" in codes, f"Expected editable warning, got codes: {codes}"

    merged = merge_pm_guard_warnings_into_qa_issues("[]", warnings)
    parsed = json.loads(merged)
    assert isinstance(parsed, list)
    assert len(parsed) >= 3

    raws = set(parsed)
    assert any("legal reference" in r for r in raws)
    assert any("global default" in r for r in raws)
    assert any("make_editable" in r for r in raws)
