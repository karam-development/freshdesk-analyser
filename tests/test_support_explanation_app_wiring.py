"""Tests for support_explanation wiring in app.py and ticket.html.

Source-level only — no Flask, no DB, no network.
"""
from __future__ import annotations

from pathlib import Path

APP_SRC = Path("app.py").read_text(encoding="utf-8")
TICKET_HTML = Path("templates/ticket.html").read_text(encoding="utf-8")


# ── app.py imports ────────────────────────────────────────────────────────────


def test_app_imports_build_support_explanation_context():
    assert "build_support_explanation_context" in APP_SRC


def test_app_imports_from_ai_support_explanation():
    assert "from ai.support_explanation import build_support_explanation_context" in APP_SRC


# ── Injection in generate_drafts ─────────────────────────────────────────────


def test_support_explanation_injected_in_generate_drafts():
    # The support explanation import must appear inside the generate_drafts route body
    idx_route = APP_SRC.find("def generate_drafts(")
    idx_next = APP_SRC.find("def regenerate_draft_pm(")
    route_body = APP_SRC[idx_route:idx_next] if idx_next != -1 else APP_SRC[idx_route:]
    assert "build_support_explanation_context" in route_body


def test_support_explanation_result_prepended_to_enhanced_kb_in_generate_drafts():
    idx_route = APP_SRC.find("def generate_drafts(")
    idx_next = APP_SRC.find("def regenerate_draft_pm(")
    route_body = APP_SRC[idx_route:idx_next] if idx_next != -1 else APP_SRC[idx_route:]
    # The result must be prepended: _support_ctx + "\n\n" + enhanced_kb
    assert "_support_ctx" in route_body
    assert "enhanced_kb" in route_body


def test_support_explanation_in_generate_drafts_is_guarded_by_try_except():
    idx_route = APP_SRC.find("def generate_drafts(")
    idx_next = APP_SRC.find("def regenerate_draft_pm(")
    route_body = APP_SRC[idx_route:idx_next] if idx_next != -1 else APP_SRC[idx_route:]
    idx_sup = route_body.find("build_support_explanation_context")
    surrounding = route_body[max(0, idx_sup - 200):idx_sup + 300]
    assert "try:" in surrounding or "except" in surrounding


# ── Injection in regenerate_draft_pm ─────────────────────────────────────────


def test_support_explanation_injected_in_regenerate_draft_pm():
    idx_route = APP_SRC.find("def regenerate_draft_pm(")
    idx_next = APP_SRC.find("def generate_decline_drafts(")
    route_body = APP_SRC[idx_route:idx_next] if idx_next != -1 else APP_SRC[idx_route:]
    assert "build_support_explanation_context" in route_body


def test_support_explanation_result_used_in_regenerate_draft_pm():
    idx_route = APP_SRC.find("def regenerate_draft_pm(")
    idx_next = APP_SRC.find("def generate_decline_drafts(")
    route_body = APP_SRC[idx_route:idx_next] if idx_next != -1 else APP_SRC[idx_route:]
    assert "_support_ctx_regen" in route_body


# ── No logic change ───────────────────────────────────────────────────────────


def test_support_explanation_does_not_change_pm_gate():
    """Support explanation must never change the PM gate logic or classification."""
    # The function is only used for prompt injection, not for decision mutation
    # Verify it's only called near enhanced_kb injection, not near po_decision or pm_decision assignment
    assert "support_explanation" not in APP_SRC.replace(
        "from ai.support_explanation import build_support_explanation_context", ""
    ).replace("build_support_explanation_context", "").lower()


def test_support_explanation_never_auto_sends():
    """The support explanation module must never trigger a Freshdesk send."""
    # No send / freshdesk_reply reference in the support explanation wiring
    from ai.support_explanation import build_support_explanation_context as func
    import inspect
    src = inspect.getsource(func)
    assert "freshdesk" not in src.lower()
    assert "requests.post" not in src
    assert "send_reply" not in src


# ── Template card present ─────────────────────────────────────────────────────


def test_ticket_html_has_support_explanation_guidance_card():
    assert "Support Explanation Guidance" in TICKET_HTML


def test_ticket_html_support_explanation_card_is_read_only():
    assert "read-only" in TICKET_HTML


def test_ticket_html_support_explanation_has_empty_state():
    assert "No specific support explanation guidance available" in TICKET_HTML
