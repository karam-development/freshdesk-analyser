"""Tests for agents.html visibility: Purpose, Used In, and no-auto-send note.

Source-level only — reads templates/agents.html as a string.
No Flask, no DB, no network.
"""
from __future__ import annotations

from pathlib import Path

AGENTS_HTML = Path("templates/agents.html").read_text(encoding="utf-8")
APP_SRC = Path("app.py").read_text(encoding="utf-8")


# ── Template columns ──────────────────────────────────────────────────────────


def test_agents_html_has_purpose_column():
    assert "Purpose" in AGENTS_HTML


def test_agents_html_has_used_in_column():
    assert "Used In" in AGENTS_HTML


def test_agents_html_renders_agent_catalog_rows():
    """agent_catalog_rows variable must be used in the template."""
    assert "agent_catalog_rows" in AGENTS_HTML


def test_agents_html_shows_cfg_purpose():
    assert "cfg.purpose" in AGENTS_HTML


def test_agents_html_shows_cfg_used_in():
    assert "cfg.used_in" in AGENTS_HTML


# ── No auto-send note ─────────────────────────────────────────────────────────


def test_agents_html_has_no_auto_send_note():
    lower = AGENTS_HTML.lower()
    assert "auto-send" in lower or "does not auto-send" in lower or "no auto" in lower


def test_agents_html_mentions_human_review():
    lower = AGENTS_HTML.lower()
    assert "human review" in lower or "manual" in lower


# ── app.py wiring ─────────────────────────────────────────────────────────────


def test_app_imports_build_agent_catalog_rows():
    assert "build_agent_catalog_rows" in APP_SRC


def test_app_passes_agent_catalog_rows_to_template():
    assert "agent_catalog_rows=agent_catalog_rows" in APP_SRC


def test_app_wraps_catalog_build_in_try_except():
    idx = APP_SRC.find("build_agent_catalog_rows(")
    surrounding = APP_SRC[max(0, idx - 100):idx + 300]
    assert "try:" in surrounding or "except" in surrounding
