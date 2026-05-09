"""Source-level wiring tests for PR 29 — safe-to-send display in review flow.

Reads app.py and templates/ticket.html to assert correct imports,
wiring, and template constructs. No Flask or HTTP.
"""
from __future__ import annotations

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


APP_SRC = _read("app.py")
TEMPLATE_SRC = _read("templates/ticket.html")


# ── app.py: import ─────────────────────────────────────────────────────────────


def test_app_imports_build_safe_to_send_display():
    assert "build_safe_to_send_display" in APP_SRC


def test_app_imports_from_ai_safe_to_send_display():
    assert "from ai.safe_to_send_display import build_safe_to_send_display" in APP_SRC


# ── app.py: ticket_detail sets safe_to_send_display ───────────────────────────


def test_app_sets_safe_to_send_display():
    assert 'ticket_dict["safe_to_send_display"]' in APP_SRC


def test_app_safe_to_send_display_inside_ticket_detail():
    pos_func = APP_SRC.find("def ticket_detail(ticket_id):")
    pos_disp = APP_SRC.find('ticket_dict["safe_to_send_display"]')
    assert pos_func != -1
    assert pos_disp != -1
    assert pos_disp > pos_func


def test_app_safe_to_send_display_after_review():
    pos_review = APP_SRC.find('ticket_dict["safe_to_send_review"]')
    pos_disp   = APP_SRC.find('ticket_dict["safe_to_send_display"]')
    assert pos_review != -1 and pos_disp != -1
    assert pos_disp > pos_review


def test_app_safe_to_send_display_before_render_template():
    pos_disp   = APP_SRC.find('ticket_dict["safe_to_send_display"]')
    pos_render = APP_SRC.find('return render_template("ticket.html"')
    assert pos_disp != -1 and pos_render != -1
    assert pos_disp < pos_render


def test_app_display_passes_safe_to_send_review():
    assert 'build_safe_to_send_display(\n            ticket_dict.get("safe_to_send_review")\n        )' in APP_SRC \
        or 'build_safe_to_send_display(ticket_dict.get("safe_to_send_review"))' in APP_SRC \
        or 'build_safe_to_send_display(\n        ticket_dict.get("safe_to_send_review")' in APP_SRC


def test_app_display_fallback_has_data_false():
    assert '"has_data": False' in APP_SRC or "'has_data': False" in APP_SRC


def test_app_display_fallback_has_copy_warning():
    assert "copy_warning" in APP_SRC


# ── template: banner present ───────────────────────────────────────────────────


def test_template_contains_safe_to_send_draft_banner_comment():
    assert "SAFE TO SEND DRAFT BANNER" in TEMPLATE_SRC


def test_template_references_safe_to_send_display():
    assert "safe_to_send_display" in TEMPLATE_SRC


def test_template_renders_badge_label():
    assert "std.badge_label" in TEMPLATE_SRC


def test_template_renders_score():
    assert "std.score" in TEMPLATE_SRC


def test_template_renders_banner_title():
    assert "std.banner_title" in TEMPLATE_SRC


def test_template_renders_banner_message():
    assert "std.banner_message" in TEMPLATE_SRC


def test_template_renders_copy_warning():
    assert "std.copy_warning" in TEMPLATE_SRC


def test_template_renders_top_reasons():
    assert "std.top_reasons" in TEMPLATE_SRC


def test_template_renders_reason_title_in_banner():
    assert "reason.title" in TEMPLATE_SRC


# ── template: banner near draft area ─────────────────────────────────────────


def test_template_banner_before_ticket_form():
    banner_pos = TEMPLATE_SRC.find("SAFE TO SEND DRAFT BANNER")
    form_pos   = TEMPLATE_SRC.find('<form id="ticket-form"')
    assert banner_pos != -1
    assert form_pos != -1
    assert banner_pos < form_pos


def test_template_banner_after_regenerate_drafts():
    regen_pos  = TEMPLATE_SRC.find("Regenerate Drafts")
    banner_pos = TEMPLATE_SRC.find("SAFE TO SEND DRAFT BANNER")
    assert regen_pos != -1
    assert banner_pos != -1
    assert banner_pos > regen_pos


