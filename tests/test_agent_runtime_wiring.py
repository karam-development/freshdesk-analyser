"""Source-level wiring tests: verify all 16 agents have real call sites.

Reads app.py and agents.py — no Flask, no DB, no network.
"""
from __future__ import annotations

import ast
import re

import pytest


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


APP_SRC = _read("app.py")
AGENTS_SRC = _read("agents.py")


# ── agents.py: standalone agent functions exist ───────────────────────────────

STANDALONE_AGENT_FUNCTIONS = [
    "classification_agent",
    "summary_agent",
    "feasibility_agent",
    "jira_agent",
    "notification_agent",
    "reply_scanner_agent",
    "batch_agent",
    "reporting_agent",
]


@pytest.mark.parametrize("fn", STANDALONE_AGENT_FUNCTIONS)
def test_agent_function_defined_in_agents_py(fn):
    assert f"def {fn}(" in AGENTS_SRC, f"def {fn}() not found in agents.py"


# ── agents.py: orchestrator runner methods exist ──────────────────────────────

ORCHESTRATOR_RUNNER_METHODS = [
    "run_classification",
    "run_summary",
    "run_feasibility",
    "run_jira_summary",
    "run_notification_preview",
    "run_reply_scanner",
    "run_batch_plan",
    "run_report",
]


@pytest.mark.parametrize("method", ORCHESTRATOR_RUNNER_METHODS)
def test_orchestrator_method_defined_in_agents_py(method):
    assert f"def {method}(" in AGENTS_SRC, f"def {method}() not in AgentOrchestrator"


# ── agents.py: _record_agent_run exists ──────────────────────────────────────

def test_record_agent_run_defined():
    assert "def _record_agent_run(" in AGENTS_SRC


# ── agents.py: get_agent_runs exists ─────────────────────────────────────────

def test_get_agent_runs_defined():
    assert "def get_agent_runs(" in AGENTS_SRC


# ── agents.py: agent_runs table in SQL schema ─────────────────────────────────

def test_agent_runs_table_in_schema():
    assert "CREATE TABLE IF NOT EXISTS agent_runs" in AGENTS_SRC


def test_agent_runs_status_column_in_schema():
    idx = AGENTS_SRC.find("CREATE TABLE IF NOT EXISTS agent_runs")
    snippet = AGENTS_SRC[idx:idx + 600]
    assert "status" in snippet


def test_agent_runs_flow_column_in_schema():
    idx = AGENTS_SRC.find("CREATE TABLE IF NOT EXISTS agent_runs")
    snippet = AGENTS_SRC[idx:idx + 600]
    assert "flow" in snippet


def test_agent_runs_output_json_column_in_schema():
    idx = AGENTS_SRC.find("CREATE TABLE IF NOT EXISTS agent_runs")
    snippet = AGENTS_SRC[idx:idx + 600]
    assert "output_json" in snippet


# ── app.py: call sites for newly-wired agents ─────────────────────────────────

APP_CALL_SITES = [
    ("orchestrator.run_classification(", "classification_agent call site"),
    ("orchestrator.run_summary(", "summary_agent call site"),
    ("orchestrator.run_feasibility(", "feasibility_agent call site"),
    ("orchestrator.run_jira_summary(", "jira_agent call site"),
    ("orchestrator.run_notification_preview(", "notification_agent call site"),
    ("orchestrator.run_reply_scanner(", "reply_scanner_agent call site"),
    ("orchestrator.run_batch_plan(", "batch_agent call site"),
    ("orchestrator.run_report(", "reporting_agent call site"),
]


@pytest.mark.parametrize("call_site,description", APP_CALL_SITES)
def test_call_site_present_in_app_py(call_site, description):
    assert call_site in APP_SRC, f"{description} not found in app.py: {call_site!r}"


# ── app.py: new API routes registered ────────────────────────────────────────

NEW_ROUTES = [
    '/ticket/<int:ticket_id>/scan-replies',
    '/ticket/<int:ticket_id>/notification-preview',
    '/api/batch/plan',
    '/api/reports/generate-ai',
]


@pytest.mark.parametrize("route", NEW_ROUTES)
def test_new_route_registered_in_app_py(route):
    assert route in APP_SRC, f"Route {route!r} not registered in app.py"


# ── app.py: existing wired agents still present ───────────────────────────────

EXISTING_CALL_SITES = [
    "run_preparation_agents_parallel(",
    "run_qa_with_retry(",
    "run_learning(",
]


@pytest.mark.parametrize("site", EXISTING_CALL_SITES)
def test_existing_wired_agent_still_present(site):
    assert site in APP_SRC, f"Existing call site {site!r} was removed from app.py"


# ── app.py: agent_runtime_map built and passed to template ───────────────────

def test_agent_runtime_map_built_in_agent_dashboard():
    pos_func = APP_SRC.find("def agent_dashboard(")
    pos_map = APP_SRC.find("agent_runtime_map")
    assert pos_func != -1
    assert pos_map != -1
    assert pos_map > pos_func


def test_agent_runtime_map_passed_to_render_template():
    assert "agent_runtime_map=agent_runtime_map" in APP_SRC


def test_agent_runtime_map_has_16_entries():
    """The _AGENT_REGISTRY list in app.py must have 16 entries."""
    idx = APP_SRC.find("_AGENT_REGISTRY = [")
    assert idx != -1, "_AGENT_REGISTRY not found in app.py"
    # Find end of the list (closing bracket at same indentation)
    end_idx = APP_SRC.find("\n    ]\n", idx)
    if end_idx == -1:
        end_idx = idx + 3000
    snippet = APP_SRC[idx:end_idx]
    count = snippet.count('"agent_name"')
    assert count == 16, f"Expected 16 entries in _AGENT_REGISTRY, found {count}"


# ── app.py: agent_runs + agent_briefs injected into ticket_detail ─────────────

def test_ticket_detail_injects_agent_runs():
    assert 'ticket_dict["agent_runs"]' in APP_SRC


def test_ticket_detail_injects_agent_briefs():
    assert 'ticket_dict["agent_briefs"]' in APP_SRC
