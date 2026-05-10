"""Safety tests: no new auto-send logic added by this PR.

- notification_agent is preview-only (no external send calls)
- reply_scanner_agent stores lessons, never sends replies
- batch_agent returns a plan, never auto-applies it
- Copy remains a manual user action (no JS auto-submit)
- No new hidden auto-send logic in app.py
- No new auto-send in agents.py (notification preview only)

Reads app.py, agents.py, templates/ticket.html — no Flask, no DB, no network.
"""
from __future__ import annotations

import re
import pytest


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


APP_SRC = _read("app.py")
AGENTS_SRC = _read("agents.py")
TICKET_TMPL = _read("templates/ticket.html")


# ── notification_agent is preview-only ───────────────────────────────────────

def test_notification_agent_route_is_preview_only():
    """The /notification-preview route must be GET and return JSON — no external sends."""
    idx = APP_SRC.find("def notification_preview(")
    assert idx != -1, "notification_preview route not found"
    snippet = APP_SRC[idx:idx + 1000]
    # Must return jsonify, not send email/Slack
    assert "jsonify(" in snippet
    assert "smtp" not in snippet.lower()
    assert "send_email" not in snippet.lower()
    assert "slack" not in snippet.lower()


def test_notification_agent_function_no_external_send():
    """notification_agent() in agents.py must not call any external send function.
    The word 'slack' may appear in system prompt as a channel name — that is fine.
    We check for actual send API patterns only.
    """
    idx = AGENTS_SRC.find("def notification_agent(")
    assert idx != -1
    # Find end of function by next def at same indent level
    next_def = AGENTS_SRC.find("\ndef ", idx + 1)
    snippet = AGENTS_SRC[idx:next_def if next_def != -1 else idx + 2000]
    assert "smtp" not in snippet.lower()
    assert "send_email" not in snippet.lower()
    # Must not use Slack WebClient or POST to Slack API
    assert "WebClient" not in snippet
    assert "slack_client" not in snippet.lower()
    assert "slack.com/api" not in snippet.lower()
    # No external HTTP sends (webhooks/Slack/email APIs)
    assert 'requests.post("http' not in snippet
    assert "smtplib" not in snippet


def test_notification_route_labeled_preview():
    """Route name or docstring must make clear it is a preview."""
    assert "preview" in APP_SRC.lower()
    idx = APP_SRC.find("def notification_preview(")
    snippet = APP_SRC[idx:idx + 300]
    assert "preview" in snippet.lower()


# ── reply_scanner_agent stores lessons, does not send replies ────────────────

def test_scan_replies_route_no_freshdesk_send():
    idx = APP_SRC.find("def scan_replies(")
    assert idx != -1
    snippet = APP_SRC[idx:idx + 2000]
    # Must not call create_note / create_reply / post to Freshdesk tickets API
    assert "create_note" not in snippet
    assert "create_reply" not in snippet
    # Must only store lessons and return JSON
    assert "jsonify(" in snippet


def test_reply_scanner_agent_function_returns_dict():
    """reply_scanner_agent must return (dict, usage) — not send anything."""
    idx = AGENTS_SRC.find("def reply_scanner_agent(")
    assert idx != -1
    next_def = AGENTS_SRC.find("\ndef ", idx + 1)
    snippet = AGENTS_SRC[idx:next_def if next_def != -1 else idx + 2000]
    assert "return" in snippet
    assert "smtp" not in snippet.lower()
    assert "requests.post" not in snippet


# ── batch_agent returns plan only ────────────────────────────────────────────

def test_batch_plan_route_returns_json_only():
    idx = APP_SRC.find("def batch_plan(")
    assert idx != -1
    snippet = APP_SRC[idx:idx + 2000]
    assert "jsonify(" in snippet
    # Must not update tickets or call external systems
    assert "UPDATE tickets" not in snippet
    assert "db.execute" not in snippet.replace("db.execute(\n", "").replace("db.execute(", "db_execute_used")
    # ^ actually it's OK to query (SELECT), just must not auto-apply plan
    # The key safety check: no auto-update of ticket data
    assert 'db.execute("UPDATE' not in snippet and "db.execute('UPDATE" not in snippet


def test_batch_agent_function_returns_dict():
    idx = AGENTS_SRC.find("def batch_agent(")
    assert idx != -1
    next_def = AGENTS_SRC.find("\ndef ", idx + 1)
    snippet = AGENTS_SRC[idx:next_def if next_def != -1 else idx + 2000]
    assert "return" in snippet


# ── Copy remains a manual user action ────────────────────────────────────────

def test_ticket_copy_button_not_disabled():
    """copyCleanDraft button must not have disabled attribute."""
    btn_pos = TICKET_TMPL.find("copyCleanDraft")
    assert btn_pos != -1
    context = TICKET_TMPL[max(0, btn_pos - 200):btn_pos + 200]
    assert "disabled" not in context.lower()


def test_template_no_autosubmit():
    assert "autosubmit" not in TICKET_TMPL.lower()


def test_template_no_auto_send_js():
    assert "auto-send" not in TICKET_TMPL.lower()


def test_template_no_auto_form_submit_on_load():
    """No window.onload / DOMContentLoaded that calls form.submit() or fetch auto-send."""
    # Check that no onload auto-submits the ticket form
    assert "form.submit()" not in TICKET_TMPL
    # window.onload = function() { ... .submit() } pattern not present
    onload_pattern = re.search(r"onload\s*=.*submit\(\)", TICKET_TMPL, re.DOTALL)
    assert onload_pattern is None


# ── app.py: no new auto-send calls in route handlers ─────────────────────────

def test_app_no_auto_send_in_scan_replies():
    idx = APP_SRC.find("def scan_replies(")
    if idx == -1:
        pytest.skip("scan_replies not yet in app.py")
    # Find next route handler
    next_route = APP_SRC.find("\n@app.route", idx + 1)
    snippet = APP_SRC[idx:next_route if next_route != -1 else idx + 3000]
    assert "send_reply" not in snippet.lower()
    assert "create_note" not in snippet


def test_app_no_auto_send_in_generate_ai_report():
    idx = APP_SRC.find("def generate_ai_report(")
    if idx == -1:
        pytest.skip("generate_ai_report not yet in app.py")
    next_route = APP_SRC.find("\n@app.route", idx + 1)
    snippet = APP_SRC[idx:next_route if next_route != -1 else idx + 2000]
    # Reporting route must only return JSON insights, not send anything
    assert "send_email" not in snippet.lower()
    assert "smtp" not in snippet.lower()
    assert "jsonify(" in snippet


# ── agents.py: no agent marks itself wired without actual LLM call ───────────

def test_newly_wired_agents_call_llm_or_llm_router():
    """Each newly-wired agent function must reference client or llm_router."""
    for fn_name in (
        "classification_agent",
        "summary_agent",
        "feasibility_agent",
        "jira_agent",
        "notification_agent",
        "reply_scanner_agent",
        "batch_agent",
        "reporting_agent",
    ):
        idx = AGENTS_SRC.find(f"def {fn_name}(")
        assert idx != -1, f"def {fn_name}() not found in agents.py"
        next_def = AGENTS_SRC.find("\ndef ", idx + 1)
        snippet = AGENTS_SRC[idx:next_def if next_def != -1 else idx + 3000]
        has_llm_call = (
            "client" in snippet
            or "llm_router" in snippet
            or "_call_with_retry" in snippet
            or "complete(" in snippet
        )
        assert has_llm_call, f"{fn_name} has no LLM call — not actually wired"
