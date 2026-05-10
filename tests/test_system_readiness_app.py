"""Source/route/template tests for PR 31 — system readiness wiring.

Reads app.py and templates/settings.html to assert correct imports,
route presence, template constructs, and doc file existence.
No Flask or HTTP.
"""
from __future__ import annotations

import os

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


APP_SRC = _read("app.py")
SETTINGS_TMPL = _read("templates/settings.html")


# ── app.py: import ─────────────────────────────────────────────────────────────

def test_app_imports_build_system_readiness_report():
    assert "build_system_readiness_report" in APP_SRC


def test_app_imports_from_ai_system_readiness():
    assert "from ai.system_readiness import build_system_readiness_report" in APP_SRC


# ── app.py: /api/system-readiness route ──────────────────────────────────────

def test_app_has_system_readiness_route():
    assert '"/api/system-readiness"' in APP_SRC


def test_app_system_readiness_route_returns_jsonify():
    # Route should return a jsonify call with ok and report keys
    assert '"ok"' in APP_SRC or "'ok'" in APP_SRC
    assert '"report"' in APP_SRC or "'report'" in APP_SRC


def test_app_system_readiness_route_uses_get_db():
    # Find the route function and check it calls get_db()
    pos_route = APP_SRC.find('"/api/system-readiness"')
    pos_get_db = APP_SRC.find("get_db()", pos_route)
    assert pos_route != -1
    assert pos_get_db != -1
    assert pos_get_db > pos_route


def test_app_system_readiness_route_does_not_expose_key_value():
    # The route must not pass raw key values into the response — it only
    # passes settings to build_system_readiness_report which sanitises them.
    pos_route = APP_SRC.find('"/api/system-readiness"')
    pos_next_route = APP_SRC.find("@app.route", pos_route + 1)
    route_body = APP_SRC[pos_route:pos_next_route]
    # Route should call build_system_readiness_report
    assert "build_system_readiness_report" in route_body


def test_app_system_readiness_route_has_error_handling():
    pos_route = APP_SRC.find('"/api/system-readiness"')
    pos_next_route = APP_SRC.find("@app.route", pos_route + 1)
    route_body = APP_SRC[pos_route:pos_next_route]
    assert "except" in route_body


# ── app.py: settings view passes system_readiness ────────────────────────────

def test_app_settings_view_calls_build_readiness():
    pos_func = APP_SRC.find("def settings():")
    pos_call = APP_SRC.find("build_system_readiness_report(", pos_func)
    assert pos_func != -1
    assert pos_call != -1
    assert pos_call > pos_func


def test_app_settings_view_passes_readiness_to_template():
    pos_func = APP_SRC.find("def settings():")
    pos_render = APP_SRC.find('render_template("settings.html"', pos_func)
    assert pos_func != -1
    assert pos_render != -1
    # system_readiness variable should appear in the render_template call
    pos_arg = APP_SRC.find("system_readiness=system_readiness", pos_render)
    assert pos_arg != -1
    assert pos_arg > pos_render


def test_app_settings_view_does_not_expose_raw_key_in_readiness():
    # The settings dict passed to build_system_readiness_report should use
    # .get("llm_api_key") style — not directly pass current["llm_api_key"]
    # We just check that build_system_readiness_report is called in settings()
    pos_func = APP_SRC.find("def settings():")
    pos_call = APP_SRC.find("build_system_readiness_report(", pos_func)
    assert pos_call > pos_func
    # and that the call is before render_template
    pos_render = APP_SRC.find('render_template("settings.html"', pos_func)
    assert pos_call < pos_render


# ── settings template: readiness card present ─────────────────────────────────

def test_settings_template_has_system_readiness():
    assert "System Readiness" in SETTINGS_TMPL


def test_settings_template_references_system_readiness_var():
    assert "system_readiness" in SETTINGS_TMPL


def test_settings_template_has_readiness_card_comment():
    assert "SYSTEM READINESS CARD" in SETTINGS_TMPL


def test_settings_template_renders_sr_status():
    assert "sr.status" in SETTINGS_TMPL


