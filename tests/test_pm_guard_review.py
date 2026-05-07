"""Tests for pm_guard_review categorizer."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.pm_guard_review import categorize_pm_guard_warning, categorize_pm_guard_warnings


# ── Single warning categorization ────────────────────────────────────────────

def test_legal_reference_is_high_severity():
    w = "[PM guard: legal reference detected although PM decision says should_mention_law=false.]"
    result = categorize_pm_guard_warning(w)
    assert result["code"] == "legal_reference_blocked"
    assert result["severity"] == "high"
    assert result["raw"] == w


def test_global_default_change_is_high_severity():
    w = "[PM guard: global default change suggested although global_change_risk=high.]"
    result = categorize_pm_guard_warning(w)
    assert result["code"] == "global_default_change_blocked"
    assert result["severity"] == "high"
    assert result["raw"] == w


def test_editability_missing_is_medium_severity():
    w = "[PM guard: recommended_action=make_editable but output does not mention editability/configurability.]"
    result = categorize_pm_guard_warning(w)
    assert result["code"] == "editability_missing"
    assert result["severity"] == "medium"
    assert result["raw"] == w


def test_bug_framed_as_feature_is_high_severity():
    w = "[PM guard: bug_fix decision may have been framed as a feature request.]"
    result = categorize_pm_guard_warning(w)
    assert result["code"] == "bug_framed_as_feature"
    assert result["severity"] == "high"
    assert result["raw"] == w


def test_support_escalated_is_medium_severity():
    w = "[PM guard: support guidance decision may have been escalated to development.]"
    result = categorize_pm_guard_warning(w)
    assert result["code"] == "support_escalated_to_dev"
    assert result["severity"] == "medium"
    assert result["raw"] == w


def test_prd_style_blocked_is_medium():
    w = "[PM guard: PRD-style output detected although PM decision says needs_prd=false.]"
    result = categorize_pm_guard_warning(w)
    assert result["code"] == "prd_style_blocked"
    assert result["severity"] == "medium"


def test_output_too_long_is_low():
    w = "[PM guard: output is 400 words; recommended max is 200. Manual review required.]"
    result = categorize_pm_guard_warning(w)
    assert result["code"] == "output_too_long"
    assert result["severity"] == "low"


def test_unknown_warning_is_low():
    w = "[PM guard: some completely unrecognised message here.]"
    result = categorize_pm_guard_warning(w)
    assert result["code"] == "unknown"
    assert result["severity"] == "low"
    assert result["raw"] == w


def test_empty_string_is_unknown_low():
    result = categorize_pm_guard_warning("")
    assert result["code"] == "unknown"
    assert result["severity"] == "low"


def test_none_is_unknown_low():
    result = categorize_pm_guard_warning(None)
    assert result["code"] == "unknown"
    assert result["severity"] == "low"


# ── List categorization ───────────────────────────────────────────────────────

def test_categorize_list_preserves_raw():
    warnings = [
        "[PM guard: legal reference detected although PM decision says should_mention_law=false.]",
        "[PM guard: global default change suggested although global_change_risk=high.]",
    ]
    results = categorize_pm_guard_warnings(warnings)
    assert len(results) == 2
    assert results[0]["raw"] == warnings[0]
    assert results[1]["raw"] == warnings[1]


def test_categorize_list_skips_empty_items():
    warnings = [
        "[PM guard: legal reference detected although PM decision says should_mention_law=false.]",
        "",
        None,
    ]
    results = categorize_pm_guard_warnings(warnings)
    assert len(results) == 1
    assert results[0]["code"] == "legal_reference_blocked"


def test_categorize_empty_list_returns_empty():
    assert categorize_pm_guard_warnings([]) == []


def test_categorize_none_returns_empty():
    assert categorize_pm_guard_warnings(None) == []


def test_all_required_keys_present():
    w = "[PM guard: legal reference detected although PM decision says should_mention_law=false.]"
    result = categorize_pm_guard_warning(w)
    for key in ("code", "severity", "title", "message", "raw"):
        assert key in result, f"Missing key: {key}"


# ── Acceptance scenario ───────────────────────────────────────────────────────

def test_acceptance_three_warnings_categorized():
    """Three typical guard markers → correct codes, severities, and preserved raws."""
    raw_warnings = [
        "[PM guard: legal reference detected although PM decision says should_mention_law=false.]",
        "[PM guard: global default change suggested although global_change_risk=high.]",
        "[PM guard: recommended_action=make_editable but output does not mention editability/configurability.]",
    ]
    results = categorize_pm_guard_warnings(raw_warnings)

    assert len(results) == 3

    assert results[0]["code"] == "legal_reference_blocked"
    assert results[0]["severity"] == "high"
    assert results[0]["raw"] == raw_warnings[0]

    assert results[1]["code"] == "global_default_change_blocked"
    assert results[1]["severity"] == "high"
    assert results[1]["raw"] == raw_warnings[1]

    assert results[2]["code"] == "editability_missing"
    assert results[2]["severity"] == "medium"
    assert results[2]["raw"] == raw_warnings[2]
