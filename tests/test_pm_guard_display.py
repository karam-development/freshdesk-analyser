"""Tests for ai/pm_guard_display helpers."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.pm_guard_display import get_clean_draft_for_display, has_pm_guard_warnings


_MARKER = "[PM guard: recommended_action=make_editable but output does not mention editability/configurability.]"
_DRAFT_WITH_MARKER = f"Hi team, we can make the text editable per client.\n\n{_MARKER}"
_CLEAN_DRAFT = "Hi team, we can make the text editable per client."


# ── get_clean_draft_for_display ───────────────────────────────────────────────

def test_clean_draft_removes_pm_guard_lines():
    result = get_clean_draft_for_display(_DRAFT_WITH_MARKER)
    assert "[PM guard:" not in result


def test_clean_draft_preserves_normal_text():
    result = get_clean_draft_for_display(_DRAFT_WITH_MARKER)
    assert "Hi team, we can make the text editable per client." in result


def test_clean_draft_empty_string_returns_empty():
    assert get_clean_draft_for_display("") == ""


def test_clean_draft_none_returns_empty():
    assert get_clean_draft_for_display(None) == ""


def test_clean_draft_clean_input_unchanged():
    assert get_clean_draft_for_display(_CLEAN_DRAFT) == _CLEAN_DRAFT


def test_clean_draft_multiple_markers_all_removed():
    text = (
        "Normal text here.\n\n"
        "[PM guard: legal reference detected although PM decision says should_mention_law=false.]\n"
        "[PM guard: global default change suggested although global_change_risk=high.]"
    )
    result = get_clean_draft_for_display(text)
    assert "[PM guard:" not in result
    assert "Normal text here." in result


def test_clean_draft_does_not_mutate_original():
    original = _DRAFT_WITH_MARKER
    original_copy = original
    get_clean_draft_for_display(original)
    assert original == original_copy


# ── has_pm_guard_warnings ─────────────────────────────────────────────────────

def test_has_warnings_true_when_marker_present():
    assert has_pm_guard_warnings(_DRAFT_WITH_MARKER) is True


def test_has_warnings_false_for_clean_text():
    assert has_pm_guard_warnings(_CLEAN_DRAFT) is False


def test_has_warnings_false_for_empty():
    assert has_pm_guard_warnings("") is False


def test_has_warnings_false_for_none():
    assert has_pm_guard_warnings(None) is False


def test_has_warnings_true_for_legal_marker():
    text = "Some response.\n\n[PM guard: legal reference detected although PM decision says should_mention_law=false.]"
    assert has_pm_guard_warnings(text) is True


# ── Acceptance scenario ────────────────────────────────────────────────────────

def test_acceptance_scenario_clean_display_and_raw_unchanged():
    """Acceptance test from PR spec:

    raw draft: normal text + PM guard marker
    Expected:
    - clean draft contains the normal text
    - clean draft does not contain "[PM guard:"
    - PM guard extraction still finds the warning from the raw draft
    - raw text remains unchanged
    """
    from ai.pm_decision_formatter import extract_pm_guard_warnings

    raw_draft = (
        "Hi team, we can make the text editable per client.\n\n"
        "[PM guard: recommended_action=make_editable but output does not mention editability/configurability.]"
    )

    clean = get_clean_draft_for_display(raw_draft)

    # Clean contains normal text
    assert "Hi team, we can make the text editable per client." in clean, \
        "Clean draft must contain the normal text"

    # Clean does not contain marker
    assert "[PM guard:" not in clean, \
        "Clean draft must not contain PM guard markers"

    # Extract still works on raw
    warnings = extract_pm_guard_warnings(raw_draft)
    assert len(warnings) == 1, \
        "PM guard extraction must still find the warning in the raw draft"
    assert "make_editable" in warnings[0]

    # Raw is unchanged
    assert "[PM guard: recommended_action=make_editable" in raw_draft, \
        "Raw draft must remain unchanged"
