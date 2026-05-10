"""Security readiness helper — no LLM calls, no DB writes.

Public function
---------------
build_security_readiness_report(
    settings: dict | None = None,
    env: dict | None = None,
) -> dict

Returns a stable security readiness report suitable for the settings page and
the /api/security-readiness endpoint.

Returned structure::

    {
      "status": str,          # secure_enough_for_demo / needs_attention /
                              #   unsafe_for_production / unknown
      "score": int,           # 0–100
      "checks": list[dict],   # one dict per check
      "summary": dict,        # {pass_count, warning_count, fail_count, unknown_count}
    }

Each check::

    {
      "code": str,       # machine-readable identifier
      "status": str,     # pass / warning / fail / unknown
      "severity": str,   # critical / warning / info
      "title": str,
      "message": str,    # human-readable; NEVER contains secret values
    }

Rules
-----
- Never raises.
- Never exposes secret values in any field.
- API key presence is reported as "present" or "missing" only.
- Score starts at 100; fail deducts 25, warning deducts 10; floored at 0.
- Status:
    - unknown: settings is invalid/None AND env is invalid/None
    - unsafe_for_production: any fail with severity critical
    - needs_attention: any warning or non-critical fail
    - secure_enough_for_demo: no fails and score >= 80
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

_CRITICAL_CODES = frozenset({
    "secret_key_set",
    "secret_key_not_default",
    "flask_debug_disabled",
})

_SCORE_DEDUCT = {"fail": 25, "warning": 10, "pass": 0, "unknown": 0}

# Substrings that indicate a weak/default SECRET_KEY
_WEAK_KEY_SUBSTRINGS = (
    "dev", "default", "change-me", "changeme", "secret", "test",
    "example", "placeholder", "replace", "insecure",
)

# Docs files to verify exist (relative to repo root)
_EXPECTED_DOCS = {
    "production_checklist_present": "docs/PRODUCTION_CHECKLIST.md",
    "live_demo_smoke_test_present": "docs/LIVE_DEMO_SMOKE_TEST.md",
}


# ── Public API ───────────────────────────────────────────────────────────────

def build_security_readiness_report(
    settings: Optional[dict] = None,
    env: Optional[dict] = None,
) -> dict:
    """Build and return a security readiness report.

    Parameters
    ----------
    settings:
        Dict with keys such as ``llm_api_key``, ``freshdesk_api_key``,
        ``freshdesk_domain``.  Values are used only to determine
        present/missing — never included in the output.
    env:
        Dict of environment variables (e.g. ``os.environ``).  Defaults to an
        empty dict when not provided so the function can still run.

    Returns
    -------
    dict
        Stable report with ``status``, ``score``, ``checks``, ``summary``.
    """
    try:
        return _build(settings, env)
    except Exception as exc:  # pragma: no cover — defensive catch-all
        logger.warning("build_security_readiness_report: unexpected error: %s", exc)
        return {
            "status": "unknown",
            "score": 0,
            "checks": [],
            "summary": {
                "pass_count": 0, "warning_count": 0,
                "fail_count": 0, "unknown_count": 1,
            },
        }


# ── Internal ─────────────────────────────────────────────────────────────────

def _build(settings: Optional[dict], env: Optional[dict]) -> dict:
    _s = settings if isinstance(settings, dict) else {}
    _e = env if isinstance(env, dict) else {}

    # If both are missing/invalid, return unknown immediately
    if not isinstance(settings, dict) and not isinstance(env, dict):
        return {
            "status": "unknown",
            "score": 0,
            "checks": [],
            "summary": {
                "pass_count": 0, "warning_count": 0,
                "fail_count": 0, "unknown_count": 1,
            },
        }

    checks: list[dict] = []

    # 1. SECRET_KEY set
    checks.append(_check_secret_key_set(_e))

    # 2. SECRET_KEY not a weak/default value
    checks.append(_check_secret_key_not_default(_e))

    # 3. Flask debug disabled
    checks.append(_check_flask_debug_disabled(_e))

    # 4. LLM API key — confirm present/missing, never expose value
    checks.append(_check_api_key_not_exposed("llm_api_key_not_exposed",
                                             "LLM API Key",
                                             _s.get("llm_api_key") or ""))

    # 5. Freshdesk API key — confirm present/missing, never expose value
    checks.append(_check_api_key_not_exposed("freshdesk_api_key_not_exposed",
                                             "Freshdesk API Key",
                                             _s.get("freshdesk_api_key") or ""))

    # 6. Database path hint (best-effort advisory)
    checks.append(_check_database_path_hint(_e))

    # 7. Human review required — documented
    checks.append(_check_doc_content(
        "human_review_required_documented",
        "Human Review Required Documented",
        "docs/TEAM_DEMO_GUIDE.md",
        keywords=["human review", "human must", "no auto-send", "no auto send"],
        pass_msg="TEAM_DEMO_GUIDE.md documents human review requirement.",
        warn_msg="Could not confirm human review requirement is documented in TEAM_DEMO_GUIDE.md.",
    ))

    # 8. No auto-send — documented
    checks.append(_check_doc_content(
        "no_auto_send_documented",
        "No Auto-Send Documented",
        "docs/TEAM_DEMO_GUIDE.md",
        keywords=["auto-send", "auto send", "never auto"],
        pass_msg="TEAM_DEMO_GUIDE.md documents no auto-send behaviour.",
        warn_msg="Could not confirm no-auto-send is documented in TEAM_DEMO_GUIDE.md.",
    ))

    # 9. Production checklist present
    checks.append(_check_doc_exists(
        "production_checklist_present",
        "Production Checklist Present",
        "docs/PRODUCTION_CHECKLIST.md",
    ))

    # 10. Live demo smoke test present
    checks.append(_check_doc_exists(
        "live_demo_smoke_test_present",
        "Live Demo Smoke Test Present",
        "docs/LIVE_DEMO_SMOKE_TEST.md",
    ))

    # ── Scoring ──────────────────────────────────────────────────────────────
    score = 100
    for c in checks:
        score -= _SCORE_DEDUCT.get(c["status"], 0)
    score = max(0, score)

    # ── Summary ──────────────────────────────────────────────────────────────
    summary = {
        "pass_count":    sum(1 for c in checks if c["status"] == "pass"),
        "warning_count": sum(1 for c in checks if c["status"] == "warning"),
        "fail_count":    sum(1 for c in checks if c["status"] == "fail"),
        "unknown_count": sum(1 for c in checks if c["status"] == "unknown"),
    }

    # ── Status ───────────────────────────────────────────────────────────────
    any_critical_fail = any(
        c["status"] == "fail" and c["severity"] == "critical"
        and c["code"] in _CRITICAL_CODES
        for c in checks
    )
    # Only critical- or warning-severity issues block secure_enough_for_demo
    any_significant_issue = any(
        c["status"] in ("fail", "warning") and c["severity"] in ("critical", "warning")
        for c in checks
    )

    if any_critical_fail:
        status = "unsafe_for_production"
    elif any_significant_issue:
        status = "needs_attention"
    elif score >= 80:
        status = "secure_enough_for_demo"
    else:
        status = "needs_attention"

    return {
        "status": status,
        "score": score,
        "checks": checks,
        "summary": summary,
    }


# ── Check helpers ─────────────────────────────────────────────────────────────

def _make_check(code: str, status: str, severity: str,
                title: str, message: str) -> dict:
    return {
        "code": code,
        "status": status,
        "severity": severity,
        "title": title,
        "message": message,
    }


def _check_secret_key_set(env: dict) -> dict:
    code = "secret_key_set"
    title = "SECRET_KEY Set"
    key = env.get("SECRET_KEY") or ""
    if key:
        return _make_check(code, "pass", "critical", title,
                           "SECRET_KEY environment variable is set.")
    # Determine severity based on environment
    app_env = (env.get("APP_ENV") or env.get("FLASK_ENV") or "").lower()
    is_prod_like = app_env in ("production", "prod", "staging")
    severity = "critical" if is_prod_like else "warning"
    status = "fail" if is_prod_like else "warning"
    return _make_check(code, status, severity, title,
                       "SECRET_KEY is not set. Set it via the SECRET_KEY environment "
                       "variable before production or team usage.")


def _check_secret_key_not_default(env: dict) -> dict:
    code = "secret_key_not_default"
    title = "SECRET_KEY Is Not Default/Weak"
    key = env.get("SECRET_KEY") or ""
    if not key:
        # Already caught by secret_key_set; treat as warning here to avoid double-fail
        return _make_check(code, "warning", "critical", title,
                           "SECRET_KEY is not set; cannot verify strength.")
    key_lower = key.lower()
    for weak in _WEAK_KEY_SUBSTRINGS:
        if weak in key_lower:
            return _make_check(code, "fail", "critical", title,
                               "SECRET_KEY appears to be a weak or default value "
                               "(contains common placeholder text). "
                               "Replace it with a strong random string.")
    if len(key) < 24:
        return _make_check(code, "warning", "critical", title,
                           "SECRET_KEY is shorter than recommended (24+ characters). "
                           "Use a longer random value for production.")
    return _make_check(code, "pass", "critical", title,
                       "SECRET_KEY appears to be a non-default value.")


def _check_flask_debug_disabled(env: dict) -> dict:
    code = "flask_debug_disabled"
    title = "Debug Mode Disabled"

    def _is_truthy(val: str) -> bool:
        return val.strip().lower() in ("1", "true", "yes", "on")

    flask_debug = env.get("FLASK_DEBUG") or ""
    app_debug = env.get("APP_DEBUG") or ""

    if _is_truthy(flask_debug) or _is_truthy(app_debug):
        app_env = (env.get("APP_ENV") or env.get("FLASK_ENV") or "").lower()
        is_prod_like = app_env in ("production", "prod", "staging")
        severity = "critical" if is_prod_like else "warning"
        status = "fail" if is_prod_like else "warning"
        return _make_check(code, status, severity, title,
                           "Debug mode is enabled (FLASK_DEBUG or APP_DEBUG is set to a "
                           "truthy value). Disable debug mode before production or "
                           "team-accessible deployment.")
    return _make_check(code, "pass", "warning", title,
                       "Debug mode is not enabled.")


def _check_api_key_not_exposed(code: str, label: str, value: str) -> dict:
    """Confirm API key is present/missing — never include the value."""
    title = f"{label} Configured"
    if value:
        return _make_check(code, "pass", "info", title,
                           f"{label} is configured (value not shown).")
    return _make_check(code, "warning", "warning", title,
                       f"{label} is not configured.")


def _check_database_path_hint(env: dict) -> dict:
    code = "database_path_not_public_hint"
    title = "Database Path Advisory"
    db_url = env.get("DATABASE_URL") or env.get("DB_PATH") or ""
    if db_url:
        # Never show the actual path — just confirm it's set
        return _make_check(code, "pass", "info", title,
                           "Database path/URL is configured via environment variable (value not shown). "
                           "Ensure the DB file is not publicly accessible.")
    return _make_check(code, "warning", "info", title,
                       "No DATABASE_URL or DB_PATH environment variable detected. "
                       "Ensure the SQLite DB file is stored in a non-public directory "
                       "and is regularly backed up.")


def _check_doc_exists(code: str, title: str, path: str) -> dict:
    """Check that a documentation file exists on disk."""
    try:
        p = Path(path)
        if p.exists() and p.stat().st_size > 0:
            return _make_check(code, "pass", "info", title,
                               f"{path} is present.")
        return _make_check(code, "warning", "info", title,
                           f"{path} not found. Create it to document deployment safety.")
    except Exception:
        return _make_check(code, "warning", "info", title,
                           f"Could not verify {path} exists.")


def _check_doc_content(code: str, title: str, path: str,
                        keywords: list[str],
                        pass_msg: str, warn_msg: str) -> dict:
    """Check that a doc file contains at least one of the given keywords."""
    try:
        p = Path(path)
        if not p.exists():
            return _make_check(code, "warning", "info", title,
                               f"{path} not found.")
        text = p.read_text(encoding="utf-8").lower()
        if any(kw.lower() in text for kw in keywords):
            return _make_check(code, "pass", "info", title, pass_msg)
        return _make_check(code, "warning", "info", title, warn_msg)
    except Exception:
        return _make_check(code, "warning", "info", title,
                           f"Could not read {path}.")
