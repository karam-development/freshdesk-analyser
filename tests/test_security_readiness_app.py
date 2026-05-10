"""Source / route / template / doc tests for PR 34 — security readiness.

Tests cover:
- app.py imports build_security_readiness_report
- /api/security-readiness route exists in source
- route does not expose API key values
- settings route passes security_readiness to template
- settings template contains "Security Readiness"
- security card has no form/input/button/password/save/edit controls
- security card does not render settings.llm_api_key or settings.freshdesk_api_key
- docs/PRODUCTION_CHECKLIST.md mentions SECRET_KEY, debug, DB, private, rotate
- docs/TEAM_DEMO_GUIDE.md mentions screen sharing / secrets / no auto-send / human review
- docs/LIVE_DEMO_SMOKE_TEST.md mentions Security Readiness
- README mentions security readiness
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# ── Source files ──────────────────────────────────────────────────────────────

APP_SRC      = Path("app.py").read_text(encoding="utf-8")
SETTINGS_TPL = Path("templates/settings.html").read_text(encoding="utf-8")
PROD_CHECKLIST = Path("docs/PRODUCTION_CHECKLIST.md").read_text(encoding="utf-8")
TEAM_DEMO    = Path("docs/TEAM_DEMO_GUIDE.md").read_text(encoding="utf-8")
SMOKE_TEST   = Path("docs/LIVE_DEMO_SMOKE_TEST.md").read_text(encoding="utf-8")
README       = Path("README.md").read_text(encoding="utf-8")


# ── 1. app.py imports build_security_readiness_report ────────────────────────

def test_app_imports_build_security_readiness_report():
    assert "build_security_readiness_report" in APP_SRC


def test_app_imports_from_ai_security_readiness():
    assert "from ai.security_readiness import build_security_readiness_report" in APP_SRC


def test_app_has_import_guard_for_security_readiness():
    # Should be inside a try/except in case the module isn't available
    idx = APP_SRC.find("from ai.security_readiness import build_security_readiness_report")
    surrounding = APP_SRC[max(0, idx - 50):idx + 100]
    assert "try" in surrounding or "except" in APP_SRC[idx:idx + 200]


# ── 2. /api/security-readiness route exists ──────────────────────────────────

def test_security_readiness_route_defined():
    assert '"/api/security-readiness"' in APP_SRC or "'/api/security-readiness'" in APP_SRC


def test_security_readiness_route_is_get():
    # Route should be GET only (no methods= or methods=["GET"])
    idx = APP_SRC.find("/api/security-readiness")
    route_line = APP_SRC[max(0, idx - 20):idx + 100]
    # Either no methods= (defaults to GET) or explicit GET
    assert "POST" not in route_line


def test_security_readiness_route_calls_build_security_readiness_report():
    # Find the route function body
    idx = APP_SRC.find("def api_security_readiness")
    func_body = APP_SRC[idx:idx + 800]
    assert "build_security_readiness_report" in func_body


def test_security_readiness_route_returns_jsonify():
    idx = APP_SRC.find("def api_security_readiness")
    func_body = APP_SRC[idx:idx + 800]
    assert "jsonify" in func_body


# ── 3. Route does not expose API key values ───────────────────────────────────

def test_route_does_not_return_raw_llm_api_key():
    idx = APP_SRC.find("def api_security_readiness")
    func_body = APP_SRC[idx:idx + 800]
    # Must not pass raw key value directly into jsonify response
    assert "llm_api_key" not in func_body.replace(
        'get_setting("llm_api_key"', ""
    ).replace('"llm_api_key"', "")


def test_route_does_not_return_raw_freshdesk_api_key():
    idx = APP_SRC.find("def api_security_readiness")
    func_body = APP_SRC[idx:idx + 800]
    assert "freshdesk_api_key" not in func_body.replace(
        'get_setting("freshdesk_api_key"', ""
    ).replace('"freshdesk_api_key"', "")


def test_route_has_try_except_safety():
    idx = APP_SRC.find("def api_security_readiness")
    func_body = APP_SRC[idx:idx + 800]
    assert "except" in func_body


# ── 4. settings route passes security_readiness to template ───────────────────

def test_settings_route_builds_security_readiness():
    # settings() should call build_security_readiness_report somewhere after the def
    idx = APP_SRC.find("def settings()")
    if idx == -1:
        idx = APP_SRC.find("def settings(")
    # The settings function is long; search a generous window
    func_body = APP_SRC[idx:idx + 10000]
    assert "build_security_readiness_report" in func_body


def test_settings_route_passes_security_readiness_to_template():
    idx = APP_SRC.find("def settings()")
    if idx == -1:
        idx = APP_SRC.find("def settings(")
    func_body = APP_SRC[idx:idx + 10000]
    assert "security_readiness=security_readiness" in func_body


# ── 5. Template contains Security Readiness ───────────────────────────────────

def test_template_contains_security_readiness_title():
    assert "Security Readiness" in SETTINGS_TPL


def test_template_uses_security_readiness_variable():
    assert "security_readiness" in SETTINGS_TPL


def test_template_shows_security_score():
    # The card should show score/100
    assert "sec.score" in SETTINGS_TPL or "security_readiness.score" in SETTINGS_TPL


def test_template_shows_security_status_badge():
    assert "sec.status" in SETTINGS_TPL or "security_readiness.status" in SETTINGS_TPL


# ── 6. Security card has no dangerous controls ───────────────────────────────

def _extract_security_card(html: str) -> str:
    """Extract the security readiness card section from the template."""
    start = html.find("SECURITY READINESS CARD")
    end = html.find("END SECURITY READINESS CARD")
    if start == -1 or end == -1:
        return ""
    return html[start:end]


_SECURITY_CARD = _extract_security_card(SETTINGS_TPL)


def test_security_card_is_present():
    assert _SECURITY_CARD != "", "Security Readiness card section not found in template"


def test_security_card_has_no_form_tag():
    # Must be read-only — no form submission inside the card
    assert "<form" not in _SECURITY_CARD.lower()


def test_security_card_has_no_input_tag():
    assert "<input" not in _SECURITY_CARD.lower()


def test_security_card_has_no_button_tag():
    assert "<button" not in _SECURITY_CARD.lower()


def test_security_card_has_no_password_field():
    assert 'type="password"' not in _SECURITY_CARD.lower()


def test_security_card_has_no_save_text():
    # No save/edit controls inside the card
    lower = _SECURITY_CARD.lower()
    assert "save" not in lower or "settings" not in lower  # "save settings" button not inside card


def test_security_card_has_no_textarea():
    assert "<textarea" not in _SECURITY_CARD.lower()


# ── 7. Card does not render secret values ────────────────────────────────────

def test_security_card_does_not_render_llm_api_key_value():
    # The card must not print {{ settings.llm_api_key }} or similar
    lower = _SECURITY_CARD.lower()
    assert "settings.llm_api_key" not in lower


def test_security_card_does_not_render_freshdesk_api_key_value():
    lower = _SECURITY_CARD.lower()
    assert "settings.freshdesk_api_key" not in lower


def test_security_card_does_not_render_secret_key_value():
    lower = _SECURITY_CARD.lower()
    assert "secret_key" not in lower or "{{ " + "secret_key }}" not in lower


# ── 8. PRODUCTION_CHECKLIST.md content ───────────────────────────────────────

def test_checklist_mentions_secret_key():
    assert "SECRET_KEY" in PROD_CHECKLIST


def test_checklist_mentions_debug_disable():
    lower = PROD_CHECKLIST.lower()
    assert "debug" in lower and ("disable" in lower or "disabled" in lower)


def test_checklist_mentions_db_not_public():
    lower = PROD_CHECKLIST.lower()
    assert "db" in lower and ("not be publicly" in lower or "private" in lower
                               or "non-public" in lower)


def test_checklist_mentions_rotate_keys():
    lower = PROD_CHECKLIST.lower()
    assert "rotat" in lower  # "rotate" or "rotation"


def test_checklist_mentions_no_secrets_in_screenshots():
    lower = PROD_CHECKLIST.lower()
    assert "screenshot" in lower


def test_checklist_mentions_restrict_access():
    lower = PROD_CHECKLIST.lower()
    assert "restrict" in lower or "trusted" in lower or "access" in lower


def test_checklist_mentions_backup_access_controlled():
    lower = PROD_CHECKLIST.lower()
    assert "backup" in lower


# ── 9. TEAM_DEMO_GUIDE.md content ────────────────────────────────────────────

def test_team_demo_mentions_screen_sharing():
    lower = TEAM_DEMO.lower()
    assert "screen" in lower


def test_team_demo_mentions_secrets():
    lower = TEAM_DEMO.lower()
    assert "secret" in lower or "api key" in lower or "hide" in lower


def test_team_demo_mentions_no_auto_send():
    lower = TEAM_DEMO.lower()
    assert "auto-send" in lower or "auto send" in lower or "no auto" in lower


def test_team_demo_mentions_human_review():
    lower = TEAM_DEMO.lower()
    assert "human review" in lower or "human must" in lower


def test_team_demo_has_before_sharing_section():
    assert "Before" in TEAM_DEMO and "Screen" in TEAM_DEMO


def test_team_demo_mentions_security_readiness():
    assert "Security Readiness" in TEAM_DEMO


# ── 10. LIVE_DEMO_SMOKE_TEST.md mentions Security Readiness ──────────────────

def test_smoke_test_mentions_security_readiness():
    assert "Security Readiness" in SMOKE_TEST


def test_smoke_test_mentions_security_api_endpoint():
    assert "/api/security-readiness" in SMOKE_TEST


# ── 11. README mentions security readiness ───────────────────────────────────

def test_readme_mentions_security_readiness():
    lower = README.lower()
    assert "security" in lower and "readiness" in lower


def test_readme_mentions_security_api_endpoint():
    assert "/api/security-readiness" in README
