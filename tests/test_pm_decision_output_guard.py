"""Tests for apply_pm_decision_output_guard."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.pm_decision_formatter import apply_pm_decision_output_guard


# ── Helpers ───────────────────────────────────────────────────────────────────

def _short_pm(should_mention_law=False, needs_prd=False, max_words=200):
    return {
        "answer_depth": "short",
        "max_words": max_words,
        "should_mention_law": should_mention_law,
        "needs_prd": needs_prd,
    }


SHORT_CLEAN = "Bien reçu. Nous allons corriger le libellé dans la prochaine mise à jour."


# ── Guard 1: word count ───────────────────────────────────────────────────────

def test_long_output_adds_word_count_warning():
    long_output = " ".join(["word"] * 400)  # well above 200 * 1.5
    result = apply_pm_decision_output_guard(long_output, _short_pm())
    assert "[PM guard:" in result
    assert "400 words" in result or "words" in result


def test_output_within_tolerance_has_no_word_count_warning():
    # 200 words — within 50 % tolerance of max_words=200
    ok_output = " ".join(["word"] * 200)
    result = apply_pm_decision_output_guard(ok_output, _short_pm())
    assert "[PM guard:" not in result


def test_word_count_guard_inactive_for_normal_depth():
    """Guard only fires for answer_depth=short."""
    long_output = " ".join(["word"] * 800)
    pm = {"answer_depth": "detailed", "max_words": 800, "should_mention_law": False, "needs_prd": False}
    result = apply_pm_decision_output_guard(long_output, pm)
    # No word-count warning for non-short depth
    assert "[PM guard:" not in result or "words" not in result


# ── Guard 2: legal citations ──────────────────────────────────────────────────

def test_legal_reference_adds_warning_when_law_false():
    output = "This is required per Article 123 of the commercial code."
    result = apply_pm_decision_output_guard(output, _short_pm(should_mention_law=False))
    assert "[PM guard:" in result
    assert "legal reference detected" in result or "should_mention_law=false" in result


def test_french_law_reference_adds_warning():
    output = "Conformément à la loi du 19 décembre 2002, ce champ est obligatoire."
    result = apply_pm_decision_output_guard(output, _short_pm(should_mention_law=False))
    assert "[PM guard:" in result


def test_no_warning_when_should_mention_law_is_true():
    output = "This is required per Article 123 of the commercial code."
    result = apply_pm_decision_output_guard(output, _short_pm(should_mention_law=True))
    # Guard should NOT fire because should_mention_law is True
    assert "should_mention_law=false" not in result


def test_no_warning_when_should_mention_law_is_default_absent():
    """Guard only fires when should_mention_law is explicitly False."""
    output = "This is required per Article 123 of the commercial code."
    pm = {"answer_depth": "short", "max_words": 200}  # key absent
    result = apply_pm_decision_output_guard(output, pm)
    assert "should_mention_law=false" not in result


def test_only_one_legal_warning_per_output():
    """Multiple legal patterns should produce exactly one legal guard entry."""
    output = "Article 12 applies. Law of 2002 requires this. Legal requirement confirmed."
    result = apply_pm_decision_output_guard(output, _short_pm(should_mention_law=False))
    count = result.count("[PM guard: legal reference")
    assert count == 1, f"Expected exactly 1 legal warning, got {count}"


# ── Guard 3: PRD headings ─────────────────────────────────────────────────────

def test_prd_heading_adds_warning_when_prd_false():
    output = "## Objective:\nThe client wants a new section.\n\nAcceptance Criteria: done."
    result = apply_pm_decision_output_guard(output, _short_pm(needs_prd=False))
    assert "[PM guard:" in result
    assert "PRD-style" in result or "needs_prd=false" in result


def test_prd_warning_only_once_per_output():
    output = (
        "## Objective:\n## User Stories:\n"
        "Acceptance Criteria: x\nDefinition of Done: y"
    )
    result = apply_pm_decision_output_guard(output, _short_pm(needs_prd=False))
    count = result.count("[PM guard: PRD-style")
    assert count == 1, f"Expected exactly 1 PRD warning, got {count}"


def test_no_prd_warning_when_needs_prd_is_true():
    output = "## Objective:\nThis is a PRD-style output."
    pm = {"answer_depth": "detailed", "max_words": 800, "needs_prd": True}
    result = apply_pm_decision_output_guard(output, pm)
    assert "needs_prd=false" not in result


def test_no_prd_warning_when_needs_prd_absent():
    """Guard only fires when needs_prd is explicitly False."""
    output = "## Objective:\nSome heading."
    pm = {"answer_depth": "short", "max_words": 200}  # key absent
    result = apply_pm_decision_output_guard(output, pm)
    assert "needs_prd=false" not in result


# ── Clean output — no warnings ────────────────────────────────────────────────

def test_clean_short_output_has_no_warning():
    result = apply_pm_decision_output_guard(SHORT_CLEAN, _short_pm())
    assert "[PM guard:" not in result


def test_empty_output_returns_unchanged():
    result = apply_pm_decision_output_guard("", _short_pm())
    assert result == ""


def test_empty_pm_decision_returns_output_unchanged():
    output = "Some response text."
    result = apply_pm_decision_output_guard(output, {})
    assert result == output
    result2 = apply_pm_decision_output_guard(output, None)
    assert result2 == output


# ── Warning content ───────────────────────────────────────────────────────────

def test_warnings_are_appended_not_prepended():
    """Warnings must appear after the original content, not before it."""
    output = "Some clean text."
    long_output = " ".join(["word"] * 400)
    result = apply_pm_decision_output_guard(long_output, _short_pm())
    guard_pos = result.index("[PM guard:")
    assert guard_pos > len(long_output) // 2, "Guard warning should appear after the main content"


def test_original_content_is_preserved():
    """The original AI text must be present verbatim in the guarded output."""
    output = SHORT_CLEAN
    long_output = " ".join(["word"] * 400)
    result = apply_pm_decision_output_guard(long_output, _short_pm())
    assert long_output in result, "Original content must be preserved unchanged"


# ── Guard A: global default change ───────────────────────────────────────────

def test_global_default_phrase_triggers_warning_when_high_risk():
    """High global_change_risk + global-default language → warning."""
    pm = {"global_change_risk": "high", "should_mention_law": False, "needs_prd": False}
    output = "We suggest changing the default globally so all clients benefit."
    result = apply_pm_decision_output_guard(output, pm)
    assert "[PM guard: global default change suggested" in result


def test_update_default_wording_phrase_triggers_warning():
    pm = {"global_change_risk": "high"}
    output = "The best solution would be to update the default wording for everyone."
    result = apply_pm_decision_output_guard(output, pm)
    assert "[PM guard: global default change suggested" in result


def test_no_global_warning_when_risk_is_low():
    """No global-default warning when risk is not high."""
    pm = {"global_change_risk": "low"}
    output = "We suggest changing the default globally so all clients benefit."
    result = apply_pm_decision_output_guard(output, pm)
    assert "global default change suggested" not in result


def test_no_global_warning_when_no_global_phrase():
    """High risk but no global-default phrase → no warning."""
    pm = {"global_change_risk": "high"}
    output = "We can make this field configurable per client."
    result = apply_pm_decision_output_guard(output, pm)
    assert "global default change suggested" not in result


# ── Guard B: make editable — editability not mentioned ────────────────────────

def test_make_editable_without_editable_phrase_triggers_warning():
    """recommended_action=make_editable but output has no editable/configurable → warning."""
    pm = {"recommended_action": "make_editable"}
    output = "We will look into changing the wording for you."
    result = apply_pm_decision_output_guard(output, pm)
    assert "[PM guard: recommended_action=make_editable" in result


def test_make_editable_with_editable_phrase_no_warning():
    """recommended_action=make_editable and output mentions editable → no warning."""
    pm = {"recommended_action": "make_editable"}
    output = "The field can be made editable per client in the configuration settings."
    result = apply_pm_decision_output_guard(output, pm)
    assert "recommended_action=make_editable" not in result


def test_make_editable_with_configurable_phrase_no_warning():
    pm = {"recommended_action": "make_editable"}
    output = "This section is configurable per client."
    result = apply_pm_decision_output_guard(output, pm)
    assert "recommended_action=make_editable" not in result


# ── Guard C: bug_fix framed as feature request ────────────────────────────────

def test_bug_fix_framed_as_feature_request_triggers_warning():
    """development_type=bug_fix + only feature-request language (no bug/fix) → warning."""
    pm = {"development_type": "bug_fix"}
    output = "This is a new feature request that will enhance the product."
    result = apply_pm_decision_output_guard(output, pm)
    assert "[PM guard: bug_fix decision may have been framed as a feature request" in result


def test_bug_fix_with_bug_language_no_warning():
    """development_type=bug_fix + output contains bug/fix language → no warning."""
    pm = {"development_type": "bug_fix"}
    output = "We have identified a bug and will provide a fix in the next release."
    result = apply_pm_decision_output_guard(output, pm)
    assert "framed as a feature request" not in result


def test_bug_fix_no_feature_framing_no_warning():
    """development_type=bug_fix but output has neither feature-request nor bug language → no warning."""
    pm = {"development_type": "bug_fix"}
    output = "We will investigate the issue and get back to you."
    result = apply_pm_decision_output_guard(output, pm)
    assert "framed as a feature request" not in result


# ── Guard D: support guidance escalated to development ────────────────────────

def test_support_guidance_create_jira_triggers_warning():
    """development_type=support_guidance + 'create a jira' → warning."""
    pm = {"development_type": "support_guidance"}
    output = "We will create a Jira ticket and development required to implement this."
    result = apply_pm_decision_output_guard(output, pm)
    assert "[PM guard: support guidance decision may have been escalated to development" in result


def test_support_guidance_development_required_triggers_warning():
    pm = {"development_type": "support_guidance"}
    output = "Development required to implement this change for the client."
    result = apply_pm_decision_output_guard(output, pm)
    assert "[PM guard: support guidance decision may have been escalated to development" in result


def test_support_guidance_no_dev_language_no_warning():
    """development_type=support_guidance + clean support answer → no warning."""
    pm = {"development_type": "support_guidance"}
    output = "You can use the existing workaround by adjusting the template settings."
    result = apply_pm_decision_output_guard(output, pm)
    assert "escalated to development" not in result


# ── Integration: pm_decision_json column migration ───────────────────────────

def test_pm_decision_json_column_in_migrations():
    """The pm_decision_json column must be registered in the migration dict."""
    import importlib, sys
    # We can't import app.py directly (Flask app), so check the source text
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app_source = app_path.read_text()
    assert "pm_decision_json" in app_source, (
        "pm_decision_json column not found in app.py migrations"
    )
    # Verify it appears in the ticket_migrations-style block
    assert "ALTER TABLE tickets ADD COLUMN pm_decision_json" in app_source
