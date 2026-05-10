"""Source-level UX tests for the PM/PO workspace redesign.

Reads templates/ticket.html only — no Flask, no DB, no network.
"""
from __future__ import annotations
import pytest


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


TICKET = _read("templates/ticket.html")


# ── Sticky decision bar ───────────────────────────────────────────────────────

def test_has_sticky_bar_comment():
    assert "WORKSPACE STICKY BAR" in TICKET


def test_sticky_bar_has_ws_bar_class():
    assert 'class="ws-bar"' in TICKET or "ws-bar" in TICKET


def test_sticky_bar_shows_ticket_number():
    idx = TICKET.find("WORKSPACE STICKY BAR")
    snippet = TICKET[idx:idx + 800]
    assert "ticket_id" in snippet or "ticket.ticket_id" in snippet


def test_sticky_bar_has_freshdesk_link():
    idx = TICKET.find("WORKSPACE STICKY BAR")
    snippet = TICKET[idx:idx + 1200]
    assert "freshdesk" in snippet.lower() or "Open in Freshdesk" in snippet


def test_sticky_bar_shows_classification():
    idx = TICKET.find("WORKSPACE STICKY BAR")
    snippet = TICKET[idx:idx + 800]
    assert "classification" in snippet.lower()


def test_sticky_bar_shows_sts_status():
    idx = TICKET.find("WORKSPACE STICKY BAR")
    snippet = TICKET[idx:idx + 800]
    assert "safe_to_send" in snippet.lower() or "STS" in snippet


# ── Workflow stepper ─────────────────────────────────────────────────────────

def test_has_workspace_stepper_comment():
    assert "WORKSPACE STEPPER" in TICKET


def test_stepper_has_4_steps():
    assert "Understand" in TICKET
    assert "Decide" in TICKET
    assert "Review" in TICKET
    assert "Act" in TICKET


def test_stepper_step_circle_class():
    assert "ws-step-circle" in TICKET


def test_stepper_done_class():
    assert "ws-step--done" in TICKET


def test_stepper_current_class():
    assert "ws-step--current" in TICKET


def test_stepper_pending_class():
    assert "ws-step--pending" in TICKET


def test_stepper_computes_step_state_from_analysis():
    assert "_step1_done" in TICKET or "step1_done" in TICKET


# ── Two-column workspace grid ─────────────────────────────────────────────────

def test_has_ws_grid():
    assert "ws-grid" in TICKET


def test_has_ws_col_left():
    assert "ws-col--left" in TICKET


def test_has_ws_col_right():
    assert "ws-col--right" in TICKET


def test_ws_grid_is_closed():
    """ws-grid div must be properly closed."""
    assert "/ws-grid" in TICKET


def test_ws_col_left_is_closed():
    assert "/ws-col--left" in TICKET


def test_ws_col_right_is_closed():
    assert "/ws-col--right" in TICKET


def test_ws_grid_css_two_columns():
    """CSS must define the two-column grid layout."""
    assert "grid-template-columns" in TICKET
    assert "1.25fr" in TICKET or "1fr 1fr" in TICKET


def test_ws_grid_mobile_responsive():
    assert "max-width" in TICKET and "grid-template-columns: 1fr" in TICKET


# ── What Support Should Send panel ────────────────────────────────────────────

def test_has_what_support_should_send_comment():
    assert "WHAT SUPPORT SHOULD SEND" in TICKET


def test_what_to_send_panel_id():
    assert 'id="what-to-send-panel"' in TICKET


def test_what_to_send_has_no_auto_send_notice():
    idx = TICKET.find("WHAT SUPPORT SHOULD SEND")
    snippet = TICKET[idx:idx + 2000]
    assert "No reply is sent automatically" in snippet


def test_what_to_send_shows_draft_preview():
    idx = TICKET.find("WHAT SUPPORT SHOULD SEND")
    snippet = TICKET[idx:idx + 2000]
    assert "draft_response" in snippet


def test_what_to_send_empty_state():
    idx = TICKET.find("WHAT SUPPORT SHOULD SEND")
    snippet = TICKET[idx:idx + 3500]
    assert "No draft generated yet" in snippet


def test_what_to_send_has_what_to_send_class():
    assert 'class="card what-to-send"' in TICKET


def test_what_to_send_in_right_column():
    right_pos = TICKET.find("ws-col--right")
    panel_pos = TICKET.find("what-to-send-panel")
    assert right_pos != -1 and panel_pos != -1
    assert panel_pos > right_pos


# ── PO Decision and Draft forms intact ───────────────────────────────────────

def test_po_decision_panel_id_intact():
    assert 'id="po-decision-panel"' in TICKET


def test_ticket_form_id_intact():
    assert 'id="ticket-form"' in TICKET


def test_rich_editors_intact():
    assert 'id="richtext-fr"' in TICKET
    assert 'id="richtext-en"' in TICKET


def test_textarea_fr_intact():
    assert 'id="textarea-fr"' in TICKET


def test_ai_progress_overlay_intact():
    assert 'id="ai-progress-overlay"' in TICKET


# ── AI Chat section ───────────────────────────────────────────────────────────

def test_ai_chat_exists():
    assert "Ask about this ticket" in TICKET


def test_ai_chat_messages_id():
    assert 'id="ai-chat-messages"' in TICKET


def test_ai_chat_has_6_chips():
    count = TICKET.count("setAIChatPrompt(")
    assert count >= 6, f"Expected ≥6 prompt chips, found {count}"


def test_ai_chat_chip_what_should_bso_do():
    assert "BSO" in TICKET


def test_ai_chat_chip_what_should_support_tell_client():
    assert "What should Support tell the client?" in TICKET or "What should Support" in TICKET


def test_ai_chat_helper_text():
    assert "agent briefs" in TICKET.lower() or "PM decision" in TICKET


# ── Diagnostics collapsed ─────────────────────────────────────────────────────

def test_evidence_diagnostics_is_details():
    assert "<details" in TICKET
    assert "Evidence" in TICKET and "Diagnostics" in TICKET


def test_diagnostics_section_has_summary():
    assert "<summary" in TICKET


def test_safe_to_send_review_card_still_present():
    assert "SAFE TO SEND REVIEW CARD" in TICKET


def test_agent_run_status_card_still_present():
    assert "AGENT RUN STATUS CARD" in TICKET


def test_agent_briefs_card_still_present():
    assert "AGENT BRIEFS CARD" in TICKET


# ── No auto-send ──────────────────────────────────────────────────────────────

def test_no_autosubmit():
    assert "autosubmit" not in TICKET.lower()


def test_no_auto_send():
    assert "auto-send" not in TICKET.lower()


def test_copy_button_not_disabled():
    btn_pos = TICKET.find("copyCleanDraft")
    assert btn_pos != -1
    context = TICKET[max(0, btn_pos - 200):btn_pos + 200]
    assert "disabled" not in context.lower()
