"""System readiness helper — no LLM calls, no DB writes.

Public function
---------------
build_system_readiness_report(settings: dict | None = None, db=None) -> dict

Returns a stable readiness report suitable for the settings page and the
/api/system-readiness endpoint.

Returned structure::

    {
      "status": str,          # ready / needs_configuration / degraded / unknown
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
      "message": str,    # human-readable; never contains API key values
    }

Rules
-----
- Never raises.
- Never exposes API key values in any field.
- API key presence is reported as "present" or "missing" only.
- DB table checks are best-effort; failures produce warning/fail, not exceptions.
- Score starts at 100; fail deducts 20, warning deducts 8; floored at 0.
- status:
    - unknown: settings is invalid/None AND db is None
    - needs_configuration: any critical config check fails
      (llm_provider_set, llm_api_key_set, freshdesk_domain_set,
       freshdesk_api_key_set)
    - ready: no fails and score >= 85
    - degraded: everything else
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

_CRITICAL_CODES = frozenset({
    "llm_provider_set",
    "llm_api_key_set",
    "freshdesk_domain_set",
    "freshdesk_api_key_set",
})

_SCORE_DEDUCT = {"fail": 20, "warning": 8, "pass": 0, "unknown": 0}

_EMPTY_REPORT: dict = {
    "status": "unknown",
    "score": 0,
    "checks": [],
    "summary": {"pass_count": 0, "warning_count": 0, "fail_count": 0, "unknown_count": 0},
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _check(code: str, status: str, severity: str, title: str, message: str) -> dict:
    return {
        "code": code,
        "status": status,
        "severity": severity,
        "title": title,
        "message": message,
    }


def _table_exists(db, table: str) -> bool:
    """Return True if ``table`` exists in the SQLite DB. Never raises."""
    try:
        row = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        return row is not None
    except Exception:
        return False


def _table_row_count(db, table: str) -> Optional[int]:
    """Return row count for ``table``, or None on error. Never raises."""
    try:
        row = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()  # noqa: S608
        return row[0] if row else 0
    except Exception:
        return None


# ── Individual check builders ─────────────────────────────────────────────────

def _check_db_available(db) -> dict:
    if db is not None:
        return _check(
            "db_available", "pass", "critical",
            "Database available",
            "Database connection is active.",
        )
    return _check(
        "db_available", "warning", "warning",
        "Database unavailable",
        "No database connection provided. Some checks were skipped.",
    )


def _check_llm_provider_set(settings: dict) -> dict:
    value = (settings.get("llm_provider") or "").strip()
    if value:
        return _check(
            "llm_provider_set", "pass", "critical",
            "LLM provider configured",
            f"Provider is set to '{value}'.",
        )
    return _check(
        "llm_provider_set", "fail", "critical",
        "LLM provider not configured",
        "Set the LLM provider in Settings → AI Provider Configuration.",
    )


def _check_llm_api_key_set(settings: dict) -> dict:
    value = (settings.get("llm_api_key") or "").strip()
    if value:
        return _check(
            "llm_api_key_set", "pass", "critical",
            "LLM API key present",
            "LLM API key is configured (value not shown).",
        )
    return _check(
        "llm_api_key_set", "fail", "critical",
        "LLM API key missing",
        "Set the LLM API key in Settings → AI Provider Configuration.",
    )


def _check_freshdesk_domain_set(settings: dict) -> dict:
    value = (settings.get("freshdesk_domain") or "").strip()
    if value:
        return _check(
            "freshdesk_domain_set", "pass", "critical",
            "Freshdesk domain configured",
            f"Domain is set to '{value}'.",
        )
    return _check(
        "freshdesk_domain_set", "fail", "critical",
        "Freshdesk domain not configured",
        "Set the Freshdesk domain in Settings → Freshdesk Configuration.",
    )


def _check_freshdesk_api_key_set(settings: dict) -> dict:
    value = (settings.get("freshdesk_api_key") or "").strip()
    if value:
        return _check(
            "freshdesk_api_key_set", "pass", "critical",
            "Freshdesk API key present",
            "Freshdesk API key is configured (value not shown).",
        )
    return _check(
        "freshdesk_api_key_set", "fail", "critical",
        "Freshdesk API key missing",
        "Set the Freshdesk API key in Settings → Freshdesk Configuration.",
    )


def _check_agent_model_config_seeded(db) -> dict:
    if db is None:
        return _check(
            "agent_model_config_seeded", "unknown", "warning",
            "Agent model config (skipped)",
            "No database connection — cannot verify agent model configuration.",
        )
    if not _table_exists(db, "agent_model_config"):
        return _check(
            "agent_model_config_seeded", "fail", "warning",
            "Agent model config table missing",
            "The agent_model_config table does not exist. Run the app once to initialise the DB.",
        )
    count = _table_row_count(db, "agent_model_config")
    if count is None:
        return _check(
            "agent_model_config_seeded", "warning", "warning",
            "Agent model config unreadable",
            "Could not read agent_model_config table.",
        )
    if count == 0:
        return _check(
            "agent_model_config_seeded", "warning", "warning",
            "Agent model config not seeded",
            "No agent model configurations found. Restart the app to auto-seed defaults.",
        )
    return _check(
        "agent_model_config_seeded", "pass", "info",
        "Agent model config seeded",
        f"{count} agent model configuration(s) found.",
    )


def _check_kb_entries_available(db) -> dict:
    if db is None:
        return _check(
            "kb_entries_available", "unknown", "info",
            "Knowledge base (skipped)",
            "No database connection — cannot verify knowledge base.",
        )
    if not _table_exists(db, "knowledge_base"):
        return _check(
            "kb_entries_available", "warning", "info",
            "Knowledge base table missing",
            "The knowledge_base table does not exist.",
        )
    count = _table_row_count(db, "knowledge_base")
    if count is None:
        return _check(
            "kb_entries_available", "warning", "info",
            "Knowledge base unreadable",
            "Could not read knowledge_base table.",
        )
    if count == 0:
        return _check(
            "kb_entries_available", "warning", "info",
            "No knowledge base entries",
            "Add KB entries in Settings → Knowledge Base for better AI context.",
        )
    return _check(
        "kb_entries_available", "pass", "info",
        "Knowledge base populated",
        f"{count} knowledge base entry/entries found.",
    )


def _check_safe_to_send_available() -> dict:
    try:
        from ai.safe_to_send_review import build_safe_to_send_review  # noqa: F401
        return _check(
            "safe_to_send_available", "pass", "info",
            "Safe-to-send module available",
            "Safe-to-send review module loaded successfully.",
        )
    except ImportError:
        return _check(
            "safe_to_send_available", "warning", "info",
            "Safe-to-send module unavailable",
            "Could not import ai.safe_to_send_review.",
        )


def _check_main_llm_helper_available() -> dict:
    try:
        from ai.main_llm import complete_main_llm  # noqa: F401
        return _check(
            "main_llm_helper_available", "pass", "info",
            "Main LLM helper available",
            "LLM routing helper (complete_main_llm) loaded successfully.",
        )
    except ImportError:
        return _check(
            "main_llm_helper_available", "warning", "info",
            "Main LLM helper unavailable",
            "Could not import ai.main_llm.complete_main_llm.",
        )


# ── DB table presence checks ─────────────────────────────────────────────────

def _check_db_tables(db) -> list[dict]:
    """Return one check per required DB table. Returns [] if db is None."""
    if db is None:
        return []
    results = []
    for table in ("settings", "tickets", "knowledge_base", "agent_model_config"):
        if _table_exists(db, table):
            results.append(_check(
                f"db_table_{table}", "pass", "info",
                f"DB table '{table}' present",
                f"Table '{table}' exists in the database.",
            ))
        else:
            results.append(_check(
                f"db_table_{table}", "warning", "warning",
                f"DB table '{table}' missing",
                f"Table '{table}' not found. The app will create it on first run.",
            ))
    return results


# ── Score and status ─────────────────────────────────────────────────────────

def _compute_score(checks: list[dict]) -> int:
    score = 100
    for c in checks:
        score -= _SCORE_DEDUCT.get(c.get("status", "unknown"), 0)
    return max(0, score)


def _compute_status(
    checks: list[dict],
    score: int,
    settings_valid: bool,
    db: object,
) -> str:
    # Unknown: no usable input at all
    if not settings_valid and db is None:
        return "unknown"

    # needs_configuration: any critical config check failed
    critical_fails = [
        c for c in checks
        if c.get("code") in _CRITICAL_CODES and c.get("status") == "fail"
    ]
    if critical_fails:
        return "needs_configuration"

    # ready: no fails and good score
    any_fail = any(c.get("status") == "fail" for c in checks)
    if not any_fail and score >= 85:
        return "ready"

    return "degraded"


def _compute_summary(checks: list[dict]) -> dict:
    counts = {"pass_count": 0, "warning_count": 0, "fail_count": 0, "unknown_count": 0}
    for c in checks:
        s = c.get("status", "unknown")
        if s == "pass":
            counts["pass_count"] += 1
        elif s == "warning":
            counts["warning_count"] += 1
        elif s == "fail":
            counts["fail_count"] += 1
        else:
            counts["unknown_count"] += 1
    return counts


# ── Public API ────────────────────────────────────────────────────────────────

def build_system_readiness_report(
    settings: Optional[dict] = None,
    db=None,
) -> dict:
    """Build a system readiness report.

    Parameters
    ----------
    settings:
        Dict with keys: llm_provider, llm_api_key, freshdesk_domain,
        freshdesk_api_key, freshdesk_group_id.
        May be None or invalid — handled defensively.
    db:
        Active DB connection (sqlite3 / Flask-SQLite).
        May be None.

    Returns
    -------
    dict
        ``{"status", "score", "checks", "summary"}``.
        Never raises. Never exposes API key values.
    """
    try:
        settings_valid = isinstance(settings, dict) and bool(settings)
        safe_settings = settings if settings_valid else {}

        checks: list[dict] = []

        # DB availability
        checks.append(_check_db_available(db))

        # Critical configuration checks
        checks.append(_check_llm_provider_set(safe_settings))
        checks.append(_check_llm_api_key_set(safe_settings))
        checks.append(_check_freshdesk_domain_set(safe_settings))
        checks.append(_check_freshdesk_api_key_set(safe_settings))

        # Agent model config
        checks.append(_check_agent_model_config_seeded(db))

        # Knowledge base
        checks.append(_check_kb_entries_available(db))

        # Module availability
        checks.append(_check_safe_to_send_available())
        checks.append(_check_main_llm_helper_available())

        # DB table presence (only when db is provided)
        checks.extend(_check_db_tables(db))

        score = _compute_score(checks)
        status = _compute_status(checks, score, settings_valid, db)
        summary = _compute_summary(checks)

        logger.debug(
            f"build_system_readiness_report: status={status} score={score} "
            f"checks={len(checks)}"
        )

        return {
            "status": status,
            "score": score,
            "checks": checks,
            "summary": summary,
        }

    except Exception as exc:
        logger.warning(f"build_system_readiness_report: unexpected error: {exc}")
        return dict(_EMPTY_REPORT)
