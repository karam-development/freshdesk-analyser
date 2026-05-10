"""Source-level tests for agents.html Runtime Agent Map.

Reads templates/agents.html only — no Flask, no DB, no network.
"""
from __future__ import annotations
import pytest


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


AGENTS = _read("templates/agents.html")


# ── Runtime Agent Map present ─────────────────────────────────────────────────

def test_has_runtime_agent_map():
    assert "Runtime Agent Map" in AGENTS


def test_no_pipeline_architecture_h3():
    """The old 'Pipeline Architecture' card title must be gone."""
    # Accept it only if it's not in an H-tag or card heading
    assert "Pipeline Architecture" not in AGENTS


def test_no_hardcoded_active_agents_run_today():
    """Old text 'active agents run today' must be gone."""
    assert "active agents run today" not in AGENTS
    assert "run today" not in AGENTS


# ── Runtime map content ───────────────────────────────────────────────────────

def test_runtime_map_uses_agent_runtime_map_variable():
    assert "agent_runtime_map" in AGENTS


def test_runtime_map_has_table():
    idx = AGENTS.find("Runtime Agent Map")
    nearby = AGENTS[idx:idx + 5000]
    assert "<table" in nearby


def test_runtime_map_shows_wired_now_badge():
    assert "wired · new" in AGENTS or "wired_now" in AGENTS


def test_runtime_map_shows_wired_active_badge():
    assert "wired · active" in AGENTS or "wired_active" in AGENTS


def test_runtime_map_shows_completed_runs():
    assert "completed_runs" in AGENTS


def test_runtime_map_shows_last_run():
    idx = AGENTS.find("Runtime Agent Map")
    nearby = AGENTS[idx:idx + 6000]
    assert "last_run" in nearby


def test_runtime_map_shows_trigger():
    idx = AGENTS.find("Runtime Agent Map")
    nearby = AGENTS[idx:idx + 6000]
    assert "trigger" in nearby.lower()


def test_runtime_map_shows_runtime_status():
    idx = AGENTS.find("Runtime Agent Map")
    nearby = AGENTS[idx:idx + 6000]
    assert "runtime_status" in nearby or "Runtime Status" in nearby


def test_runtime_map_has_fallback():
    """Must degrade gracefully when no agent_runtime_map data."""
    assert "{% else %}" in AGENTS or "fallback" in AGENTS.lower()


# ── Safety ───────────────────────────────────────────────────────────────────

def test_no_api_keys_rendered():
    assert "api_key" not in AGENTS or "{{ cfg.api_key" not in AGENTS
    assert "ANTHROPIC_API_KEY" not in AGENTS
    assert "sk-ant" not in AGENTS


def test_no_auto_send_claim():
    """If 'auto-send' mentioned, must be in a 'no auto-send' context."""
    if "auto-send" in AGENTS.lower():
        assert "no agent auto-sends" in AGENTS.lower() or "no auto-send" in AGENTS.lower()


# ── Agent catalog table still present ────────────────────────────────────────

def test_agent_catalog_table_still_present():
    """The existing Agent Model Configuration table must not be removed."""
    assert "agent_catalog_rows" in AGENTS or "Agent Model Configuration" in AGENTS
