"""Tests for ai/security_readiness.py — build_security_readiness_report.

Covers:
- empty/None inputs → unknown or needs_attention, no crash
- SECRET_KEY present and strong → pass
- SECRET_KEY missing → warning or fail
- SECRET_KEY default-like → fail
- FLASK_DEBUG=1 → warning or fail
- APP_DEBUG=true → warning or fail
- debug disabled → pass
- API keys present → never appear in report output
- API keys missing → warning, not value
- docs present → pass
- score floor at 0
- secure_enough_for_demo when all required checks pass
- unsafe_for_production when critical fail exists
- function never mutates inputs
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai.security_readiness import build_security_readiness_report

# ── Helpers ───────────────────────────────────────────────────────────────────

_STRONG_KEY = "a-very-long-and-random-xK9mQ2nP7vZ4wL8jR3tY6hF"
_WEAK_KEY   = "change-me"

_GOOD_ENV = {
    "SECRET_KEY": _STRONG_KEY,
    "FLASK_DEBUG": "0",
    "APP_DEBUG":   "0",
    "APP_ENV":     "production",
}

_GOOD_SETTINGS = {
    "llm_api_key":       "sk-test-key",
    "freshdesk_api_key": "fd-test-key",
    "freshdesk_domain":  "example.freshdesk.com",
}


def _report(settings=None, env=None) -> dict:
    return build_security_readiness_report(settings=settings, env=env)


def _check(report: dict, code: str) -> dict | None:
    return next((c for c in report.get("checks", []) if c["code"] == code), None)


# ── 1. Empty / None inputs — no crash ─────────────────────────────────────────

def test_none_inputs_returns_dict():
    r = _report(None, None)
    assert isinstance(r, dict)


def test_none_inputs_status_unknown():
    r = _report(None, None)
    assert r["status"] == "unknown"


def test_empty_dict_inputs_returns_dict():
    r = _report({}, {})
    assert isinstance(r, dict)


def test_empty_dict_has_required_keys():
    r = _report({}, {})
    for key in ("status", "score", "checks", "summary"):
        assert key in r


def test_empty_env_does_not_crash():
    r = _report(settings={}, env={})
    assert r["status"] in ("unknown", "needs_attention", "secure_enough_for_demo",
                           "unsafe_for_production")


def test_settings_only_no_env_does_not_crash():
    r = _report(settings=_GOOD_SETTINGS, env=None)
    assert isinstance(r, dict)


def test_env_only_no_settings_does_not_crash():
    r = _report(settings=None, env=_GOOD_ENV)
    assert isinstance(r, dict)


# ── 2. SECRET_KEY present and strong → pass ───────────────────────────────────

def test_strong_secret_key_passes():
    r = _report(settings={}, env={"SECRET_KEY": _STRONG_KEY})
    c = _check(r, "secret_key_set")
    assert c is not None
    assert c["status"] == "pass"


def test_strong_secret_key_not_default_passes():
    r = _report(settings={}, env={"SECRET_KEY": _STRONG_KEY})
    c = _check(r, "secret_key_not_default")
    assert c is not None
    assert c["status"] == "pass"


def test_strong_secret_key_value_not_in_report():
    r = _report(settings={}, env={"SECRET_KEY": _STRONG_KEY})
    report_str = json.dumps(r)
    assert _STRONG_KEY not in report_str


# ── 3. SECRET_KEY missing → warning or fail ───────────────────────────────────

def test_missing_secret_key_not_pass():
    r = _report(settings={}, env={})
    c = _check(r, "secret_key_set")
    assert c is not None
    assert c["status"] in ("warning", "fail")


def test_missing_secret_key_in_production_fails():
    r = _report(settings={}, env={"APP_ENV": "production"})
    c = _check(r, "secret_key_set")
    assert c is not None
    assert c["status"] == "fail"


def test_missing_secret_key_non_prod_warns():
    r = _report(settings={}, env={})
    c = _check(r, "secret_key_set")
    assert c is not None
    assert c["status"] in ("warning", "fail")


# ── 4. SECRET_KEY default-like → fail ─────────────────────────────────────────

def test_default_secret_key_fails():
    r = _report(settings={}, env={"SECRET_KEY": "change-me"})
    c = _check(r, "secret_key_not_default")
    assert c is not None
    assert c["status"] == "fail"


def test_dev_secret_key_fails():
    r = _report(settings={}, env={"SECRET_KEY": "dev-secret-key"})
    c = _check(r, "secret_key_not_default")
    assert c is not None
    assert c["status"] == "fail"


def test_example_secret_key_fails():
    r = _report(settings={}, env={"SECRET_KEY": "example-value"})
    c = _check(r, "secret_key_not_default")
    assert c is not None
    assert c["status"] == "fail"


def test_short_secret_key_warns():
    r = _report(settings={}, env={"SECRET_KEY": "abc123"})  # < 24 chars
    c = _check(r, "secret_key_not_default")
    assert c is not None
    assert c["status"] in ("warning", "fail")


def test_default_secret_key_value_not_in_report():
    r = _report(settings={}, env={"SECRET_KEY": _WEAK_KEY})
    report_str = json.dumps(r)
    assert _WEAK_KEY not in report_str


# ── 5. FLASK_DEBUG=1 → warning or fail ───────────────────────────────────────

def test_flask_debug_1_not_pass():
    r = _report(settings={}, env={"FLASK_DEBUG": "1"})
    c = _check(r, "flask_debug_disabled")
    assert c is not None
    assert c["status"] in ("warning", "fail")


def test_flask_debug_true_not_pass():
    r = _report(settings={}, env={"FLASK_DEBUG": "true"})
    c = _check(r, "flask_debug_disabled")
    assert c is not None
    assert c["status"] in ("warning", "fail")


def test_flask_debug_1_in_production_fails():
    r = _report(settings={}, env={"FLASK_DEBUG": "1", "APP_ENV": "production"})
    c = _check(r, "flask_debug_disabled")
    assert c is not None
    assert c["status"] == "fail"


# ── 6. APP_DEBUG=true → warning or fail ──────────────────────────────────────

def test_app_debug_true_not_pass():
    r = _report(settings={}, env={"APP_DEBUG": "true"})
    c = _check(r, "flask_debug_disabled")
    assert c is not None
    assert c["status"] in ("warning", "fail")


def test_app_debug_1_not_pass():
    r = _report(settings={}, env={"APP_DEBUG": "1"})
    c = _check(r, "flask_debug_disabled")
    assert c is not None
    assert c["status"] in ("warning", "fail")


# ── 7. Debug disabled → pass ─────────────────────────────────────────────────

def test_flask_debug_0_passes():
    r = _report(settings={}, env={"FLASK_DEBUG": "0"})
    c = _check(r, "flask_debug_disabled")
    assert c is not None
    assert c["status"] == "pass"


def test_flask_debug_false_passes():
    r = _report(settings={}, env={"FLASK_DEBUG": "false"})
    c = _check(r, "flask_debug_disabled")
    assert c is not None
    assert c["status"] == "pass"


def test_no_debug_env_passes():
    r = _report(settings={}, env={})
    c = _check(r, "flask_debug_disabled")
    assert c is not None
    assert c["status"] == "pass"


# ── 8. API keys present → value never in report ──────────────────────────────

def test_llm_api_key_value_not_in_report():
    secret = "sk-super-secret-llm-key"
    r = _report(settings={"llm_api_key": secret}, env={})
    report_str = json.dumps(r)
    assert secret not in report_str


def test_freshdesk_api_key_value_not_in_report():
    secret = "fd-super-secret-freshdesk-key"
    r = _report(settings={"freshdesk_api_key": secret}, env={})
    report_str = json.dumps(r)
    assert secret not in report_str


def test_llm_api_key_present_passes_check():
    r = _report(settings={"llm_api_key": "sk-test"}, env={})
    c = _check(r, "llm_api_key_not_exposed")
    assert c is not None
    assert c["status"] == "pass"


def test_freshdesk_api_key_present_passes_check():
    r = _report(settings={"freshdesk_api_key": "fd-test"}, env={})
    c = _check(r, "freshdesk_api_key_not_exposed")
    assert c is not None
    assert c["status"] == "pass"


# ── 9. API keys missing → warning, not value ─────────────────────────────────

def test_llm_api_key_missing_warns():
    r = _report(settings={}, env={})
    c = _check(r, "llm_api_key_not_exposed")
    assert c is not None
    assert c["status"] in ("warning", "fail")


def test_freshdesk_api_key_missing_warns():
    r = _report(settings={}, env={})
    c = _check(r, "freshdesk_api_key_not_exposed")
    assert c is not None
    assert c["status"] in ("warning", "fail")


# ── 10. Docs present checks ──────────────────────────────────────────────────

def test_production_checklist_check_exists():
    r = _report(settings={}, env={})
    c = _check(r, "production_checklist_present")
    assert c is not None


def test_live_demo_smoke_test_check_exists():
    r = _report(settings={}, env={})
    c = _check(r, "live_demo_smoke_test_present")
    assert c is not None


def test_docs_present_when_files_exist(tmp_path, monkeypatch):
    """If the docs files exist, checks should pass."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "PRODUCTION_CHECKLIST.md").write_text("checklist content")
    (tmp_path / "docs" / "LIVE_DEMO_SMOKE_TEST.md").write_text("smoke test content")
    monkeypatch.chdir(tmp_path)
    r = _report(settings={}, env={})
    c1 = _check(r, "production_checklist_present")
    c2 = _check(r, "live_demo_smoke_test_present")
    assert c1 is not None and c1["status"] == "pass"
    assert c2 is not None and c2["status"] == "pass"


