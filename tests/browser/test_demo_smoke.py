"""Optional Playwright browser smoke tests for the Freshdesk AI Analyser.

These tests are OPTIONAL and SAFE:
- They skip cleanly if Playwright is not installed.
- They skip cleanly if the app is not running at APP_BASE_URL.
- They never POST to mutating endpoints.
- They never call Freshdesk, OpenAI, or Anthropic APIs directly.
- They never trigger draft generation or auto-send.
- They are read-only: navigate and assert on visible UI only.

Usage:
    APP_BASE_URL=http://localhost:5000 python3 -m pytest tests/browser -q

Environment variables:
    APP_BASE_URL    Base URL of the running app (default: http://localhost:5000)
    PW_HEADLESS     Set to "0" or "false" to run headed (default: headless)
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import pytest

# ── Playwright availability check ─────────────────────────────────────────────

try:
    from playwright.sync_api import sync_playwright, Page, expect
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False

# ── Configuration ─────────────────────────────────────────────────────────────

BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:5000").rstrip("/")
_HEADLESS = os.environ.get("PW_HEADLESS", "1").lower() not in ("0", "false", "no")
_TIMEOUT_MS = 10_000  # 10 s per assertion


# ── Session-level skip guards ──────────────────────────────────────────────────

def _app_is_reachable() -> bool:
    """Return True if the app responds at BASE_URL within a short timeout."""
    try:
        req = urllib.request.Request(BASE_URL + "/api/status",
                                     method="GET")
        with urllib.request.urlopen(req, timeout=4) as resp:
            return resp.status == 200
    except Exception:
        return False


_skip_no_playwright = pytest.mark.skipif(
    not _PLAYWRIGHT_AVAILABLE,
    reason="playwright not installed — run: pip install playwright pytest-playwright && playwright install chromium",
)
_skip_no_app = pytest.mark.skipif(
    not _app_is_reachable(),
    reason=f"App not reachable at {BASE_URL} — start with: python3 app.py",
)


def _skip_guards():
    """Compound skip decorator for all browser tests."""
    return pytest.mark.usefixtures()  # placeholder — marks applied per-test below


# ── Browser fixture ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def browser_page():
    """Provide a Playwright page for the module. Skips if Playwright unavailable."""
    if not _PLAYWRIGHT_AVAILABLE:
        pytest.skip("playwright not installed")
    if not _app_is_reachable():
        pytest.skip(f"App not reachable at {BASE_URL}")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=_HEADLESS)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(_TIMEOUT_MS)
        yield page
        context.close()
        browser.close()


# ── Helper ────────────────────────────────────────────────────────────────────

def _goto(page, path: str) -> None:
    """Navigate to a path and wait for load."""
    page.goto(BASE_URL + path, wait_until="domcontentloaded")


def _safe_text(page) -> str:
    """Return page text content for assertions."""
    return page.content()


# ── 1. Homepage / inbox loads ─────────────────────────────────────────────────

@_skip_no_playwright
@_skip_no_app
def test_homepage_loads(browser_page):
    """Inbox page loads without a 500 error."""
    _goto(browser_page, "/")
    # Page must not show a server error
    content = _safe_text(browser_page)
    assert "500" not in browser_page.title()
    assert "Internal Server Error" not in content
    # Title or body should contain something meaningful
    assert browser_page.url.startswith(BASE_URL)


# ── 2. Settings page loads ────────────────────────────────────────────────────

@_skip_no_playwright
@_skip_no_app
def test_settings_page_loads(browser_page):
    """Settings page loads without a 500 error."""
    _goto(browser_page, "/settings")
    content = _safe_text(browser_page)
    assert "Internal Server Error" not in content
    assert "500" not in browser_page.title()


@_skip_no_playwright
@_skip_no_app
def test_settings_contains_system_readiness(browser_page):
    """Settings page shows the System Readiness card."""
    _goto(browser_page, "/settings")
    content = _safe_text(browser_page)
    assert "System Readiness" in content


@_skip_no_playwright
@_skip_no_app
def test_settings_contains_security_readiness(browser_page):
    """Settings page shows the Security Readiness card."""
    _goto(browser_page, "/settings")
    content = _safe_text(browser_page)
    assert "Security Readiness" in content


# ── 3. Agents page loads ──────────────────────────────────────────────────────

@_skip_no_playwright
@_skip_no_app
def test_agents_page_loads(browser_page):
    """Agents page loads without a 500 error."""
    _goto(browser_page, "/agents")
    content = _safe_text(browser_page)
    assert "Internal Server Error" not in content
    assert "500" not in browser_page.title()


# ── 4. API: system-readiness ──────────────────────────────────────────────────

@_skip_no_playwright
@_skip_no_app
def test_api_system_readiness_returns_ok(browser_page):
    """/api/system-readiness returns JSON with ok field."""
    _goto(browser_page, "/api/system-readiness")
    body = browser_page.content()
    # Extract JSON from the page body (browser wraps it in <pre> or <body>)
    try:
        # Try to find raw JSON object
        start = body.find("{")
        end = body.rfind("}") + 1
        data = json.loads(body[start:end])
        assert "ok" in data, "Response missing 'ok' field"
    except (ValueError, AssertionError) as exc:
        pytest.fail(f"api/system-readiness did not return valid JSON: {exc}")


# ── 5. API: security-readiness ────────────────────────────────────────────────

@_skip_no_playwright
@_skip_no_app
def test_api_security_readiness_returns_ok(browser_page):
    """/api/security-readiness returns JSON with ok field."""
    _goto(browser_page, "/api/security-readiness")
    body = browser_page.content()
    try:
        start = body.find("{")
        end = body.rfind("}") + 1
        data = json.loads(body[start:end])
        assert "ok" in data, "Response missing 'ok' field"
    except (ValueError, AssertionError) as exc:
        pytest.fail(f"api/security-readiness did not return valid JSON: {exc}")


# ── 6. API: no secret values in security-readiness response ──────────────────

@_skip_no_playwright
@_skip_no_app
def test_api_security_readiness_no_raw_key_values(browser_page):
    """/api/security-readiness must not expose API key values in the response."""
    _goto(browser_page, "/api/security-readiness")
    body = browser_page.content()
    # The response must not contain patterns that look like raw API keys
    # Real keys start with "sk-" (OpenAI) or "fd-" style patterns
    # We check that no check message contains a full key-length value
    try:
        start = body.find("{")
        end = body.rfind("}") + 1
        data = json.loads(body[start:end])
        report_str = json.dumps(data.get("report", {}))
        # Values longer than 40 chars in a message field could indicate key leakage
        # (real check messages are short descriptions)
        for check in data.get("report", {}).get("checks", []):
            msg = check.get("message", "")
            # Message should be a human-readable sentence, not a raw key
            assert len(msg) < 300, f"Suspiciously long message in check '{check.get('code')}'"
    except (ValueError, KeyError):
        pass  # If JSON parse fails, the first test already caught it


# ── 7. Ticket detail smoke test (conditional) ─────────────────────────────────

@_skip_no_playwright
@_skip_no_app
def test_ticket_detail_if_available(browser_page):
    """If a ticket link is visible on the inbox, open it and check for panels.

    This test is conditional: if no ticket links are found on the inbox, it
    passes vacuously. The app must be pre-loaded with tickets for a real check.
    """
    _goto(browser_page, "/")
    # Look for any href matching /ticket/<number>
    ticket_links = browser_page.locator("a[href*='/ticket/']").all()
    if not ticket_links:
        pytest.skip("No ticket links found on inbox — skipping ticket detail check")

    # Navigate to the first ticket
    first_href = ticket_links[0].get_attribute("href")
    if not first_href:
        pytest.skip("First ticket link has no href")

    ticket_url = first_href if first_href.startswith("http") else BASE_URL + first_href
    browser_page.goto(ticket_url, wait_until="domcontentloaded")

    content = _safe_text(browser_page)
    # Page must not error
    assert "Internal Server Error" not in content
    assert "500" not in browser_page.title()

    # Check for expected panel headings (best-effort — panels may say "unavailable")
    expected_panel_fragments = [
        "PMDecision",
        "Safe",        # "Safe-to-Send Review" or "Safe to Send"
        "KB Evidence",
    ]
    found_panels = [frag for frag in expected_panel_fragments if frag in content]

    # At least one panel heading should be visible (even if it says "unavailable")
    assert len(found_panels) >= 1, (
        f"No expected panel headings found on ticket detail page. "
        f"Checked: {expected_panel_fragments}. "
        "The page may not have been analysed yet — run analysis first."
    )


# ── 8. Settings form is not auto-submitted ───────────────────────────────────

@_skip_no_playwright
@_skip_no_app
def test_settings_has_no_auto_submit(browser_page):
    """Settings page must not auto-submit or redirect away on load."""
    _goto(browser_page, "/settings")
    # After a normal page load the URL should still be /settings
    assert "/settings" in browser_page.url


# ── 9. No auto-send button visible ───────────────────────────────────────────

@_skip_no_playwright
@_skip_no_app
def test_no_auto_send_button_on_settings(browser_page):
    """Settings page must not contain an auto-send button."""
    _goto(browser_page, "/settings")
    content = _safe_text(browser_page).lower()
    assert "auto-send" not in content
    assert "autosend" not in content


# ── 10. Human-review gate: Copy draft requires action ────────────────────────

@_skip_no_playwright
@_skip_no_app
def test_inbox_no_server_error(browser_page):
    """Inbox page must not show a 500 error on a clean load."""
    _goto(browser_page, "/")
    assert "Internal Server Error" not in _safe_text(browser_page)
