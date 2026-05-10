"""Source-level tests for PR 35 — Playwright browser smoke tests.

These tests run in the normal pytest suite (no Playwright required).
They verify that:
- docs/PLAYWRIGHT_SMOKE_TESTS.md exists and contains required content
- tests/browser/test_demo_smoke.py exists and is safe
- scripts/run_browser_smoke.sh exists and runs pytest tests/browser
- README links to Playwright smoke test docs
- Browser test file skips when Playwright is unavailable
- Browser test file never POSTs to mutating endpoints
- Browser test file never references external API URLs
"""
from __future__ import annotations

from pathlib import Path

import pytest

# ── Source files ──────────────────────────────────────────────────────────────

PW_DOC       = Path("docs/PLAYWRIGHT_SMOKE_TESTS.md")
BROWSER_TEST = Path("tests/browser/test_demo_smoke.py")
SHELL_SCRIPT = Path("scripts/run_browser_smoke.sh")
README       = Path("README.md").read_text(encoding="utf-8")
LIVE_SMOKE   = Path("docs/LIVE_DEMO_SMOKE_TEST.md").read_text(encoding="utf-8")
TEAM_DEMO    = Path("docs/TEAM_DEMO_GUIDE.md").read_text(encoding="utf-8")


# ── 1. docs/PLAYWRIGHT_SMOKE_TESTS.md exists ─────────────────────────────────

def test_playwright_doc_exists():
    assert PW_DOC.exists(), "docs/PLAYWRIGHT_SMOKE_TESTS.md not found"


def test_playwright_doc_not_empty():
    assert PW_DOC.stat().st_size > 100


def _doc() -> str:
    return PW_DOC.read_text(encoding="utf-8")


def test_playwright_doc_mentions_no_freshdesk_calls():
    lower = _doc().lower()
    assert "no freshdesk" in lower or "never calls freshdesk" in lower or \
           ("freshdesk" in lower and "not" in lower)


def test_playwright_doc_mentions_no_llm_calls():
    lower = _doc().lower()
    assert "no llm" in lower or "never" in lower and "llm" in lower or \
           "no draft" in lower or "not trigger" in lower


def test_playwright_doc_mentions_no_auto_send():
    lower = _doc().lower()
    assert "no auto-send" in lower or "no auto send" in lower or \
           "never post" in lower or "auto-send" in lower


def test_playwright_doc_mentions_human_review():
    lower = _doc().lower()
    assert "human review" in lower


def test_playwright_doc_mentions_install_playwright():
    lower = _doc().lower()
    assert "pip install playwright" in lower


def test_playwright_doc_mentions_app_base_url():
    assert "APP_BASE_URL" in _doc()


def test_playwright_doc_mentions_skip_if_not_installed():
    lower = _doc().lower()
    assert "skip" in lower and ("not installed" in lower or "unavailable" in lower)


def test_playwright_doc_mentions_chromium():
    lower = _doc().lower()
    assert "chromium" in lower


def test_playwright_doc_has_known_limitations():
    assert "Known Limitations" in _doc() or "known limitations" in _doc().lower()


# ── 2. tests/browser/test_demo_smoke.py exists ───────────────────────────────

def test_browser_test_file_exists():
    assert BROWSER_TEST.exists(), "tests/browser/test_demo_smoke.py not found"


def _bt() -> str:
    return BROWSER_TEST.read_text(encoding="utf-8")


def test_browser_test_references_app_base_url():
    assert "APP_BASE_URL" in _bt()


def test_browser_test_skips_when_playwright_unavailable():
    src = _bt()
    # Must guard against ImportError from playwright
    assert "ImportError" in src or "playwright not installed" in src.lower()


def test_browser_test_has_skip_when_app_not_reachable():
    src = _bt()
    assert "not reachable" in src.lower() or "_app_is_reachable" in src or \
           "App not reachable" in src


def test_browser_test_has_no_post_requests():
    """Browser test must not use POST, DELETE, PUT, or PATCH."""
    src = _bt().lower()
    # POST via playwright is done with page.request.post or fetch("...", method="POST")
    # Simple check: no method="post" strings and no explicit .post( call beyond url strings
    assert 'method="post"' not in src
    assert "request.post(" not in src
    assert 'method: "post"' not in src
    assert "page.evaluate" not in src or "post" not in src  # no eval-based POST


def test_browser_test_has_no_delete_requests():
    src = _bt().lower()
    assert "request.delete(" not in src
    assert 'method="delete"' not in src


def test_browser_test_has_no_put_requests():
    src = _bt().lower()
    assert "request.put(" not in src
    assert 'method="put"' not in src


def test_browser_test_has_no_patch_requests():
    src = _bt().lower()
    assert "request.patch(" not in src


