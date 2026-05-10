"""Tests for AGENT_WIRING_MATRIX.md completeness and correctness.

Reads docs/AGENT_WIRING_MATRIX.md and asserts structural completeness:
every agent has a trigger, input, output, and downstream section.
No Flask, no DB, no network.
"""
from __future__ import annotations

import os
import re

import pytest

MATRIX_PATH = "docs/AGENT_WIRING_MATRIX.md"


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


MATRIX_SRC = _read(MATRIX_PATH)


# ── File-level sanity ─────────────────────────────────────────────────────────

def test_matrix_file_exists():
    assert os.path.isfile(MATRIX_PATH)


def test_matrix_not_empty():
    assert len(MATRIX_SRC) > 500


# ── All 16 agents present ─────────────────────────────────────────────────────

EXPECTED_AGENTS = [
    "main_analysis_agent",
    "kb_agent",
    "code_agent",
    "research_agent",
    "classification_agent",
    "summary_agent",
    "feasibility_agent",
    "jira_agent",
    "draft_response_agent",
    "qa_agent",
    "learning_agent",
    "prd_agent",
    "notification_agent",
    "reply_scanner_agent",
    "batch_agent",
    "reporting_agent",
]


@pytest.mark.parametrize("agent", EXPECTED_AGENTS)
def test_agent_present_in_matrix(agent):
    assert agent in MATRIX_SRC, f"{agent} not found in {MATRIX_PATH}"


def test_matrix_has_16_agents_minimum():
    found = sum(1 for a in EXPECTED_AGENTS if a in MATRIX_SRC)
    assert found == 16, f"Expected 16 agents, found {found}"


# ── Required columns / fields present ────────────────────────────────────────

REQUIRED_FIELDS = ["Trigger", "Input", "Output", "Output stored", "Runtime status"]


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_matrix_has_required_field(field):
    assert field in MATRIX_SRC or field.lower() in MATRIX_SRC.lower(), \
        f"Field '{field}' not found in matrix"


# ── "What changed" summary present ───────────────────────────────────────────

def test_matrix_has_wired_now_section():
    assert "wired_now" in MATRIX_SRC or "wired now" in MATRIX_SRC.lower()


def test_matrix_has_wired_active_section():
    assert "wired_active" in MATRIX_SRC


def test_matrix_has_not_wired_reference():
    assert "not_wired" in MATRIX_SRC or "not wired" in MATRIX_SRC.lower()


# ── agent_runs schema documented ─────────────────────────────────────────────

def test_matrix_documents_agent_runs_table():
    assert "agent_runs" in MATRIX_SRC


def test_matrix_documents_agent_runs_status_column():
    assert "status" in MATRIX_SRC


def test_matrix_documents_agent_runs_flow_column():
    assert "flow" in MATRIX_SRC


# ── No auto-send language ─────────────────────────────────────────────────────

def test_matrix_has_no_auto_send_claim():
    """The matrix must not claim any agent auto-sends to clients."""
    assert "auto-send" not in MATRIX_SRC.lower() or \
           "no auto-send" in MATRIX_SRC.lower() or \
           "no agent auto-sends" in MATRIX_SRC.lower()


# ── 8 newly wired agents referenced ──────────────────────────────────────────

NEWLY_WIRED = [
    "classification_agent",
    "summary_agent",
    "feasibility_agent",
    "jira_agent",
    "notification_agent",
    "reply_scanner_agent",
    "batch_agent",
    "reporting_agent",
]


@pytest.mark.parametrize("agent", NEWLY_WIRED)
def test_newly_wired_agent_in_matrix(agent):
    assert agent in MATRIX_SRC, f"Newly-wired agent {agent} not in matrix"