# ── 11. Score floor at 0 ──────────────────────────────────────────────────────

def test_score_floor_zero():
    """Worst possible env should not produce a negative score."""
    worst_env = {
        "SECRET_KEY": "",
        "FLASK_DEBUG": "1",
        "APP_ENV": "production",
    }
    r = _report(settings={}, env=worst_env)
    assert r["score"] >= 0


def test_score_type_is_int():
    r = _report(settings={}, env={})
    assert isinstance(r["score"], int)


def test_score_max_100():
    r = _report(settings=_GOOD_SETTINGS, env=_GOOD_ENV)
    assert r["score"] <= 100


# ── 12. secure_enough_for_demo ───────────────────────────────────────────────

def test_secure_enough_for_demo_status():
    r = _report(settings=_GOOD_SETTINGS, env=_GOOD_ENV)
    # With all good inputs the status should be secure enough or better
    assert r["status"] in ("secure_enough_for_demo",)


def test_secure_enough_for_demo_score_ge_80():
    r = _report(settings=_GOOD_SETTINGS, env=_GOOD_ENV)
    # Status secure_enough_for_demo requires score >= 80
    if r["status"] == "secure_enough_for_demo":
        assert r["score"] >= 80


# ── 13. unsafe_for_production when critical fail ──────────────────────────────

