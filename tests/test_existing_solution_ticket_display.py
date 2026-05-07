"""Tests for existing solution review wiring in app.py and ticket.html.

Source-level checks — no Flask test client, no live DB required.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ── app.py wiring checks ──────────────────────────────────────────────────────

def test_app_imports_extract_existing_solution_from_pm_decision():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    source = app_path.read_text()
    assert "extract_existing_solution_from_pm_decision" in source, (
        "app.py must import/use extract_existing_solution_from_pm_decision"
    )


def test_app_sets_existing_solution_review_on_ticket_dict():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    source = app_path.read_text()
    assert 'existing_solution_review' in source, (
        'app.py must set ticket_dict["existing_solution_review"]'
    )


def test_app_uses_existing_solution_display_module():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    source = app_path.read_text()
    assert "existing_solution_display" in source, (
        "app.py must import from ai.existing_solution_display"
    )


def test_app_has_fallback_for_existing_solution_review():
    """If the helper fails, app.py must still provide a fallback dict."""
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    source = app_path.read_text()
    # The except clause must set has_data=False
    assert '"has_data": False' in source or "'has_data': False" in source, (
        "app.py must fall back to has_data=False on exception"
    )


# ── template source checks ────────────────────────────────────────────────────

def _template_source() -> str:
    template_path = Path(__file__).resolve().parents[1] / "templates" / "ticket.html"
    return template_path.read_text()


def test_template_contains_existing_solution_review_heading():
    assert "Existing Solution Review" in _template_source(), (
        "ticket.html must contain 'Existing Solution Review' heading"
    )


def test_template_contains_no_data_message():
    assert "No existing solution review available yet." in _template_source(), (
        "ticket.html must contain the no-data message"
    )


def test_template_contains_make_editable_note():
    assert "This suggests a configurable/editable approach" in _template_source(), (
        "ticket.html must contain the make_editable configurable note"
    )


def test_template_references_existing_solution_review():
    assert "existing_solution_review" in _template_source(), (
        "ticket.html must reference ticket.existing_solution_review"
    )


def test_template_renders_badge_label():
    assert "badge_label" in _template_source(), (
        "ticket.html must render esr.badge_label"
    )


def test_template_renders_recommended_action():
    assert "recommended_action" in _template_source(), (
        "ticket.html must render esr.recommended_action"
    )


def test_template_renders_confidence():
    assert "confidence" in _template_source(), (
        "ticket.html must render esr.confidence"
    )


def test_template_renders_reason():
    assert "esr.reason" in _template_source(), (
        "ticket.html must render esr.reason"
    )


def test_template_renders_sources():
    assert "esr.sources" in _template_source(), (
        "ticket.html must iterate esr.sources"
    )


def test_template_renders_signals():
    assert "esr.signals" in _template_source(), (
        "ticket.html must iterate esr.signals"
    )


def test_template_has_no_editing_controls_in_esr_card():
    """The ESR card must be read-only — no form or save button inside it."""
    source = _template_source()
    # Find the ESR card section
    start = source.find("EXISTING SOLUTION REVIEW CARD")
    end = source.find("RICE PRIORITIZATION SECTION", start)
    assert start != -1, "ESR card comment not found"
    assert end != -1, "RICE card comment not found"
    card_section = source[start:end]
    assert "<form" not in card_section, (
        "ESR card must not contain a <form> element (read-only)"
    )
    assert 'type="submit"' not in card_section, (
        "ESR card must not contain a submit button (read-only)"
    )


def test_template_has_read_only_subtitle():
    source = _template_source()
    # The card heading must include a read-only marker
    assert "read-only" in source[source.find("Existing Solution Review"):
                                  source.find("Existing Solution Review") + 200], (
        "ESR card heading must be marked read-only"
    )


# ── Helper module checks ──────────────────────────────────────────────────────

def test_helper_module_exists():
    helper_path = Path(__file__).resolve().parents[1] / "ai" / "existing_solution_display.py"
    assert helper_path.exists(), "ai/existing_solution_display.py must exist"


def test_helper_is_importable():
    from ai.existing_solution_display import extract_existing_solution_from_pm_decision
    assert callable(extract_existing_solution_from_pm_decision)


def test_helper_returns_has_data_false_for_empty_input():
    from ai.existing_solution_display import extract_existing_solution_from_pm_decision
    result = extract_existing_solution_from_pm_decision({})
    assert result["has_data"] is False


# ── Acceptance scenario ───────────────────────────────────────────────────────

def test_acceptance_template_and_wiring():
    """Confirm all wiring and template elements required by PR 17 acceptance."""
    source = _template_source()
    app_source = (Path(__file__).resolve().parents[1] / "app.py").read_text()

    assert "extract_existing_solution_from_pm_decision" in app_source
    assert 'existing_solution_review' in app_source
    assert "Existing Solution Review" in source
    assert "No existing solution review available yet." in source
    assert "This suggests a configurable/editable approach" in source
    assert "esr.sources" in source
    assert "esr.signals" in source
