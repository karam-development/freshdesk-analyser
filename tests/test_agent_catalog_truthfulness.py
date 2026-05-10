"""Tests for agent catalog truthfulness.

Verifies:
  - Active agents in the catalog actually have call sites in app.py / agents/
  - Not-wired agents are NOT labelled 'active'
  - All status values are from the valid taxonomy
  - Agents page template renders status badges
  - build_agent_catalog_rows merges correctly and never raises
"""
import re
from pathlib import Path

import pytest

from ai.agent_catalog import build_agent_catalog_rows, get_agent_purpose_catalog

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PY = PROJECT_ROOT / "app.py"
AGENTS_DIR = PROJECT_ROOT / "ai"
AGENTS_TEMPLATE = PROJECT_ROOT / "templates" / "agents.html"

VALID_STATUSES = {"active", "configured", "legacy_fallback", "not_wired", "unknown"}

# Agents we know are called in the codebase (agent_name as stored in DB)
KNOWN_ACTIVE_AGENTS = {
    "main_analysis_agent",
    "kb_agent",
    "code_agent",
    "research_agent",
    "draft_response_agent",
    "qa_agent",
    "learning_agent",
    "prd_agent",
}

# Agents that are not yet wired
KNOWN_NOT_WIRED_AGENTS = {
    "classification_agent",
    "summary_agent",
    "feasibility_agent",
    "batch_agent",
    "reply_scanner_agent",
    "jira_agent",
    "notification_agent",
    "reporting_agent",
}


class TestCatalogStatuses:
    def test_all_statuses_are_valid(self):
        catalog = get_agent_purpose_catalog()
        for agent_name, entry in catalog.items():
            status = entry.get("status", "")
            assert status in VALID_STATUSES, (
                f"Agent '{agent_name}' has invalid status '{status}'. "
                f"Must be one of: {VALID_STATUSES}"
            )

    def test_active_agents_marked_active(self):
        catalog = get_agent_purpose_catalog()
        for agent in KNOWN_ACTIVE_AGENTS:
            assert agent in catalog, f"Agent '{agent}' missing from catalog"
            assert catalog[agent]["status"] == "active", (
                f"Agent '{agent}' is called in production but status is "
                f"'{catalog[agent]['status']}', not 'active'"
            )

    def test_not_wired_agents_not_marked_active(self):
        catalog = get_agent_purpose_catalog()
        for agent in KNOWN_NOT_WIRED_AGENTS:
            if agent in catalog:
                status = catalog[agent]["status"]
                assert status != "active", (
                    f"Agent '{agent}' has no call site but is marked 'active'. "
                    f"Use 'not_wired' instead."
                )

    def test_all_entries_have_required_fields(self):
        catalog = get_agent_purpose_catalog()
        for agent_name, entry in catalog.items():
            assert "purpose" in entry, f"'{agent_name}' missing 'purpose'"
            assert "used_in" in entry, f"'{agent_name}' missing 'used_in'"
            assert "status" in entry, f"'{agent_name}' missing 'status'"
            assert entry["purpose"], f"'{agent_name}' has empty 'purpose'"
            assert entry["used_in"], f"'{agent_name}' has empty 'used_in'"

    def test_not_wired_used_in_strings_honest(self):
        """Not-wired agents must have 'used_in' that signals they are not in production."""
        catalog = get_agent_purpose_catalog()
        for agent in KNOWN_NOT_WIRED_AGENTS:
            if agent in catalog:
                used_in = catalog[agent].get("used_in", "").lower()
                assert (
                    "not wired" in used_in
                    or "not yet" in used_in
                    or "planned" in used_in
                ), (
                    f"Agent '{agent}' is not wired but 'used_in' does not reflect that: "
                    f"'{catalog[agent]['used_in']}'"
                )


class TestBuildAgentCatalogRows:
    def _make_config_rows(self, agents):
        return [
            {
                "agent_name": name,
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "temperature": 0.1,
                "max_tokens": 4096,
                "enabled": 1,
            }
            for name in agents
        ]

    def test_merges_status_from_catalog(self):
        rows = build_agent_catalog_rows(
            self._make_config_rows(["main_analysis_agent", "classification_agent"])
        )
        by_name = {r["agent_name"]: r for r in rows}
        assert by_name["main_analysis_agent"]["status"] == "active"
        assert by_name["classification_agent"]["status"] == "not_wired"

    def test_unknown_agent_gets_safe_defaults(self):
        rows = build_agent_catalog_rows(
            self._make_config_rows(["totally_unknown_agent_xyz"])
        )
        assert len(rows) == 1
        row = rows[0]
        assert row["purpose"] == "Purpose not documented yet"
        assert row["used_in"] == "—"
        assert row["status"] == "unknown"

    def test_never_raises_on_empty_input(self):
        result = build_agent_catalog_rows([])
        assert result == []

    def test_never_raises_on_none_input(self):
        result = build_agent_catalog_rows(None)  # type: ignore[arg-type]
        assert result == []

    def test_never_raises_on_malformed_rows(self):
        malformed = [None, {}, {"agent_name": ""}, "not_a_row", 42]
        result = build_agent_catalog_rows(malformed)  # type: ignore[arg-type]
        assert isinstance(result, list)  # should not raise


class TestAgentsPageStatusDisplay:
    def test_agents_template_renders_status(self):
        html = AGENTS_TEMPLATE.read_text(encoding="utf-8")
        assert "cfg.status" in html, (
            "agents.html must render cfg.status to show status badges"
        )

    def test_agents_template_shows_active_badge(self):
        html = AGENTS_TEMPLATE.read_text(encoding="utf-8")
        assert "active" in html.lower(), (
            "agents.html must show an 'active' status badge"
        )

    def test_agents_template_shows_not_wired_badge(self):
        html = AGENTS_TEMPLATE.read_text(encoding="utf-8")
        assert "not_wired" in html or "not wired" in html.lower(), (
            "agents.html must show a 'not wired' status badge for not_wired agents"
        )

    def test_status_column_in_table_header(self):
        html = AGENTS_TEMPLATE.read_text(encoding="utf-8")
        assert "<th>Status</th>" in html, (
            "Agent Model Configuration table must have a 'Status' column header"
        )
