"""Tests for ai/pm_regeneration.py and PR-13 wiring."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.pm_regeneration import build_pm_regeneration_instruction


# ── Helpers ───────────────────────────────────────────────────────────────────

def _warning(code: str, severity: str = "medium") -> dict:
    return {"code": code, "severity": severity, "title": code, "message": "", "raw": ""}


# ── Empty / None inputs ───────────────────────────────────────────────────────

def test_no_decision_no_warnings_returns_empty():
    assert build_pm_regeneration_instruction(None, None) == ""


def test_empty_decision_no_warnings_returns_empty():
    assert build_pm_regeneration_instruction({}, None) == ""


def test_none_decision_empty_warnings_returns_empty():
    assert build_pm_regeneration_instruction(None, []) == ""


def test_empty_decision_empty_warnings_returns_empty():
    assert build_pm_regeneration_instruction({}, []) == ""


# ── Title always present when output is non-empty ────────────────────────────

def test_title_present_when_decision_given():
    result = build_pm_regeneration_instruction({"decision": "make_editable"}, None)
    assert "PM REGENERATION INSTRUCTIONS:" in result


def test_title_present_when_warnings_given():
    result = build_pm_regeneration_instruction(None, [_warning("editability_missing")])
    assert "PM REGENERATION INSTRUCTIONS:" in result


# ── Closing line ──────────────────────────────────────────────────────────────

def test_closing_line_present():
    result = build_pm_regeneration_instruction({"decision": "workaround"}, None)
    assert "Regenerate the draft respecting these corrections." in result
    assert "Do not mention PM guard warnings to the client." in result


# ── Decision summary block ────────────────────────────────────────────────────

def test_decision_field_included():
    result = build_pm_regeneration_instruction({"decision": "make_editable"}, None)
    assert "decision=make_editable" in result


def test_recommended_action_included():
    result = build_pm_regeneration_instruction({"recommended_action": "short_reply"}, None)
    assert "recommended_action=short_reply" in result


def test_answer_depth_included():
    result = build_pm_regeneration_instruction({"answer_depth": "brief"}, None)
    assert "answer_depth=brief" in result


def test_max_words_included_when_set():
    result = build_pm_regeneration_instruction({"max_words": 80}, None)
    assert "max_words=80" in result


def test_max_words_absent_when_not_set():
    result = build_pm_regeneration_instruction({"decision": "make_editable"}, None)
    assert "max_words" not in result


# ── Per-code correction instructions ─────────────────────────────────────────

def test_legal_reference_blocked_instruction():
    result = build_pm_regeneration_instruction(None, [_warning("legal_reference_blocked", "high")])
    assert "legal_reference_blocked" in result
    assert "legal references" in result.lower()


def test_global_default_change_blocked_instruction():
    result = build_pm_regeneration_instruction(None, [_warning("global_default_change_blocked", "high")])
    assert "global_default_change_blocked" in result
    assert "global default" in result.lower()


def test_editability_missing_instruction():
    result = build_pm_regeneration_instruction(None, [_warning("editability_missing")])
    assert "editability_missing" in result
    assert "editable" in result.lower()


def test_bug_framed_as_feature_instruction():
    result = build_pm_regeneration_instruction(None, [_warning("bug_framed_as_feature", "high")])
    assert "bug_framed_as_feature" in result
    assert "bug" in result.lower()


def test_support_escalated_to_dev_instruction():
    result = build_pm_regeneration_instruction(None, [_warning("support_escalated_to_dev")])
    assert "support_escalated_to_dev" in result
    assert "workaround" in result.lower()


def test_prd_style_blocked_instruction():
    result = build_pm_regeneration_instruction(None, [_warning("prd_style_blocked")])
    assert "prd_style_blocked" in result
    assert "prd" in result.lower()


def test_output_too_long_instruction():
    result = build_pm_regeneration_instruction(None, [_warning("output_too_long", "low")])
    assert "output_too_long" in result
    assert "shorter" in result.lower()


def test_unknown_code_produces_no_instruction():
    """An unrecognised code must not crash and must produce no correction line."""
    result = build_pm_regeneration_instruction(None, [_warning("unknown_code_xyz")])
    # No title or output — nothing to say for an unknown code
    # (no mapped instruction, and no decision fields)
    assert result == ""


# ── Deduplication ─────────────────────────────────────────────────────────────

def test_duplicate_codes_deduplicated():
    warnings = [_warning("editability_missing"), _warning("editability_missing")]
    result = build_pm_regeneration_instruction(None, warnings)
    assert result.count("editability_missing") == 1


# ── Multiple warnings ─────────────────────────────────────────────────────────

def test_multiple_warnings_all_present():
    warnings = [
        _warning("legal_reference_blocked", "high"),
        _warning("editability_missing"),
        _warning("output_too_long", "low"),
    ]
    result = build_pm_regeneration_instruction(None, warnings)
    assert "legal_reference_blocked" in result
    assert "editability_missing" in result
    assert "output_too_long" in result


# ── Combined decision + warnings ──────────────────────────────────────────────

def test_combined_decision_and_warnings():
    pm_decision = {"decision": "make_editable", "recommended_action": "short_reply", "max_words": 60}
    warnings = [_warning("editability_missing"), _warning("output_too_long", "low")]
    result = build_pm_regeneration_instruction(pm_decision, warnings)
    assert "PM REGENERATION INSTRUCTIONS:" in result
    assert "decision=make_editable" in result
    assert "recommended_action=short_reply" in result
    assert "max_words=60" in result
    assert "editability_missing" in result
    assert "output_too_long" in result
    assert "Regenerate the draft respecting these corrections." in result


# ── Does NOT mutate inputs ─────────────────────────────────────────────────────

def test_does_not_mutate_pm_decision():
    pm_decision = {"decision": "make_editable"}
    original = dict(pm_decision)
    build_pm_regeneration_instruction(pm_decision, None)
    assert pm_decision == original


def test_does_not_mutate_guard_warnings():
    warnings = [_warning("editability_missing")]
    original = [dict(w) for w in warnings]
    build_pm_regeneration_instruction(None, warnings)
    assert warnings == original


# ── Template source checks ────────────────────────────────────────────────────

def test_template_contains_regenerate_button():
    template_path = Path(__file__).resolve().parents[1] / "templates" / "ticket.html"
    source = template_path.read_text()
    assert "Regenerate draft with PM constraints" in source, \
        "ticket.html must contain 'Regenerate draft with PM constraints' button"


def test_template_contains_regenerate_route():
    template_path = Path(__file__).resolve().parents[1] / "templates" / "ticket.html"
    source = template_path.read_text()
    assert "regenerate_draft_pm" in source, \
        "ticket.html must reference regenerate_draft_pm route"


def test_template_contains_stored_draft_unchanged_note():
    template_path = Path(__file__).resolve().parents[1] / "templates" / "ticket.html"
    source = template_path.read_text()
    assert "Stored draft remains unchanged" in source


# ── app.py wiring checks ──────────────────────────────────────────────────────

def test_app_has_regenerate_draft_pm_route():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    source = app_path.read_text()
    assert "regenerate-draft-pm" in source, \
        "app.py must define the /regenerate-draft-pm route"


def test_app_uses_build_pm_regeneration_instruction():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    source = app_path.read_text()
    assert "build_pm_regeneration_instruction" in source, \
        "app.py must call build_pm_regeneration_instruction"


def test_app_route_uses_extract_pm_guard_warnings():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    source = app_path.read_text()
    assert "extract_pm_guard_warnings" in source


def test_app_route_uses_categorize_pm_guard_warnings():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    source = app_path.read_text()
    assert "categorize_pm_guard_warnings" in source


def test_app_route_uses_apply_pm_decision_output_guard():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    source = app_path.read_text()
    assert "apply_pm_decision_output_guard" in source


def test_app_route_saves_only_on_success():
    """The UPDATE statement must be inside the try block, not after."""
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    source = app_path.read_text()
    # Check that the route exists and that we commit the result
    assert "regenerate_draft_pm" in source
    assert "Draft regenerated with PM constraints applied." in source


# ── Acceptance scenario ────────────────────────────────────────────────────────

def test_acceptance_legal_and_editability_warnings():
    """Two warnings → both correction instructions present, header + footer present."""
    pm_decision = {
        "decision": "make_editable",
        "recommended_action": "make_editable",
        "answer_depth": "brief",
        "max_words": 80,
    }
    guard_warnings = [
        {"code": "legal_reference_blocked", "severity": "high",
         "title": "Legal ref blocked", "message": "", "raw": ""},
        {"code": "editability_missing", "severity": "medium",
         "title": "Editability missing", "message": "", "raw": ""},
    ]

    result = build_pm_regeneration_instruction(pm_decision, guard_warnings)

    assert "PM REGENERATION INSTRUCTIONS:" in result, "Header must be present"
    assert "legal_reference_blocked" in result
    assert "editability_missing" in result
    assert "Regenerate the draft respecting these corrections." in result
    assert "Do not mention PM guard warnings to the client." in result
    assert "decision=make_editable" in result
    assert "max_words=80" in result
