"""Source-level wiring tests: Agent Run Status UI in ticket.html and agents.html.

Reads templates only — no Flask, no DB, no network.
"""
from __future__ import annotations

import pytest


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


TICKET_TMPL = _read("templates/ticket.html")
AGENTS_TMPL = _read("templates/agents.html")


# ══════════════════════════════════════════════════════════════════════════════
# ticket.html — Agent Run Status Card
# ══════════════════════════════════════════════════════════════════════════════

def test_ticket_has_agent_run_status_card_comment():
    assert "AGENT RUN STATUS CARD" in TICKET_TMPL


def test_ticket_has_end_agent_run_status_card_comment():
    assert "END AGENT RUN STATUS CARD" in TICKET_TMPL


def test_ticket_agent_runs_iterated():
    assert "ticket.agent_runs" in TICKET_TMPL


def test_ticket_agent_run_status_table_exists():
    start = TICKET_TMPL.find("AGENT RUN STATUS CARD")
    end = TICKET_TMPL.find("END AGENT RUN STATUS CARD")
    assert start != -1 and end != -1
    section = TICKET_TMPL[start:end]
    assert "<table" in section


def test_ticket_agent_run_status_shows_completed_badge():
    start = TICKET_TMPL.find("AGENT RUN STATUS CARD")
    end = TICKET_TMPL.find("END AGENT RUN STATUS CARD")
    section = TICKET_TMPL[start:end]
    assert "completed" in section.lower()


def test_ticket_agent_run_status_shows_failed_badge():
    start = TICKET_TMPL.find("AGENT RUN STATUS CARD")
    end = TICKET_TMPL.find("END AGENT RUN STATUS CARD")
    section = TICKET_TMPL[start:end]
    assert "failed" in section.lower()


def test_ticket_agent_run_status_shows_duration():
    start = TICKET_TMPL.find("AGENT RUN STATUS CARD")
    end = TICKET_TMPL.find("END AGENT RUN STATUS CARD")
    section = TICKET_TMPL[start:end]
    assert "duration_ms" in section or "duration" in section.lower()


def test_ticket_agent_run_status_shows_started_at():
    start = TICKET_TMPL.find("AGENT RUN STATUS CARD")
    end = TICKET_TMPL.find("END AGENT RUN STATUS CARD")
    section = TICKET_TMPL[start:end]
    assert "started_at" in section


def test_ticket_agent_run_status_empty_state_message():
    """Must have a fallback message when no runs recorded."""
    start = TICKET_TMPL.find("AGENT RUN STATUS CARD")
    end = TICKET_TMPL.find("END AGENT RUN STATUS CARD")
    section = TICKET_TMPL[start:end]
    assert "no agent runs" in section.lower() or "no runs" in section.lower()


# ── Banner is before the ticket-form ─────────────────────────────────────────

def test_agent_run_status_before_ticket_form():
    status_pos = TICKET_TMPL.find("AGENT RUN STATUS CARD")
    form_pos = TICKET_TMPL.find('<form id="ticket-form"')
    assert status_pos != -1 and form_pos != -1
    assert status_pos < form_pos


# ── Agent Run Status card is read-only (no form/input in section) ─────────────

def test_agent_run_status_card_no_form():
    start = TICKET_TMPL.find("AGENT RUN STATUS CARD")
    end = TICKET_TMPL.find("END AGENT RUN STATUS CARD")
    section = TICKET_TMPL[start:end].lower()
    assert "<form" not in section


def test_agent_run_status_card_no_input():
    start = TICKET_TMPL.find("AGENT RUN STATUS CARD")
    end = TICKET_TMPL.find("END AGENT RUN STATUS CARD")
    section = TICKET_TMPL[start:end].lower()
    assert "<input" not in section


# ══════════════════════════════════════════════════════════════════════════════
# ticket.html — Agent Briefs Card
# ══════════════════════════════════════════════════════════════════════════════

