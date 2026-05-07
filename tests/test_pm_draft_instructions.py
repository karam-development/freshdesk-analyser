"""Tests for build_pm_draft_instructions and get_pm_draft_mode."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.pm_draft_instructions import build_pm_draft_instructions, get_pm_draft_mode


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pm(**kwargs):
    """Build a minimal PMDecision-like dict, merging kwargs on top of safe defaults."""
    base = {
        "decision": "needs_analysis",
        "classification": "needs_analysis",
        "complexity": "simple",
        "answer_depth": "short",
        "max_words": 200,
        "needs_prd": False,
        "needs_development": False,
        "development_type": "unclear",
        "legal_status": "unclear",
        "should_mention_law": False,
        "global_change_risk": "unclear",
        "recommended_action": "needs_analysis",
        "reason": "",
    }
    base.update(kwargs)
    return base


# ── build_pm_draft_instructions — basic ──────────────────────────────────────

def test_empty_pm_decision_returns_empty_string():
    assert build_pm_draft_instructions({}) == ""
    assert build_pm_draft_instructions(None) == ""


def test_returns_non_empty_string_for_valid_pm():
    result = build_pm_draft_instructions(_pm())
    assert isinstance(result, str)
    assert len(result) > 0


def test_output_starts_with_header():
    result = build_pm_draft_instructions(_pm())
    assert result.startswith("PM DRAFTING INSTRUCTIONS")


# ── answer_depth = short ──────────────────────────────────────────────────────

def test_short_answer_depth_includes_concise_instruction():
    result = build_pm_draft_instructions(_pm(answer_depth="short", max_words=200))
    lower = result.lower()
    assert "short" in lower or "concise" in lower or "200" in result


def test_short_answer_no_prd_style_instruction():
    result = build_pm_draft_instructions(_pm(answer_depth="short"))
    lower = result.lower()
    assert "prd" in lower or "long explanation" in lower or "no long" in lower


# ── should_mention_law = False ────────────────────────────────────────────────

def test_should_mention_law_false_includes_no_law_instruction():
    result = build_pm_draft_instructions(_pm(should_mention_law=False))
    lower = result.lower()
    assert "law" in lower or "legal" in lower or "article" in lower


def test_should_mention_law_true_does_not_add_no_law_instruction():
    result = build_pm_draft_instructions(_pm(should_mention_law=True))
    assert "Do NOT cite law" not in result


# ── global_change_risk = high ─────────────────────────────────────────────────

def test_global_change_risk_high_includes_no_global_default_instruction():
    result = build_pm_draft_instructions(_pm(global_change_risk="high"))
    lower = result.lower()
    assert "global" in lower or "default" in lower


def test_global_change_risk_low_does_not_add_global_instruction():
    result = build_pm_draft_instructions(_pm(global_change_risk="low"))
    assert "Do NOT propose changing the global default" not in result


# ── recommended_action = make_editable ───────────────────────────────────────

def test_make_editable_includes_editability_instruction():
    result = build_pm_draft_instructions(_pm(recommended_action="make_editable"))
    lower = result.lower()
    assert "editable" in lower or "configurable" in lower


def test_non_make_editable_does_not_add_editability_instruction():
    result = build_pm_draft_instructions(_pm(recommended_action="needs_analysis"))
    assert "editable/configurable per client" not in result


# ── decision = refuse_global_change ──────────────────────────────────────────

def test_refuse_global_change_includes_polite_refusal_instruction():
    result = build_pm_draft_instructions(_pm(decision="refuse_global_change"))
    lower = result.lower()
    assert "default" in lower or "unchanged" in lower or "politely" in lower


# ── support_guidance ─────────────────────────────────────────────────────────

def test_support_guidance_decision_includes_workaround_instruction():
    result = build_pm_draft_instructions(_pm(decision="support_guidance"))
    lower = result.lower()
    assert "workaround" in lower or "available setting" in lower


def test_support_guidance_dev_type_includes_workaround_instruction():
    result = build_pm_draft_instructions(_pm(development_type="support_guidance"))
    lower = result.lower()
    assert "workaround" in lower or "available setting" in lower


def test_explain_workaround_decision_includes_workaround_instruction():
    result = build_pm_draft_instructions(_pm(decision="explain_workaround"))
    lower = result.lower()
    assert "workaround" in lower


# ── bug_fix ───────────────────────────────────────────────────────────────────

def test_bug_fix_dev_type_includes_defect_instruction():
    result = build_pm_draft_instructions(_pm(development_type="bug_fix"))
    lower = result.lower()
    assert "defect" in lower or "fix" in lower or "bug" in lower


def test_accept_bug_decision_includes_defect_instruction():
    result = build_pm_draft_instructions(_pm(decision="accept_bug"))
    lower = result.lower()
    assert "defect" in lower or "fix" in lower or "bug" in lower


# ── needs_prd = False ────────────────────────────────────────────────────────

def test_needs_prd_false_includes_no_prd_instruction():
    result = build_pm_draft_instructions(_pm(needs_prd=False))
    lower = result.lower()
    assert "prd" in lower or "objective" in lower or "acceptance criteria" in lower


def test_needs_prd_true_does_not_add_no_prd_instruction():
    result = build_pm_draft_instructions(_pm(needs_prd=True))
    assert "Do NOT generate Objective" not in result


# ── get_pm_draft_mode ────────────────────────────────────────────────────────

def test_draft_mode_client_preference_classification():
    mode = get_pm_draft_mode(_pm(classification="client_preference"))
    assert mode == "short_preference_response"


def test_draft_mode_make_editable_decision():
    mode = get_pm_draft_mode(_pm(decision="make_editable"))
    assert mode == "short_preference_response"


def test_draft_mode_refuse_global_change_decision():
    mode = get_pm_draft_mode(_pm(decision="refuse_global_change"))
    assert mode == "short_preference_response"


def test_draft_mode_product_standard_classification():
    mode = get_pm_draft_mode(_pm(classification="product_standard"))
    assert mode == "short_preference_response"


def test_draft_mode_support_guidance_dev_type():
    mode = get_pm_draft_mode(_pm(
        development_type="support_guidance",
        decision="explain_workaround",
        classification="how_to",
    ))
    assert mode == "workaround_response"


def test_draft_mode_explain_workaround_decision():
    mode = get_pm_draft_mode(_pm(decision="explain_workaround"))
    assert mode == "workaround_response"


def test_draft_mode_bug_fix_dev_type():
    mode = get_pm_draft_mode(_pm(development_type="bug_fix", decision="accept_bug"))
    assert mode == "bug_fix_response"


def test_draft_mode_accept_bug_decision():
    mode = get_pm_draft_mode(_pm(decision="accept_bug", classification="bug"))
    assert mode == "bug_fix_response"


def test_draft_mode_feature_request_dev_type():
    mode = get_pm_draft_mode(_pm(
        development_type="feature_request",
        decision="feature_request",
        classification="feature_request",
    ))
    assert mode == "feature_request_response"


def test_draft_mode_needs_analysis_decision():
    mode = get_pm_draft_mode(_pm(decision="needs_analysis", complexity="needs_analysis"))
    assert mode == "needs_analysis_response"


def test_draft_mode_needs_analysis_complexity():
    mode = get_pm_draft_mode(_pm(decision="needs_analysis", complexity="needs_analysis"))
    assert mode == "needs_analysis_response"


def test_draft_mode_normal_fallback():
    mode = get_pm_draft_mode(_pm(
        decision="accept_global_fix",
        classification="expected_behaviour",
        development_type="no_dev",
        complexity="simple",
    ))
    assert mode == "normal_response"


def test_draft_mode_empty_dict():
    assert get_pm_draft_mode({}) == "normal_response"


def test_draft_mode_none():
    assert get_pm_draft_mode(None) == "normal_response"


# ── Draft mode appears in instructions ───────────────────────────────────────

def test_instructions_include_draft_mode():
    result = build_pm_draft_instructions(_pm(
        decision="make_editable",
        classification="client_preference",
    ))
    assert "short_preference_response" in result


# ── Acceptance scenario ───────────────────────────────────────────────────────

def test_acceptance_scenario_make_editable_client_preference():
    """Full acceptance scenario: client_preference + make_editable + high risk.

    Instructions must:
      - mention short/concise
      - say no law
      - say no global default change
      - say make editable/configurable
      - say no PRD
      - draft mode = short_preference_response
    """
    pm = {
        "decision": "make_editable",
        "classification": "client_preference",
        "complexity": "simple",
        "answer_depth": "short",
        "max_words": 200,
        "needs_prd": False,
        "needs_development": True,
        "development_type": "small_improvement",
        "legal_status": "client_preference",
        "should_mention_law": False,
        "global_change_risk": "high",
        "recommended_action": "make_editable",
        "reason": "Client preference and current behaviour is correct.",
    }

    result = build_pm_draft_instructions(pm)
    lower = result.lower()

    # Short / concise
    assert "short" in lower or "concise" in lower or "200" in result, \
        "Instructions must include short/concise/word-limit guidance"

    # No law
    assert "law" in lower or "legal" in lower, \
        "Instructions must include no-law guidance"

    # No global default
    assert "global" in lower or "default" in lower, \
        "Instructions must include no-global-default guidance"

    # Make editable
    assert "editable" in lower or "configurable" in lower, \
        "Instructions must include editability/configurability guidance"

    # No PRD
    assert "prd" in lower or "objective" in lower or "acceptance criteria" in lower, \
        "Instructions must include no-PRD guidance"

    # Draft mode
    assert "short_preference_response" in result, \
        "Instructions must include draft mode = short_preference_response"


# ── app.py source checks ──────────────────────────────────────────────────────

def test_app_uses_build_pm_draft_instructions():
    """app.py must import and use build_pm_draft_instructions in generate-drafts."""
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    source = app_path.read_text()
    assert "build_pm_draft_instructions" in source, \
        "app.py must use build_pm_draft_instructions"


def test_app_has_pm_drafting_instructions_block():
    """app.py must reference pm_draft_instructions module in the generate-drafts route."""
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    source = app_path.read_text()
    assert "pm_draft_instructions" in source, \
        "app.py must import from ai.pm_draft_instructions"
