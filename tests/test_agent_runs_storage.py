"""Tests for agent_runs DB table: schema, idempotent migration, CRUD.

Uses an in-memory SQLite database — no Flask, no network, no file I/O.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pytest

from agents import init_agent_tables, AgentOrchestrator


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mem_db():
    """In-memory SQLite DB with agent tables initialised."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    init_agent_tables(db)
    yield db
    db.close()


@pytest.fixture
def orchestrator(mem_db):
    return AgentOrchestrator("dummy-key", db=mem_db)


# ── Migration idempotency ─────────────────────────────────────────────────────

def test_init_agent_tables_idempotent(mem_db):
    """Running init_agent_tables twice must not raise."""
    init_agent_tables(mem_db)  # second call
    init_agent_tables(mem_db)  # third call — still fine


def test_agent_runs_table_exists(mem_db):
    row = mem_db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_runs'"
    ).fetchone()
    assert row is not None


# ── Required columns ─────────────────────────────────────────────────────────

REQUIRED_COLUMNS = [
    "id", "ticket_id", "agent_name", "flow", "status",
    "input_summary", "output_summary", "output_json",
    "error", "started_at", "finished_at", "duration_ms",
    "provider", "model",
]


def test_agent_runs_has_required_columns(mem_db):
    cols = {row[1] for row in mem_db.execute("PRAGMA table_info(agent_runs)").fetchall()}
    for col in REQUIRED_COLUMNS:
        assert col in cols, f"Column '{col}' missing from agent_runs"


# ── Indexes created ───────────────────────────────────────────────────────────

def test_agent_runs_index_on_ticket_id(mem_db):
    indexes = {row[1] for row in mem_db.execute(
        "SELECT * FROM sqlite_master WHERE type='index' AND tbl_name='agent_runs'"
    ).fetchall()}
    assert any("ticket" in idx.lower() for idx in indexes)


# ── _record_agent_run writes a row ───────────────────────────────────────────

def test_record_agent_run_inserts_completed(orchestrator, mem_db):
    now = datetime.now(timezone.utc).isoformat()
    orchestrator._record_agent_run(
        ticket_id=42,
        agent_name="classification_agent",
        flow="analysis",
        status="completed",
        input_summary="subject: test",
        output_summary="type: feature_request",
        output_json=json.dumps({"classification": "feature_request", "confidence": 0.9}),
        error="",
        started_at=now,
        finished_at=now,
        duration_ms=120,
        provider="anthropic",
        model="claude-haiku",
    )
    row = mem_db.execute(
        "SELECT * FROM agent_runs WHERE ticket_id=42 AND agent_name='classification_agent'"
    ).fetchone()
    assert row is not None
    assert row["status"] == "completed"
    assert row["flow"] == "analysis"
    assert row["duration_ms"] == 120


def test_record_agent_run_inserts_failed(orchestrator, mem_db):
    now = datetime.now(timezone.utc).isoformat()
    orchestrator._record_agent_run(
        ticket_id=99,
        agent_name="summary_agent",
        flow="analysis",
        status="failed",
        input_summary="subject: bad",
        output_summary="",
        output_json="",
        error="API timeout after 30s",
        started_at=now,
        finished_at=now,
        duration_ms=30000,
        provider="anthropic",
        model="claude-haiku",
    )
    row = mem_db.execute(
        "SELECT * FROM agent_runs WHERE ticket_id=99 AND status='failed'"
    ).fetchone()
    assert row is not None
    assert "timeout" in row["error"].lower()


def test_record_agent_run_inserts_skipped(orchestrator, mem_db):
    now = datetime.now(timezone.utc).isoformat()
    orchestrator._record_agent_run(
        ticket_id=7,
        agent_name="jira_agent",
        flow="analysis",
        status="skipped",
        input_summary="no jira configured",
        output_summary="",
        output_json="",
        error="",
        started_at=now,
        finished_at=now,
        duration_ms=0,
        provider="",
        model="",
    )
    row = mem_db.execute(
        "SELECT * FROM agent_runs WHERE ticket_id=7 AND status='skipped'"
    ).fetchone()
    assert row is not None