def test_ticket_has_agent_briefs_card_comment():
    assert "AGENT BRIEFS CARD" in TICKET_TMPL


def test_ticket_agent_briefs_is_collapsible():
    start = TICKET_TMPL.find("AGENT BRIEFS CARD")
    end = TICKET_TMPL.find("END AGENT BRIEFS CARD")
    assert start != -1 and end != -1
    section = TICKET_TMPL[start:end]
    assert "<details" in section


def test_ticket_agent_briefs_references_ticket_agent_briefs():
    assert "ticket.agent_briefs" in TICKET_TMPL


def test_ticket_agent_briefs_iterates_items():
    start = TICKET_TMPL.find("AGENT BRIEFS CARD")
    end = TICKET_TMPL.find("END AGENT BRIEFS CARD")
    section = TICKET_TMPL[start:end]
    assert "agent_briefs.items()" in section or "agent_briefs" in section


def test_ticket_agent_briefs_empty_state_message():
    start = TICKET_TMPL.find("AGENT BRIEFS CARD")
    end = TICKET_TMPL.find("END AGENT BRIEFS CARD")
    section = TICKET_TMPL[start:end].lower()
    assert "no agent briefs" in section or "no briefs" in section


# ── Agent Briefs is read-only ─────────────────────────────────────────────────

def test_agent_briefs_card_no_submit_button():
    start = TICKET_TMPL.find("AGENT BRIEFS CARD")
    end = TICKET_TMPL.find("END AGENT BRIEFS CARD")
    section = TICKET_TMPL[start:end].lower()
    assert 'type="submit"' not in section
    assert "<button" not in section


# ══════════════════════════════════════════════════════════════════════════════
# agents.html — Runtime Agent Map
# ══════════════════════════════════════════════════════════════════════════════

def test_agents_html_has_runtime_agent_map():
    assert "Runtime Agent Map" in AGENTS_TMPL


def test_agents_html_no_hardcoded_pipeline_architecture():
    """The old static 'Pipeline Architecture' section heading must be replaced."""
    # The card title must be Runtime Agent Map, not Pipeline Architecture
    # (A comment or heading named Pipeline Architecture is not acceptable)
    assert "Pipeline Architecture" not in AGENTS_TMPL


def test_agents_html_runtime_map_references_agent_runtime_map():
    assert "agent_runtime_map" in AGENTS_TMPL


def test_agents_html_runtime_map_has_table():
    idx = AGENTS_TMPL.find("Runtime Agent Map")
    assert idx != -1
    nearby = AGENTS_TMPL[idx:idx + 2000]
    assert "<table" in nearby


def test_agents_html_runtime_map_shows_wired_active_badge():
    assert "wired" in AGENTS_TMPL.lower() and "active" in AGENTS_TMPL.lower()


def test_agents_html_runtime_map_shows_wired_now_badge():
    assert "wired" in AGENTS_TMPL.lower() and "new" in AGENTS_TMPL.lower()


def test_agents_html_runtime_map_shows_completed_runs():
    assert "completed_runs" in AGENTS_TMPL


def test_agents_html_runtime_map_has_fallback_section():
    """Must degrade gracefully when agent_runtime_map is empty."""
    assert "{% else %}" in AGENTS_TMPL or "fallback" in AGENTS_TMPL.lower()


def test_agents_html_last_run_column():
    idx = AGENTS_TMPL.find("Runtime Agent Map")
    nearby = AGENTS_TMPL[idx:idx + 5000]
    assert "last_run" in nearby


def test_agents_html_no_auto_send_language():
    idx = AGENTS_TMPL.find("Runtime Agent Map")
    nearby = AGENTS_TMPL[idx:idx + 3000]
    # If "auto-send" appears it must be in a "no auto-send" context
    if "auto-send" in nearby.lower():
        assert "no agent auto-sends" in nearby.lower() or "no auto-send" in nearby.lower()