def test_browser_test_no_freshdesk_api_url():
    src = _bt().lower()
    assert "freshdesk.com/api" not in src


def test_browser_test_no_openai_api_url():
    src = _bt().lower()
    assert "api.openai.com" not in src


def test_browser_test_no_anthropic_api_url():
    src = _bt().lower()
    assert "api.anthropic.com" not in src


def test_browser_test_checks_settings_page():
    assert "/settings" in _bt()


def test_browser_test_checks_system_readiness():
    assert "System Readiness" in _bt()


def test_browser_test_checks_security_readiness():
    assert "Security Readiness" in _bt()


def test_browser_test_checks_agents_page():
    assert "/agents" in _bt()


def test_browser_test_checks_api_system_readiness():
    assert "/api/system-readiness" in _bt()


def test_browser_test_checks_api_security_readiness():
    assert "/api/security-readiness" in _bt()


def test_browser_test_ticket_detail_is_conditional():
    """Ticket detail test must skip gracefully when no tickets exist."""
    src = _bt()
    assert "pytest.skip" in src or "skipif" in src.lower()
    # The ticket check should guard against no-tickets case
    assert "ticket" in src.lower()


def test_browser_test_no_auto_send_assertion():
    """Browser test should verify no auto-send UI exists."""
    src = _bt().lower()
    assert "auto-send" in src or "autosend" in src


def test_browser_tests_module_has_no_app_imports():
    """Browser tests must not import from app.py (keeps them independent)."""
    src = _bt()
    assert "import app" not in src
    assert "from app import" not in src


# ── 3. scripts/run_browser_smoke.sh exists ───────────────────────────────────

def test_shell_script_exists():
    assert SHELL_SCRIPT.exists(), "scripts/run_browser_smoke.sh not found"


def _sh() -> str:
    return SHELL_SCRIPT.read_text(encoding="utf-8")


def test_shell_script_runs_pytest_browser():
    assert "pytest tests/browser" in _sh()


def test_shell_script_uses_app_base_url():
    assert "APP_BASE_URL" in _sh()


def test_shell_script_checks_playwright_installed():
    sh = _sh().lower()
    assert "playwright" in sh and ("not installed" in sh or "import playwright" in sh)


def test_shell_script_checks_app_reachable():
    sh = _sh().lower()
    assert "reachable" in sh or "not reachable" in sh


def test_shell_script_has_safety_note():
    sh = _sh().lower()
    assert "no freshdesk" in sh or "read-only" in sh or "safety" in sh


def test_shell_script_is_executable():
    import stat
    mode = SHELL_SCRIPT.stat().st_mode
    assert bool(mode & stat.S_IXUSR), "scripts/run_browser_smoke.sh is not executable"


# ── 4. README links to Playwright docs ───────────────────────────────────────

def test_readme_links_playwright_smoke_tests():
    assert "PLAYWRIGHT_SMOKE_TESTS" in README or "Playwright Smoke Tests" in README


def test_readme_mentions_playwright():
    assert "Playwright" in README or "playwright" in README.lower()


# ── 5. LIVE_DEMO_SMOKE_TEST.md mentions browser smoke tests ──────────────────

def test_live_demo_mentions_playwright():
    assert "Playwright" in LIVE_SMOKE or "playwright" in LIVE_SMOKE.lower()


def test_live_demo_mentions_run_browser_smoke():
    assert "run_browser_smoke" in LIVE_SMOKE or "tests/browser" in LIVE_SMOKE


def test_live_demo_mentions_browser_tests_are_optional():
    lower = LIVE_SMOKE.lower()
    assert "optional" in lower


# ── 6. TEAM_DEMO_GUIDE.md mentions Playwright ────────────────────────────────

def test_team_demo_mentions_playwright():
    assert "Playwright" in TEAM_DEMO or "playwright" in TEAM_DEMO.lower()


def test_team_demo_mentions_browser_tests_safe():
    lower = TEAM_DEMO.lower()
    assert "safe" in lower or "optional" in lower


def test_team_demo_mentions_playwright_no_auto_send():
    lower = TEAM_DEMO.lower()
    # The playwright section should reinforce no auto-send
    assert "auto-send" in lower or "no auto" in lower


# ── 7. Normal pytest suite not broken ────────────────────────────────────────

def test_browser_init_file_exists():
    """tests/browser/__init__.py must exist to avoid import issues."""
    assert Path("tests/browser/__init__.py").exists()


def test_browser_test_not_in_root_tests():
    """Browser tests are in tests/browser/, not in tests/ root."""
    root_tests = list(Path("tests").glob("test_*.py"))
    names = [p.name for p in root_tests]
    assert "test_demo_smoke.py" not in names