# ── get_agent_runs fetches correctly ─────────────────────────────────────────

def test_get_agent_runs_by_ticket(orchestrator, mem_db):
    now = datetime.now(timezone.utc).isoformat()
    for name in ("classification_agent", "summary_agent", "feasibility_agent"):
        orchestrator._record_agent_run(
            ticket_id=1, agent_name=name, flow="analysis",
            status="completed", input_summary="", output_summary="ok",
            output_json="{}", error="", started_at=now, finished_at=now,
            duration_ms=50, provider="anthropic", model="claude-haiku",
        )
    runs = orchestrator.get_agent_runs(ticket_id=1)
    assert len(runs) == 3
    assert all(r["ticket_id"] == 1 for r in runs)


def test_get_agent_runs_by_agent_name(orchestrator, mem_db):
    now = datetime.now(timezone.utc).isoformat()
    for tid in (10, 11, 12):
        orchestrator._record_agent_run(
            ticket_id=tid, agent_name="notification_agent", flow="notification",
            status="completed", input_summary="", output_summary="preview ok",
            output_json="{}", error="", started_at=now, finished_at=now,
            duration_ms=200, provider="anthropic", model="claude-haiku",
        )
    runs = orchestrator.get_agent_runs(agent_name="notification_agent")
    assert len(runs) == 3


def test_get_agent_runs_by_flow(orchestrator, mem_db):
    now = datetime.now(timezone.utc).isoformat()
    orchestrator._record_agent_run(
        ticket_id=5, agent_name="batch_agent", flow="batch",
        status="completed", input_summary="", output_summary="plan ok",
        output_json="{}", error="", started_at=now, finished_at=now,
        duration_ms=800, provider="anthropic", model="claude-haiku",
    )
    orchestrator._record_agent_run(
        ticket_id=6, agent_name="classification_agent", flow="analysis",
        status="completed", input_summary="", output_summary="classified",
        output_json="{}", error="", started_at=now, finished_at=now,
        duration_ms=80, provider="anthropic", model="claude-haiku",
    )
    batch_runs = orchestrator.get_agent_runs(flow="batch")
    assert len(batch_runs) == 1
    assert batch_runs[0]["agent_name"] == "batch_agent"


# ── output_json stored and retrievable ───────────────────────────────────────

def test_output_json_roundtrip(orchestrator, mem_db):
    now = datetime.now(timezone.utc).isoformat()
    payload = {"classification": "bug_report", "confidence": 0.95, "reason": "error message present"}
    orchestrator._record_agent_run(
        ticket_id=20, agent_name="classification_agent", flow="analysis",
        status="completed", input_summary="", output_summary="bug_report",
        output_json=json.dumps(payload), error="", started_at=now, finished_at=now,
        duration_ms=90, provider="anthropic", model="claude-haiku",
    )
    row = mem_db.execute(
        "SELECT output_json FROM agent_runs WHERE ticket_id=20"
    ).fetchone()
    assert row is not None
    parsed = json.loads(row["output_json"])
    assert parsed["classification"] == "bug_report"
    assert parsed["confidence"] == 0.95


# ── _record_agent_run never raises ───────────────────────────────────────────

def test_record_agent_run_does_not_raise_on_bad_db(orchestrator):
    """Even with a broken DB path, _record_agent_run must not bubble up."""
    bad_orch = AgentOrchestrator("dummy-key", db=None)
    # Should silently catch and not raise
    bad_orch._record_agent_run(
        ticket_id=1, agent_name="test_agent", flow="test",
        status="completed", input_summary="", output_summary="",
        output_json="{}", error="", started_at="", finished_at="",
        duration_ms=0, provider="", model="",
    )
