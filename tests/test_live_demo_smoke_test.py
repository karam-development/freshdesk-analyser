"""Tests for PR 32 — live demo smoke test checklist and route-check script.

Source-level checks only: reads docs/LIVE_DEMO_SMOKE_TEST.md and
scripts/smoke_check.py to assert correct content. No Flask, no HTTP.
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


# ── 1. docs/LIVE_DEMO_SMOKE_TEST.md existence ────────────────────────────────

def test_live_demo_smoke_test_md_exists():
    assert os.path.isfile("docs/LIVE_DEMO_SMOKE_TEST.md"), \
        "docs/LIVE_DEMO_SMOKE_TEST.md must exist"


# ── 2. Required topics in the doc ─────────────────────────────────────────────

@pytest.fixture(scope="module")
def smoke_doc() -> str:
    return _read("docs/LIVE_DEMO_SMOKE_TEST.md").lower()


def test_doc_mentions_settings_readiness(smoke_doc):
    assert "settings readiness" in smoke_doc or "system readiness" in smoke_doc


def test_doc_mentions_freshdesk_connection(smoke_doc):
    assert "freshdesk connection" in smoke_doc or "freshdesk" in smoke_doc


def test_doc_mentions_llm_provider(smoke_doc):
    assert "llm provider" in smoke_doc or "llm connection" in smoke_doc or "llm" in smoke_doc


def test_doc_mentions_ticket_inbox(smoke_doc):
    assert "ticket inbox" in smoke_doc or "inbox" in smoke_doc


def test_doc_mentions_ticket_detail(smoke_doc):
    assert "ticket detail" in smoke_doc or "ticket page" in smoke_doc


def test_doc_mentions_draft_generation(smoke_doc):
    assert "draft generation" in smoke_doc or "generate draft" in smoke_doc


def test_doc_mentions_safe_to_send(smoke_doc):
    assert "safe-to-send" in smoke_doc or "safe to send" in smoke_doc


def test_doc_mentions_copy_confirmation(smoke_doc):
    assert "copy confirmation" in smoke_doc or "copy" in smoke_doc


def test_doc_mentions_no_auto_send(smoke_doc):
    assert "auto-send" in smoke_doc or "no auto" in smoke_doc


def test_doc_mentions_human_review(smoke_doc):
    assert "human review" in smoke_doc


def test_doc_mentions_pmdecision(smoke_doc):
    assert "pmdecision" in smoke_doc or "pm decision" in smoke_doc or "pm guard" in smoke_doc


def test_doc_mentions_kb_evidence(smoke_doc):
    assert "kb evidence" in smoke_doc or "knowledge base" in smoke_doc


def test_doc_mentions_copy_button_not_disabled(smoke_doc):
    # The copy button must not be described as blocked/disabled
    assert "copy" in smoke_doc
    # Doc should note the button is always clickable (warns but doesn't block)
    assert "warn" in smoke_doc or "always" in smoke_doc or "gate" in smoke_doc


def test_doc_has_final_checklist_table(smoke_doc):
    # Must include a summary checklist
    assert "checklist" in smoke_doc or "summary" in smoke_doc


def test_doc_references_smoke_check_script(smoke_doc):
    assert "smoke_check.py" in smoke_doc


def test_doc_references_other_docs(smoke_doc):
    assert "team_demo_guide" in smoke_doc or "production_checklist" in smoke_doc


# ── 3. scripts/smoke_check.py existence ──────────────────────────────────────

def test_smoke_check_py_exists():
    assert os.path.isfile("scripts/smoke_check.py"), \
        "scripts/smoke_check.py must exist"


# ── 4. smoke_check.py content checks ─────────────────────────────────────────

@pytest.fixture(scope="module")
def smoke_script() -> str:
    return _read("scripts/smoke_check.py")


def test_smoke_check_has_base_url_param(smoke_script):
    assert "--base-url" in smoke_script or "base_url" in smoke_script


def test_smoke_check_default_is_localhost(smoke_script):
    assert "localhost" in smoke_script


def test_smoke_check_has_dry_run_mode(smoke_script):
    assert "--dry-run" in smoke_script or "dry_run" in smoke_script


def test_smoke_check_has_timeout_param(smoke_script):
    assert "--timeout" in smoke_script or "timeout" in smoke_script


def test_smoke_check_never_calls_freshdesk_api(smoke_script):
    # Must not hardcode Freshdesk API endpoints
    assert "freshdesk.com/api" not in smoke_script
    assert "api/v2/tickets" not in smoke_script


def test_smoke_check_never_calls_llm_api(smoke_script):
    # Must not hardcode LLM API endpoints
    assert "api.anthropic.com" not in smoke_script
    assert "api.openai.com" not in smoke_script


def test_smoke_check_only_get_requests(smoke_script):
    # All HTTP checks should use GET — no POST/DELETE/PUT that could mutate state
    # The method field in CHECKS dict should only be "GET"
    method_vals = re.findall(r'"method"\s*:\s*"([A-Z]+)"', smoke_script)
    for m in method_vals:
        assert m == "GET", f"Non-GET method found in CHECKS: {m}"


def test_smoke_check_checks_system_readiness_route(smoke_script):
    assert "/api/system-readiness" in smoke_script


def test_smoke_check_checks_settings_route(smoke_script):
    assert "/settings" in smoke_script


def test_smoke_check_checks_inbox_route(smoke_script):
    # Root path or /inbox
    assert '"/",\n' in smoke_script or '"path": "/"' in smoke_script or "path\": \"/\"" in smoke_script


def test_smoke_check_has_no_app_imports(smoke_script):
    # The script must not import from app.py, agents.py, or ai.*
    # Parse the AST to find all imports at module level
    tree = ast.parse(smoke_script)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("app"), \
                    f"smoke_check.py imports from app: {alias.name}"
                assert not alias.name.startswith("ai."), \
                    f"smoke_check.py imports from ai: {alias.name}"
                assert not alias.name.startswith("agents"), \
                    f"smoke_check.py imports agents: {alias.name}"
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert not mod.startswith("app"), \
                f"smoke_check.py has 'from app' import: {mod}"
            assert not mod.startswith("ai."), \
                f"smoke_check.py has 'from ai.' import: {mod}"
            assert not mod.startswith("agents"), \
                f"smoke_check.py has 'from agents' import: {mod}"


def test_smoke_check_uses_only_stdlib_top_level_imports(smoke_script):
    # Top-level (non-lazy) imports must be stdlib only
    stdlib_allowed = {
        "argparse", "json", "sys", "time", "os", "re",
        "typing", "__future__", "urllib", "urllib.request",
        "urllib.error", "subprocess", "ast",
    }
    tree = ast.parse(smoke_script)
    for node in ast.iter_child_nodes(tree):  # only top-level
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                assert top in stdlib_allowed, \
                    f"Non-stdlib top-level import: {alias.name}"
        if isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            assert top in stdlib_allowed, \
                f"Non-stdlib top-level from-import: {node.module}"


def test_smoke_check_has_exit_code_zero_on_pass(smoke_script):
    assert "return 0" in smoke_script or "sys.exit(0)" in smoke_script or "exit(0)" in smoke_script


def test_smoke_check_has_exit_code_one_on_fail(smoke_script):
    # Accepts "return 1", "sys.exit(1)", or inline ternary "else 1"
    assert "return 1" in smoke_script or "sys.exit(1)" in smoke_script \
        or "else 1" in smoke_script


def test_smoke_check_note_says_no_freshdesk_llm_calls(smoke_script):
    lower = smoke_script.lower()
    assert "never" in lower and ("freshdesk" in lower or "llm" in lower)


def test_smoke_check_is_executable_syntax(smoke_script):
    # AST-parseable without error
    try:
        ast.parse(smoke_script)
    except SyntaxError as e:
        pytest.fail(f"smoke_check.py has syntax error: {e}")


# ── 5. smoke_check.py --dry-run works without a server ───────────────────────

def test_smoke_check_dry_run_exits_without_network():
    """--dry-run must complete without any network calls."""
    result = subprocess.run(
        [sys.executable, "scripts/smoke_check.py", "--dry-run", "--no-colour"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    # dry-run exits with code 2 (all skipped)
    assert result.returncode == 2, \
        f"Expected exit code 2, got {result.returncode}. stderr: {result.stderr}"
    # Should list the checks
    assert "smoke_check" in result.stdout.lower() or "skip" in result.stdout.lower() \
        or "checks" in result.stdout.lower() or "listed" in result.stdout.lower()


def test_smoke_check_dry_run_mentions_system_readiness():
    result = subprocess.run(
        [sys.executable, "scripts/smoke_check.py", "--dry-run", "--no-colour"],
        capture_output=True, text=True, timeout=10,
    )
    assert "system-readiness" in result.stdout or "system_readiness" in result.stdout


def test_smoke_check_dry_run_json_mode():
    result = subprocess.run(
        [sys.executable, "scripts/smoke_check.py", "--dry-run", "--json"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 2
    data = json.loads(result.stdout)
    assert data["mode"] == "dry_run"
    assert len(data["checks"]) > 0


def test_smoke_check_help_flag():
    result = subprocess.run(
        [sys.executable, "scripts/smoke_check.py", "--help"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    assert "base-url" in result.stdout or "base_url" in result.stdout


import json  # needed for test_smoke_check_dry_run_json_mode — ensure import
