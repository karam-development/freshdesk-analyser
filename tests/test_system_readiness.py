"""Unit tests for ai/system_readiness.py — PR 31.

Tests cover:
- Return structure and types
- empty/None settings → needs_configuration
- LLM provider + key present → those checks pass
- Freshdesk domain + key present → those checks pass
- API key values never appear in the report
- db=None → unknown or degraded, no crash
- db with required tables → db checks pass
- db without KB entries → warning
- db with KB entries → pass
- agent_model_config seeded check
- score floor at 0
- status=ready when all required checks pass
- status=needs_configuration when LLM/Freshdesk missing
- function never mutates settings input
"""
from __future__ import annotations

import copy
import sqlite3

import pytest

from ai.system_readiness import build_system_readiness_report


# ── Helpers ────────────────────────────────────────────────────────────────────

def _full_settings():
    return {
        "llm_provider": "openai",
        "llm_api_key": "sk-test-secret-key",
        "freshdesk_domain": "silverfin.freshdesk.com",
        "freshdesk_api_key": "freshdesk-secret-key",
        "freshdesk_group_id": "101000372179",
    }


def _make_db_with_tables(kb_count: int = 0, agent_count: int = 3):
    """Create an in-memory SQLite DB with all required tables."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    db.execute("CREATE TABLE tickets (id INTEGER PRIMARY KEY)")
    db.execute("""CREATE TABLE knowledge_base (
        id INTEGER PRIMARY KEY,
        category TEXT,
        title TEXT,
        content TEXT
    )""")
    db.execute("""CREATE TABLE agent_model_config (
        agent_name TEXT PRIMARY KEY,
        provider TEXT,
        model TEXT,
        max_tokens INTEGER,
        temperature REAL
    )""")
    for i in range(kb_count):
        db.execute(
            "INSERT INTO knowledge_base (category, title, content) VALUES (?, ?, ?)",
            ("cat", f"Entry {i}", f"Content {i}"),
        )
    for i in range(agent_count):
        db.execute(
            "INSERT INTO agent_model_config (agent_name, provider, model, max_tokens, temperature) VALUES (?, ?, ?, ?, ?)",
            (f"agent_{i}", "openai", "gpt-4o", 4000, 0.3),
        )
    db.commit()
    return db


def _make_empty_db():
    """DB with no tables at all."""
    return sqlite3.connect(":memory:")


# ── Return structure ───────────────────────────────────────────────────────────

def test_returns_dict():
    assert isinstance(build_system_readiness_report(), dict)


def test_has_status_key():
    assert "status" in build_system_readiness_report()


def test_has_score_key():
    assert "score" in build_system_readiness_report()


def test_has_checks_key():
    assert "checks" in build_system_readiness_report()


def test_has_summary_key():
    assert "summary" in build_system_readiness_report()


def test_checks_is_list():
    assert isinstance(build_system_readiness_report()["checks"], list)


def test_score_is_int():
    assert isinstance(build_system_readiness_report()["score"], int)


def test_each_check_has_required_keys():
    result = build_system_readiness_report(_full_settings())
    for check in result["checks"]:
        for key in ("code", "status", "severity", "title", "message"):
            assert key in check, f"Check missing key '{key}': {check}"


def test_check_status_values_valid():
    result = build_system_readiness_report(_full_settings())
    valid = {"pass", "warning", "fail", "unknown"}
    for check in result["checks"]:
        assert check["status"] in valid, f"Invalid status: {check['status']}"


def test_check_severity_values_valid():
    result = build_system_readiness_report(_full_settings())
    valid = {"critical", "warning", "info"}
    for check in result["checks"]:
        assert check["severity"] in valid, f"Invalid severity: {check['severity']}"


def test_status_values_valid():
    result = build_system_readiness_report()
    assert result["status"] in {"ready", "needs_configuration", "degraded", "unknown"}


def test_summary_has_count_keys():
    summary = build_system_readiness_report()["summary"]
    for k in ("pass_count", "warning_count", "fail_count", "unknown_count"):
        assert k in summary


# ── None / empty / invalid input ──────────────────────────────────────────────

def test_none_settings_no_db_returns_unknown_or_needs_config():
    result = build_system_readiness_report(None, db=None)
    assert result["status"] in {"unknown", "needs_configuration"}


def test_empty_dict_no_db():
    result = build_system_readiness_report({}, db=None)
    assert result["status"] in {"unknown", "needs_configuration", "degraded"}


def test_none_settings_has_data():
    result = build_system_readiness_report(None)
    assert isinstance(result, dict)
    assert "status" in result


def test_empty_settings_is_needs_configuration():
    result = build_system_readiness_report({})
    assert result["status"] in {"needs_configuration", "unknown"}


def test_string_input_no_crash():
    result = build_system_readiness_report("bad")  # type: ignore
    assert isinstance(result, dict)


def test_none_input_no_crash():
    result = build_system_readiness_report(None)
    assert isinstance(result, dict)


# ── LLM provider / key checks ────────────────────────────────────────────────

def test_llm_provider_present_check_passes():
    result = build_system_readiness_report({"llm_provider": "openai"})
    provider_check = next(
        (c for c in result["checks"] if c["code"] == "llm_provider_set"), None
    )
    assert provider_check is not None
    assert provider_check["status"] == "pass"


def test_llm_provider_missing_check_fails():
    result = build_system_readiness_report({"llm_provider": ""})
    provider_check = next(
        (c for c in result["checks"] if c["code"] == "llm_provider_set"), None
    )
    assert provider_check is not None
    assert provider_check["status"] == "fail"


def test_llm_api_key_present_check_passes():
    result = build_system_readiness_report({"llm_api_key": "sk-test-key"})
    key_check = next(
        (c for c in result["checks"] if c["code"] == "llm_api_key_set"), None
    )
    assert key_check is not None
    assert key_check["status"] == "pass"


def test_llm_api_key_missing_check_fails():
    result = build_system_readiness_report({"llm_api_key": ""})
    key_check = next(
        (c for c in result["checks"] if c["code"] == "llm_api_key_set"), None
    )
    assert key_check is not None
    assert key_check["status"] == "fail"


# ── Freshdesk checks ──────────────────────────────────────────────────────────

def test_freshdesk_domain_present_check_passes():
    result = build_system_readiness_report({"freshdesk_domain": "acme.freshdesk.com"})
    check = next(
        (c for c in result["checks"] if c["code"] == "freshdesk_domain_set"), None
    )
    assert check is not None
    assert check["status"] == "pass"


def test_freshdesk_domain_missing_check_fails():
    result = build_system_readiness_report({"freshdesk_domain": ""})
    check = next(
        (c for c in result["checks"] if c["code"] == "freshdesk_domain_set"), None
    )
    assert check is not None
    assert check["status"] == "fail"


def test_freshdesk_api_key_present_check_passes():
    result = build_system_readiness_report({"freshdesk_api_key": "fd-secret"})
    check = next(
        (c for c in result["checks"] if c["code"] == "freshdesk_api_key_set"), None
    )
    assert check is not None
    assert check["status"] == "pass"


def test_freshdesk_api_key_missing_check_fails():
    result = build_system_readiness_report({"freshdesk_api_key": ""})
    check = next(
        (c for c in result["checks"] if c["code"] == "freshdesk_api_key_set"), None
    )
    assert check is not None
    assert check["status"] == "fail"


# ── API key values never appear in report ────────────────────────────────────

def test_api_key_value_not_in_any_check_message():
    settings = _full_settings()
    result = build_system_readiness_report(settings)
    llm_key = settings["llm_api_key"]
    fd_key = settings["freshdesk_api_key"]
    full_text = str(result)
    assert llm_key not in full_text
    assert fd_key not in full_text


def test_api_key_value_not_in_status():
    settings = _full_settings()
    result = build_system_readiness_report(settings)
    assert settings["llm_api_key"] not in result["status"]


def test_api_key_check_message_says_not_shown():
    settings = _full_settings()
    result = build_system_readiness_report(settings)
    key_check = next(
        (c for c in result["checks"] if c["code"] == "llm_api_key_set"), None
    )
    assert key_check is not None
    assert settings["llm_api_key"] not in key_check["message"]
    # Should indicate presence without revealing value
    msg_lower = key_check["message"].lower()
    assert "present" in msg_lower or "configured" in msg_lower or "not shown" in msg_lower


# ── db=None → no crash ────────────────────────────────────────────────────────

def test_db_none_no_crash():
    result = build_system_readiness_report(_full_settings(), db=None)
    assert isinstance(result, dict)


def test_db_none_db_check_is_warning():
    result = build_system_readiness_report(_full_settings(), db=None)
    db_check = next(
        (c for c in result["checks"] if c["code"] == "db_available"), None
    )
    assert db_check is not None
    assert db_check["status"] == "warning"


def test_db_none_no_table_checks():
    result = build_system_readiness_report(_full_settings(), db=None)
    table_checks = [c for c in result["checks"] if c["code"].startswith("db_table_")]
    assert table_checks == []


# ── DB with required tables ───────────────────────────────────────────────────

def test_db_with_tables_db_check_passes():
    db = _make_db_with_tables()
    result = build_system_readiness_report(_full_settings(), db=db)
    db_check = next(
        (c for c in result["checks"] if c["code"] == "db_available"), None
    )
    assert db_check is not None
    assert db_check["status"] == "pass"


def test_db_with_tables_produces_table_checks():
    db = _make_db_with_tables()
    result = build_system_readiness_report(_full_settings(), db=db)
    table_checks = [c for c in result["checks"] if c["code"].startswith("db_table_")]
    assert len(table_checks) > 0


def test_db_table_settings_passes():
    db = _make_db_with_tables()
    result = build_system_readiness_report(_full_settings(), db=db)
    check = next(
        (c for c in result["checks"] if c["code"] == "db_table_settings"), None
    )
    assert check is not None
    assert check["status"] == "pass"


def test_db_table_tickets_passes():
    db = _make_db_with_tables()
    result = build_system_readiness_report(_full_settings(), db=db)
    check = next(
        (c for c in result["checks"] if c["code"] == "db_table_tickets"), None
    )
    assert check is not None
    assert check["status"] == "pass"


def test_db_without_knowledge_base_table_warns():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    db.execute("CREATE TABLE tickets (id INTEGER PRIMARY KEY)")
    db.execute("CREATE TABLE agent_model_config (agent_name TEXT PRIMARY KEY)")
    db.commit()
    result = build_system_readiness_report(_full_settings(), db=db)
    check = next(
        (c for c in result["checks"] if c["code"] == "db_table_knowledge_base"), None
    )
    assert check is not None
    assert check["status"] == "warning"


# ── KB entries ────────────────────────────────────────────────────────────────

def test_db_without_kb_entries_warns():
    db = _make_db_with_tables(kb_count=0)
    result = build_system_readiness_report(_full_settings(), db=db)
    check = next(
        (c for c in result["checks"] if c["code"] == "kb_entries_available"), None
    )
    assert check is not None
    assert check["status"] == "warning"


def test_db_with_kb_entries_passes():
    db = _make_db_with_tables(kb_count=3)
    result = build_system_readiness_report(_full_settings(), db=db)
    check = next(
        (c for c in result["checks"] if c["code"] == "kb_entries_available"), None
    )
    assert check is not None
    assert check["status"] == "pass"


# ── Agent model config ────────────────────────────────────────────────────────

def test_agent_model_config_seeded_passes():
    db = _make_db_with_tables(agent_count=3)
    result = build_system_readiness_report(_full_settings(), db=db)
    check = next(
        (c for c in result["checks"] if c["code"] == "agent_model_config_seeded"), None
    )
    assert check is not None
    assert check["status"] == "pass"


def test_agent_model_config_empty_warns():
    db = _make_db_with_tables(agent_count=0)
    result = build_system_readiness_report(_full_settings(), db=db)
    check = next(
        (c for c in result["checks"] if c["code"] == "agent_model_config_seeded"), None
    )
    assert check is not None
    assert check["status"] == "warning"


def test_agent_model_config_no_db_is_unknown():
    result = build_system_readiness_report(_full_settings(), db=None)
    check = next(
        (c for c in result["checks"] if c["code"] == "agent_model_config_seeded"), None
    )
    assert check is not None
    assert check["status"] == "unknown"


# ── Score floor ───────────────────────────────────────────────────────────────

def test_score_floor_at_0():
    # Empty settings → multiple fails; score must not go below 0
    result = build_system_readiness_report({})
    assert result["score"] >= 0


def test_score_is_100_max():
    db = _make_db_with_tables(kb_count=1, agent_count=3)
    result = build_system_readiness_report(_full_settings(), db=db)
    assert result["score"] <= 100


# ── Status: ready ─────────────────────────────────────────────────────────────

def test_status_ready_when_all_checks_pass():
    db = _make_db_with_tables(kb_count=1, agent_count=3)
    result = build_system_readiness_report(_full_settings(), db=db)
    assert result["status"] == "ready"
    assert result["score"] >= 85


# ── Status: needs_configuration ──────────────────────────────────────────────

def test_status_needs_configuration_when_llm_key_missing():
    settings = _full_settings()
    settings["llm_api_key"] = ""
    result = build_system_readiness_report(settings)
    assert result["status"] == "needs_configuration"


def test_status_needs_configuration_when_llm_provider_missing():
    settings = _full_settings()
    settings["llm_provider"] = ""
    result = build_system_readiness_report(settings)
    assert result["status"] == "needs_configuration"


def test_status_needs_configuration_when_freshdesk_domain_missing():
    settings = _full_settings()
    settings["freshdesk_domain"] = ""
    result = build_system_readiness_report(settings)
    assert result["status"] == "needs_configuration"


def test_status_needs_configuration_when_freshdesk_api_key_missing():
    settings = _full_settings()
    settings["freshdesk_api_key"] = ""
    result = build_system_readiness_report(settings)
    assert result["status"] == "needs_configuration"


def test_status_needs_configuration_when_all_missing():
    result = build_system_readiness_report({})
    assert result["status"] in {"needs_configuration", "unknown"}


# ── Input mutation check ──────────────────────────────────────────────────────

def test_does_not_mutate_settings():
    settings = _full_settings()
    original = copy.deepcopy(settings)
    build_system_readiness_report(settings)
    assert settings == original


# ── Acceptance scenario from PR spec ─────────────────────────────────────────

def test_acceptance_full_setup():
    """Full configured setup → status=ready, score>=85, keys not exposed."""
    settings = {
        "llm_provider": "openai",
        "llm_api_key": "sk-test-secret",
        "freshdesk_domain": "silverfin.freshdesk.com",
        "freshdesk_api_key": "freshdesk-secret",
    }
    db = _make_db_with_tables(kb_count=1, agent_count=3)
    result = build_system_readiness_report(settings, db=db)

    assert result["status"] == "ready"
    assert result["score"] >= 85

    # API keys must not appear in report
    full_text = str(result)
    assert "sk-test-secret" not in full_text
    assert "freshdesk-secret" not in full_text

    # LLM key check should say "present"
    key_check = next(c for c in result["checks"] if c["code"] == "llm_api_key_set")
    assert key_check["status"] == "pass"
    assert "sk-test-secret" not in key_check["message"]

    # KB check should pass
    kb_check = next(c for c in result["checks"] if c["code"] == "kb_entries_available")
    assert kb_check["status"] == "pass"