def test_unsafe_for_production_when_critical_fail():
    env = {
        "SECRET_KEY": "change-me",   # weak default → critical fail
        "APP_ENV": "production",
        "FLASK_DEBUG": "0",
    }
    r = _report(settings=_GOOD_SETTINGS, env=env)
    assert r["status"] in ("unsafe_for_production", "needs_attention")


def test_debug_in_production_triggers_unsafe():
    env = {
        "SECRET_KEY": _STRONG_KEY,
        "FLASK_DEBUG": "1",
        "APP_ENV": "production",
    }
    r = _report(settings=_GOOD_SETTINGS, env=env)
    assert r["status"] in ("unsafe_for_production", "needs_attention")


# ── 14. Function never mutates inputs ────────────────────────────────────────

def test_does_not_mutate_settings():
    settings = {"llm_api_key": "sk-test", "freshdesk_api_key": "fd-test"}
    original_settings = dict(settings)
    _report(settings=settings, env={})
    assert settings == original_settings


def test_does_not_mutate_env():
    env = {"SECRET_KEY": _STRONG_KEY, "FLASK_DEBUG": "0"}
    original_env = dict(env)
    _report(settings={}, env=env)
    assert env == original_env


# ── 15. Summary dict structure ───────────────────────────────────────────────

def test_summary_has_all_keys():
    r = _report(settings={}, env={})
    summary = r.get("summary", {})
    for key in ("pass_count", "warning_count", "fail_count", "unknown_count"):
        assert key in summary, f"Missing summary key: {key}"


