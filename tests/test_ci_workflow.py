"""Source-level tests for PR 36 — GitHub Actions CI workflow.

All tests are source/text checks. No workflow execution required.
Covers:
- .github/workflows/ci.yml exists and has expected content
- workflow triggers on pull_request and push to main
- workflow uses Python 3.11
- workflow installs requirements.txt
- workflow runs py_compile
- workflow runs pytest -q
- workflow runs smoke_check --dry-run --json
- workflow does not contain external API URLs or secrets
- workflow does not install Playwright
- README mentions CI, pytest, smoke_check, and optional browser tests
"""
from __future__ import annotations

from pathlib import Path

import pytest

# ── Source files ──────────────────────────────────────────────────────────────

CI_WORKFLOW = Path(".github/workflows/ci.yml")
README      = Path("README.md").read_text(encoding="utf-8")


def _ci() -> str:
    return CI_WORKFLOW.read_text(encoding="utf-8")


# ── 1. Workflow file exists ───────────────────────────────────────────────────

def test_ci_workflow_file_exists():
    assert CI_WORKFLOW.exists(), ".github/workflows/ci.yml not found"


def test_ci_workflow_not_empty():
    assert CI_WORKFLOW.stat().st_size > 100


# ── 2. Workflow name ──────────────────────────────────────────────────────────

def test_workflow_name_is_ci():
    ci = _ci()
    assert "name: CI" in ci


# ── 3. Triggers ───────────────────────────────────────────────────────────────

def test_workflow_triggers_on_pull_request():
    assert "pull_request" in _ci()


def test_workflow_triggers_on_push():
    assert "push:" in _ci() or "push\n" in _ci()


def test_workflow_targets_main_branch():
    assert "main" in _ci()


# ── 4. Python version ─────────────────────────────────────────────────────────

def test_workflow_uses_python_311():
    ci = _ci()
    assert "3.11" in ci


def test_workflow_uses_setup_python_action():
    assert "setup-python" in _ci()


# ── 5. Dependency installation ────────────────────────────────────────────────

def test_workflow_installs_requirements_txt():
    assert "requirements.txt" in _ci()


def test_workflow_upgrades_pip():
    assert "pip install --upgrade pip" in _ci() or "pip install -U pip" in _ci()


# ── 6. Compile check ──────────────────────────────────────────────────────────

def test_workflow_runs_py_compile():
    ci = _ci()
    assert "py_compile" in ci


def test_workflow_compiles_app_py():
    assert "app.py" in _ci()


def test_workflow_compiles_agents_py():
    assert "agents.py" in _ci()


def test_workflow_compiles_security_readiness():
    assert "ai/security_readiness.py" in _ci()


def test_workflow_compiles_smoke_check():
    assert "scripts/smoke_check.py" in _ci()


# ── 7. pytest ─────────────────────────────────────────────────────────────────

def test_workflow_runs_pytest():
    assert "pytest" in _ci()


def test_workflow_runs_pytest_q():
    ci = _ci()
    assert "pytest -q" in ci


# ── 8. Smoke check dry-run ────────────────────────────────────────────────────

def test_workflow_runs_smoke_check():
    assert "smoke_check.py" in _ci()


def test_workflow_runs_smoke_check_dry_run():
    assert "--dry-run" in _ci()


def test_workflow_runs_smoke_check_json():
    assert "--json" in _ci()


# ── 9. No external API calls ─────────────────────────────────────────────────

def test_workflow_no_freshdesk_api_url():
    assert "freshdesk.com/api" not in _ci().lower()


def test_workflow_no_openai_api_url():
    assert "api.openai.com" not in _ci().lower()


def test_workflow_no_anthropic_api_url():
    assert "api.anthropic.com" not in _ci().lower()


# ── 10. No secrets required ───────────────────────────────────────────────────

def test_workflow_no_required_secrets():
    ci = _ci()
    # Should not reference ${{ secrets.SOME_KEY }} for API credentials
    import re
    secret_refs = re.findall(r'\$\{\{\s*secrets\.\w+\s*\}\}', ci)
    # Allow zero secret references
    assert len(secret_refs) == 0, f"Workflow references secrets: {secret_refs}"


# ── 11. No Playwright install ─────────────────────────────────────────────────

def test_workflow_does_not_install_playwright():
    ci = _ci().lower()
    # Must not install Playwright in CI (browser tests are optional)
    assert "playwright install" not in ci


def test_workflow_does_not_pip_install_playwright():
    ci = _ci().lower()
    # pip install playwright is not in the workflow
    assert "install playwright" not in ci


# ── 12. Workflow runs on ubuntu-latest ───────────────────────────────────────

def test_workflow_uses_ubuntu_latest():
    assert "ubuntu-latest" in _ci()


# ── 13. Checkout step present ─────────────────────────────────────────────────

def test_workflow_has_checkout_step():
    assert "actions/checkout" in _ci()


# ── 14. README mentions CI ────────────────────────────────────────────────────

def test_readme_mentions_ci():
    assert "CI" in README or "GitHub Actions" in README


def test_readme_mentions_pytest():
    assert "pytest" in README


def test_readme_mentions_smoke_check():
    assert "smoke_check" in README or "smoke check" in README.lower()


def test_readme_mentions_browser_tests_optional():
    lower = README.lower()
    assert "optional" in lower and ("browser" in lower or "playwright" in lower)


def test_readme_mentions_no_secrets_for_ci():
    lower = README.lower()
    assert "no secrets" in lower or "secrets" in lower or "api key" in lower


# ── 15. Workflow structure ────────────────────────────────────────────────────

def test_workflow_has_jobs_section():
    assert "jobs:" in _ci()


def test_workflow_has_steps_section():
    assert "steps:" in _ci()


def test_workflow_has_test_job():
    ci = _ci()
    assert "test:" in ci or "test\n" in ci or "  test:" in ci