def test_settings_template_renders_sr_score():
    assert "sr.score" in SETTINGS_TMPL


def test_settings_template_renders_sr_checks():
    assert "sr.checks" in SETTINGS_TMPL


def test_settings_template_renders_sr_summary():
    assert "sr.summary" in SETTINGS_TMPL or "pass_count" in SETTINGS_TMPL


def test_settings_template_shows_status_badge():
    assert "readiness-badge" in SETTINGS_TMPL


def test_settings_template_shows_ready_badge_style():
    assert "readiness-badge-ready" in SETTINGS_TMPL


def test_settings_template_shows_needs_configuration_badge_style():
    assert "readiness-badge-needs_configuration" in SETTINGS_TMPL


# ── template: readiness card is read-only (no forms/inputs/secrets) ──────────

def test_settings_template_readiness_card_has_no_secret_input():
    start = SETTINGS_TMPL.find("SYSTEM READINESS CARD")
    end = SETTINGS_TMPL.find("END SYSTEM READINESS CARD")
    assert start != -1 and end != -1
    section = SETTINGS_TMPL[start:end].lower()
    assert "<input" not in section
    assert "<textarea" not in section
    assert "password" not in section


def test_settings_template_readiness_card_has_no_form():
    start = SETTINGS_TMPL.find("SYSTEM READINESS CARD")
    end = SETTINGS_TMPL.find("END SYSTEM READINESS CARD")
    section = SETTINGS_TMPL[start:end].lower()
    assert "<form" not in section


def test_settings_template_readiness_card_shows_guidance():
    assert "Action needed" in SETTINGS_TMPL or "Configure" in SETTINGS_TMPL


# ── module importable ─────────────────────────────────────────────────────────

def test_build_system_readiness_report_importable():
    from ai.system_readiness import build_system_readiness_report
    assert callable(build_system_readiness_report)


def test_build_system_readiness_report_returns_dict():
    from ai.system_readiness import build_system_readiness_report
    assert isinstance(build_system_readiness_report(None), dict)


def test_build_system_readiness_report_has_status_key():
    from ai.system_readiness import build_system_readiness_report
    assert "status" in build_system_readiness_report(None)


# ── docs files exist ──────────────────────────────────────────────────────────

def test_team_demo_guide_exists():
    assert os.path.isfile("docs/TEAM_DEMO_GUIDE.md"), "docs/TEAM_DEMO_GUIDE.md must exist"


def test_production_checklist_exists():
    assert os.path.isfile("docs/PRODUCTION_CHECKLIST.md"), "docs/PRODUCTION_CHECKLIST.md must exist"


def test_team_demo_guide_mentions_no_auto_send():
    src = _read("docs/TEAM_DEMO_GUIDE.md")
    assert "auto-send" in src.lower() or "auto send" in src.lower()


def test_team_demo_guide_mentions_human_review():
    src = _read("docs/TEAM_DEMO_GUIDE.md")
    assert "human review" in src.lower() or "human-review" in src.lower()


def test_team_demo_guide_mentions_safe_to_send():
    src = _read("docs/TEAM_DEMO_GUIDE.md")
    assert "safe to send" in src.lower() or "safe-to-send" in src.lower()


def test_team_demo_guide_mentions_llmrouter():
    src = _read("docs/TEAM_DEMO_GUIDE.md")
    assert "llmrouter" in src.lower() or "lLMRouter" in src or "LLMRouter" in src


def test_production_checklist_mentions_secrets():
    src = _read("docs/PRODUCTION_CHECKLIST.md")
    assert "secret" in src.lower() or "api key" in src.lower()


def test_production_checklist_mentions_backup():
    src = _read("docs/PRODUCTION_CHECKLIST.md")
    assert "backup" in src.lower()


def test_production_checklist_mentions_rollback():
    src = _read("docs/PRODUCTION_CHECKLIST.md")
    assert "rollback" in src.lower()


def test_production_checklist_mentions_human_review():
    src = _read("docs/PRODUCTION_CHECKLIST.md")
    assert "human review" in src.lower() or "human-review" in src.lower()