def test_summary_counts_are_non_negative():
    r = _report(settings={}, env={})
    summary = r["summary"]
    for k, v in summary.items():
        assert v >= 0, f"{k} should be non-negative"


def test_summary_counts_match_checks():
    r = _report(settings=_GOOD_SETTINGS, env=_GOOD_ENV)
    checks = r["checks"]
    summary = r["summary"]
    assert summary["pass_count"]    == sum(1 for c in checks if c["status"] == "pass")
    assert summary["warning_count"] == sum(1 for c in checks if c["status"] == "warning")
    assert summary["fail_count"]    == sum(1 for c in checks if c["status"] == "fail")
    assert summary["unknown_count"] == sum(1 for c in checks if c["status"] == "unknown")


# ── 16. Check structure ──────────────────────────────────────────────────────

def test_each_check_has_required_fields():
    r = _report(settings=_GOOD_SETTINGS, env=_GOOD_ENV)
    for c in r["checks"]:
        for field in ("code", "status", "severity", "title", "message"):
            assert field in c, f"Check {c.get('code')} missing field {field}"


def test_check_statuses_are_valid():
    r = _report(settings=_GOOD_SETTINGS, env=_GOOD_ENV)
    valid = {"pass", "warning", "fail", "unknown"}
    for c in r["checks"]:
        assert c["status"] in valid, f"Invalid status '{c['status']}' for {c['code']}"


def test_check_severities_are_valid():
    r = _report(settings=_GOOD_SETTINGS, env=_GOOD_ENV)
    valid = {"critical", "warning", "info"}
    for c in r["checks"]:
        assert c["severity"] in valid, f"Invalid severity '{c['severity']}' for {c['code']}"


# ── 17. Counter scenario ─────────────────────────────────────────────────────

def test_counter_scenario_weak_key_and_debug():
    """Counter scenario from the PR spec."""
    env = {"SECRET_KEY": "change-me", "FLASK_DEBUG": "1"}
    r = _report(settings={}, env=env)
    assert r["status"] in ("unsafe_for_production", "needs_attention")
    # Reasons must mention something without printing the key value
    report_str = json.dumps(r)
    assert "change-me" not in report_str
    # Should flag weak key
    c_weak = _check(r, "secret_key_not_default")
    assert c_weak is not None and c_weak["status"] in ("warning", "fail")
    # Should flag debug
    c_debug = _check(r, "flask_debug_disabled")
    assert c_debug is not None and c_debug["status"] in ("warning", "fail")


# ── 18. Acceptance scenario ──────────────────────────────────────────────────

def test_acceptance_scenario_good_env():
    """Acceptance scenario from the PR spec."""
    env = {
        "SECRET_KEY": "a-strong-random-value-with-enough-length",
        "FLASK_DEBUG": "0",
        "APP_ENV":     "production",
    }
    settings = {
        "llm_api_key":       "sk-super-secret",
        "freshdesk_api_key": "fd-secret",
        "freshdesk_domain":  "silverfin.freshdesk.com",
    }
    r = _report(settings=settings, env=env)
    assert r["status"] in ("secure_enough_for_demo",)
    assert r["score"] >= 80
    # No secret values in output
    report_str = json.dumps(r)
    assert "sk-super-secret" not in report_str
    assert "fd-secret" not in report_str
    assert "a-strong-random-value-with-enough-length" not in report_str
    # Debug and secret key checks pass
    assert _check(r, "flask_debug_disabled")["status"] == "pass"
    assert _check(r, "secret_key_set")["status"] == "pass"
    assert _check(r, "secret_key_not_default")["status"] == "pass"
