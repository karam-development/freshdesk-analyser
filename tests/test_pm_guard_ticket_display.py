"""Tests for PM guard warning visibility in ticket detail.

These are helper/source-level tests that do not require a running Flask app
or a live database.  They verify:
  - the extraction + categorization pipeline end-to-end
  - deduplication of repeated markers
  - template source contains required PM Guard Review elements
  - app.py wiring
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.pm_decision_formatter import extract_pm_guard_warnings, strip_pm_guard_warnings
from ai.pm_guard_review import categorize_pm_guard_warnings


# ── Pipeline: extract → categorize ───────────────────────────────────────────

def _build_pm_guard_warnings(draft: str, draft_en: str = "", qa_issues: str = "") -> list:
    """Inline replica of the ticket_detail helper logic for isolated testing."""
    seen: set = set()
    raw: list = []
    for text in (draft, draft_en, qa_issues):
        for w in extract_pm_guard_warnings(text or ""):
            if w not in seen:
                seen.add(w)
                raw.append(w)
    return categorize_pm_guard_warnings(raw)


def test_helper_returns_pm_guard_warnings_list_when_draft_contains_marker():
    draft = (
        "The template has been updated.\n\n"
        "[PM guard: legal reference detected although PM decision says should_mention_law=false.]"
    )
    warnings = _build_pm_guard_warnings(draft)
    assert len(warnings) == 1
    assert warnings[0]["code"] == "legal_reference_blocked"


def test_helper_returns_empty_list_for_clean_draft():
    assert _build_pm_guard_warnings("A clean response with no issues.") == []


def test_helper_returns_empty_for_empty_fields():
    assert _build_pm_guard_warnings("", "", "") == []


def test_helper_returns_empty_for_none_fields():
    assert _build_pm_guard_warnings(None, None, None) == []


# ── Deduplication ────────────────────────────────────────────────────────────

def test_duplicate_guard_markers_across_fields_are_deduplicated():
    """The same marker in both draft_response and draft_response_en must appear once."""
    marker = "[PM guard: global default change suggested although global_change_risk=high.]"
    warnings = _build_pm_guard_warnings(
        draft=f"Response FR.\n\n{marker}",
        draft_en=f"Response EN.\n\n{marker}",
    )
    assert len(warnings) == 1
    assert warnings[0]["code"] == "global_default_change_blocked"


def test_duplicate_markers_in_same_field_are_deduplicated():
    """Two identical markers in the same draft → deduplicated to one."""
    marker = "[PM guard: legal reference detected although PM decision says should_mention_law=false.]"
    draft = f"Text.\n\n{marker}\n{marker}"
    warnings = _build_pm_guard_warnings(draft)
    assert len(warnings) == 1


def test_different_markers_in_multiple_fields_are_all_captured():
    legal = "[PM guard: legal reference detected although PM decision says should_mention_law=false.]"
    global_w = "[PM guard: global default change suggested although global_change_risk=high.]"
    warnings = _build_pm_guard_warnings(
        draft=f"FR draft.\n\n{legal}",
        draft_en=f"EN draft.\n\n{global_w}",
    )
    assert len(warnings) == 2
    codes = {w["code"] for w in warnings}
    assert "legal_reference_blocked" in codes
    assert "global_default_change_blocked" in codes


# ── Template source checks ────────────────────────────────────────────────────

def test_template_contains_pm_guard_review_title():
    template_path = Path(__file__).resolve().parents[1] / "templates" / "ticket.html"
    source = template_path.read_text()
    assert "PM Guard Review" in source, "ticket.html must contain 'PM Guard Review' heading"


def test_template_contains_no_warnings_message():
    template_path = Path(__file__).resolve().parents[1] / "templates" / "ticket.html"
    source = template_path.read_text()
    assert "No PM guard warnings detected" in source


def test_template_renders_severity_badge():
    template_path = Path(__file__).resolve().parents[1] / "templates" / "ticket.html"
    source = template_path.read_text()
    assert "w.severity" in source, "Template must render severity from warning dict"


def test_template_renders_title():
    template_path = Path(__file__).resolve().parents[1] / "templates" / "ticket.html"
    source = template_path.read_text()
    assert "w.title" in source, "Template must render title from warning dict"


def test_template_renders_message():
    template_path = Path(__file__).resolve().parents[1] / "templates" / "ticket.html"
    source = template_path.read_text()
    assert "w.message" in source, "Template must render message from warning dict"


def test_template_iterates_pm_guard_warnings():
    template_path = Path(__file__).resolve().parents[1] / "templates" / "ticket.html"
    source = template_path.read_text()
    assert "pm_guard_warnings" in source, "Template must reference pm_guard_warnings"


# ── app.py wiring checks ──────────────────────────────────────────────────────

def test_app_uses_collect_pm_guard_warnings_from_texts():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    source = app_path.read_text()
    assert "collect_pm_guard_warnings_from_texts" in source, \
        "app.py must use collect_pm_guard_warnings_from_texts in ticket_detail"


def test_extract_and_categorize_available_via_helper():
    """extract_pm_guard_warnings and categorize_pm_guard_warnings are
    used inside collect_pm_guard_warnings_from_texts; verify they exist there."""
    from ai.pm_guard_review import collect_pm_guard_warnings_from_texts
    import inspect
    src = inspect.getsource(collect_pm_guard_warnings_from_texts)
    assert "extract_pm_guard_warnings" in src
    assert "categorize_pm_guard_warnings" in src


def test_app_sets_pm_guard_warnings_on_ticket_dict():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    source = app_path.read_text()
    assert 'ticket_dict["pm_guard_warnings"]' in source, \
        'app.py must assign ticket_dict["pm_guard_warnings"]'


# ── Acceptance scenario ────────────────────────────────────────────────────────

def test_acceptance_three_markers_full_pipeline():
    """Three different markers → extracted, deduplicated, and categorized correctly."""
    draft = (
        "Please note that Article 12 applies here.\n"
        "We recommend changing the default globally.\n\n"
        "[PM guard: legal reference detected although PM decision says should_mention_law=false.]\n"
        "[PM guard: global default change suggested although global_change_risk=high.]\n"
        "[PM guard: recommended_action=make_editable but output does not mention editability/configurability.]"
    )

    warnings = _build_pm_guard_warnings(draft)

    assert len(warnings) == 3, f"Expected 3 warnings, got {len(warnings)}"

    codes = [w["code"] for w in warnings]
    assert "legal_reference_blocked" in codes
    assert "global_default_change_blocked" in codes
    assert "editability_missing" in codes

    severities = {w["code"]: w["severity"] for w in warnings}
    assert severities["legal_reference_blocked"] == "high"
    assert severities["global_default_change_blocked"] == "high"
    assert severities["editability_missing"] == "medium"

    # raw markers preserved
    raws = {w["raw"] for w in warnings}
    assert "[PM guard: legal reference detected although PM decision says should_mention_law=false.]" in raws
    assert "[PM guard: global default change suggested although global_change_risk=high.]" in raws


# ── PR 12: clean draft display checks ────────────────────────────────────────

def test_app_sets_draft_response_clean():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    source = app_path.read_text()
    assert 'draft_response_clean' in source, \
        'app.py must set ticket_dict["draft_response_clean"]'


def test_app_sets_draft_response_en_clean():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    source = app_path.read_text()
    assert 'draft_response_en_clean' in source, \
        'app.py must set ticket_dict["draft_response_en_clean"]'


def test_app_uses_get_clean_draft_for_display():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    source = app_path.read_text()
    assert 'get_clean_draft_for_display' in source, \
        'app.py must use get_clean_draft_for_display'


def test_template_references_draft_response_clean():
    template_path = Path(__file__).resolve().parents[1] / "templates" / "ticket.html"
    source = template_path.read_text()
    assert "draft_response_clean" in source, \
        "ticket.html must reference draft_response_clean"


def test_template_references_draft_response_en_clean():
    template_path = Path(__file__).resolve().parents[1] / "templates" / "ticket.html"
    source = template_path.read_text()
    assert "draft_response_en_clean" in source, \
        "ticket.html must reference draft_response_en_clean"


def test_template_contains_copy_clean_draft_button():
    template_path = Path(__file__).resolve().parents[1] / "templates" / "ticket.html"
    source = template_path.read_text()
    assert "Copy clean draft" in source, \
        "ticket.html must contain a 'Copy clean draft' button"


def test_template_contains_stored_draft_unchanged_note():
    template_path = Path(__file__).resolve().parents[1] / "templates" / "ticket.html"
    source = template_path.read_text()
    assert "Stored draft remains unchanged" in source, \
        "PM Guard Review card must note that the stored draft is unchanged"


def test_template_contains_clean_content_attribute():
    template_path = Path(__file__).resolve().parents[1] / "templates" / "ticket.html"
    source = template_path.read_text()
    assert "data-clean-content" in source, \
        "ticket.html must use data-clean-content attribute on draft textareas"


def test_template_uses_clean_content_in_js():
    template_path = Path(__file__).resolve().parents[1] / "templates" / "ticket.html"
    source = template_path.read_text()
    assert "cleanContent" in source, \
        "ticket.html JS must use dataset.cleanContent for display"