# ── template: data attributes for JS copy confirmation ───────────────────────


def test_template_banner_has_data_safe_to_send_status():
    assert "data-safe-to-send-status" in TEMPLATE_SRC


def test_template_banner_has_data_copy_warning():
    assert "data-copy-warning" in TEMPLATE_SRC


# ── template: copy confirmation JS ────────────────────────────────────────────


def test_template_copy_confirm_do_not_send_text():
    assert "do not send yet" in TEMPLATE_SRC.lower() or "Do not send yet" in TEMPLATE_SRC


def test_template_copy_confirm_needs_review_text():
    assert "review warnings" in TEMPLATE_SRC.lower()


def test_template_js_checks_sts_status():
    assert "data-safe-to-send-status" in TEMPLATE_SRC


def test_template_js_confirm_called():
    assert "confirm(" in TEMPLATE_SRC


# ── no blocking / no auto-send ────────────────────────────────────────────────


def test_template_copy_button_not_disabled():
    """The Copy clean draft button must not have a disabled attribute."""
    # Find the button
    btn_pos = TEMPLATE_SRC.find("copyCleanDraft")
    assert btn_pos != -1
    # Check surrounding 200 chars for disabled
    context = TEMPLATE_SRC[max(0, btn_pos - 200):btn_pos + 200]
    assert "disabled" not in context.lower()


def test_template_no_auto_send():
    # No hidden auto-submit, no form that auto-submits on page load
    assert "autosubmit" not in TEMPLATE_SRC.lower()
    assert "auto-send" not in TEMPLATE_SRC.lower()


def test_template_safe_to_send_card_still_present():
    """PR 28 card must remain unchanged."""
    assert "SAFE TO SEND REVIEW CARD" in TEMPLATE_SRC


# ── banner read-only: no form / input / save / edit ─────────────────────────


def test_template_draft_banner_has_no_form():
    start = TEMPLATE_SRC.find("SAFE TO SEND DRAFT BANNER")
    end   = TEMPLATE_SRC.find("END SAFE TO SEND DRAFT BANNER")
    assert start != -1 and end != -1
    section = TEMPLATE_SRC[start:end].lower()
    assert "<form" not in section


def test_template_draft_banner_has_no_input():
    start = TEMPLATE_SRC.find("SAFE TO SEND DRAFT BANNER")
    end   = TEMPLATE_SRC.find("END SAFE TO SEND DRAFT BANNER")
    section = TEMPLATE_SRC[start:end].lower()
    assert "<input" not in section
    assert "<textarea" not in section
    assert "<select" not in section


def test_template_draft_banner_has_no_save_or_edit():
    start = TEMPLATE_SRC.find("SAFE TO SEND DRAFT BANNER")
    end   = TEMPLATE_SRC.find("END SAFE TO SEND DRAFT BANNER")
    section = TEMPLATE_SRC[start:end].lower()
    assert "save" not in section
    assert "edit" not in section


def test_template_draft_banner_has_no_submit_button():
    start = TEMPLATE_SRC.find("SAFE TO SEND DRAFT BANNER")
    end   = TEMPLATE_SRC.find("END SAFE TO SEND DRAFT BANNER")
    section = TEMPLATE_SRC[start:end].lower()
    assert 'type="submit"' not in section
    assert "<button" not in section


# ── module importable ─────────────────────────────────────────────────────────


def test_build_safe_to_send_display_importable():
    from ai.safe_to_send_display import build_safe_to_send_display
    assert callable(build_safe_to_send_display)


def test_build_safe_to_send_display_returns_dict():
    from ai.safe_to_send_display import build_safe_to_send_display
    assert isinstance(build_safe_to_send_display(None), dict)


def test_build_safe_to_send_display_has_data_key():
    from ai.safe_to_send_display import build_safe_to_send_display
    assert "has_data" in build_safe_to_send_display(None)
