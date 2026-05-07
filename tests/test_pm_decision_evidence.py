"""Tests for the PM decision evidence extractor."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.pm_decision_evidence import (
    extract_pm_ticket_summary,
    extract_pm_current_behaviour,
    extract_pm_evidence,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _ticket(subject="Test subject", description_text="A description.", description=""):
    return {"subject": subject, "description_text": description_text, "description": description}


def _html_ticket():
    return {
        "subject": "HTML ticket",
        "description_text": "",
        "description": "<p>Client <b>wants</b> to change the <em>label</em>.</p>",
    }


# ── extract_pm_ticket_summary ─────────────────────────────────────────────────

def test_summary_includes_subject_and_description():
    t = _ticket(subject="Change wording", description_text="Client wants preferred wording.")
    result = extract_pm_ticket_summary(t)
    assert "Change wording" in result
    assert "Client wants preferred wording" in result


def test_summary_strips_html_from_description():
    result = extract_pm_ticket_summary(_html_ticket())
    assert "<p>" not in result
    assert "<b>" not in result
    assert "Client" in result
    assert "label" in result


def test_summary_handles_missing_description():
    t = {"subject": "Only subject", "description_text": "", "description": ""}
    result = extract_pm_ticket_summary(t)
    assert "Only subject" in result


def test_summary_handles_missing_subject():
    t = {"subject": "", "description_text": "Just description.", "description": ""}
    result = extract_pm_ticket_summary(t)
    assert "Just description" in result


def test_summary_handles_completely_empty_ticket():
    result = extract_pm_ticket_summary({})
    assert isinstance(result, str)  # must not raise


def test_summary_is_truncated_to_max_chars():
    long_desc = "word " * 400  # ~2000 chars
    t = _ticket(subject="Subject", description_text=long_desc)
    result = extract_pm_ticket_summary(t)
    assert len(result) <= 1100  # allow small margin for the ellipsis


def test_summary_uses_conversation_when_description_short():
    t = {"subject": "Short", "description_text": "Hi.", "description": ""}
    conversations = [
        {"incoming": True, "body": "<p>We want our own wording in this field.</p>"},
    ]
    result = extract_pm_ticket_summary(t, conversations=conversations)
    assert "our own wording" in result


def test_summary_skips_agent_conversation():
    """Only customer messages (incoming=True) supplement the description."""
    t = {"subject": "Short", "description_text": "Hi.", "description": ""}
    conversations = [
        {"incoming": False, "body": "Agent reply — should be ignored."},
        {"incoming": True, "body": "Client follow-up content."},
    ]
    result = extract_pm_ticket_summary(t, conversations=conversations)
    assert "Client follow-up content" in result
    assert "Agent reply" not in result


# ── extract_pm_current_behaviour ─────────────────────────────────────────────

def test_current_behaviour_prefers_code_brief():
    t = _ticket()
    result = extract_pm_current_behaviour(
        t,
        code_brief="The template currently shows the standard wording.",
        analysis="Analysis says something else.",
    )
    assert "standard wording" in result
    assert "Analysis says" not in result


def test_current_behaviour_falls_back_to_analysis():
    t = _ticket()
    result = extract_pm_current_behaviour(t, code_brief="", analysis="Analysis: field is correct.")
    assert "Analysis" in result or "correct" in result


def test_current_behaviour_returns_empty_when_both_absent():
    result = extract_pm_current_behaviour(_ticket(), code_brief="", analysis="")
    assert result == ""


def test_current_behaviour_truncated():
    long_brief = "detail " * 300
    result = extract_pm_current_behaviour(_ticket(), code_brief=long_brief)
    assert len(result) <= 900  # 800 chars + ellipsis margin


# ── extract_pm_evidence — context flags ──────────────────────────────────────

def test_evidence_has_code_context_true_when_brief_given():
    ev = extract_pm_evidence(_ticket(), code_brief="Some code brief.")
    assert ev["has_code_context"] is True


def test_evidence_has_code_context_false_when_brief_absent():
    ev = extract_pm_evidence(_ticket(), code_brief="")
    assert ev["has_code_context"] is False


def test_evidence_has_analysis_context():
    ev = extract_pm_evidence(_ticket(), analysis="Some analysis.")
    assert ev["has_analysis_context"] is True


def test_evidence_has_kb_context():
    ev = extract_pm_evidence(_ticket(), kb_brief="KB content.")
    assert ev["has_kb_context"] is True


# ── extract_pm_evidence — keyword signals ────────────────────────────────────

def test_detects_custom_wording_phrase():
    t = _ticket(description_text="We want our own wording in this field.")
    ev = extract_pm_evidence(t)
    assert ev["mentions_custom_wording"] is True


def test_detects_preferred_wording():
    t = _ticket(description_text="Client prefers their preferred wording.")
    ev = extract_pm_evidence(t)
    assert ev["mentions_custom_wording"] is True


def test_detects_existing_workaround():
    t = _ticket(description_text="How to use the workaround for this section?")
    ev = extract_pm_evidence(t)
    assert ev["mentions_existing_workaround"] is True


def test_detects_wrong_output():
    t = _ticket(description_text="The template is producing the wrong output for account 601.")
    ev = extract_pm_evidence(t)
    assert ev["mentions_wrong_output"] is True


def test_detects_incorrect_result():
    t = _ticket(description_text="The calculation result is incorrect.")
    ev = extract_pm_evidence(t)
    assert ev["mentions_wrong_output"] is True


def test_detects_correct_current_behaviour_from_analysis():
    ev = extract_pm_evidence(
        _ticket(),
        analysis="The current wording is correct and standard.",
    )
    assert ev["mentions_correct_current_behaviour"] is True


def test_detects_correct_behaviour_from_code_brief():
    ev = extract_pm_evidence(
        _ticket(),
        code_brief="Template behaviour is correct and expected.",
    )
    assert ev["mentions_correct_current_behaviour"] is True


# ── Legal terms: signal only, NOT mandatory ───────────────────────────────────

def test_legal_terms_only_set_mentions_legal_terms():
    """mentions_legal_terms is a signal flag only — it must NOT trigger should_mention_law.
    The legal_preference_gate is the only component that sets should_mention_law=True,
    and it requires an explicit evidence key like legal_requirement or accounting_standard."""
    t = _ticket(description_text="Client mentions this might be a legal requirement.")
    ev = extract_pm_evidence(t)
    # Evidence signal is set
    assert ev["mentions_legal_terms"] is True
    # But evidence dict does NOT contain mandatory/legal_requirement keys
    assert "legal_requirement" not in ev
    assert "mandatory" not in ev
    assert "accounting_standard" not in ev


def test_legal_terms_false_for_neutral_ticket():
    t = _ticket(description_text="Client wants to add a dropdown option.")
    ev = extract_pm_evidence(t)
    assert ev["mentions_legal_terms"] is False


def test_legal_terms_detected_in_analysis():
    ev = extract_pm_evidence(
        _ticket(description_text="Change the label."),
        analysis="This is required by Luxembourg law and the RGD.",
    )
    assert ev["mentions_legal_terms"] is True


# ── source_fields ─────────────────────────────────────────────────────────────

def test_source_fields_includes_subject_and_description():
    t = _ticket(subject="Subject", description_text="Description.")
    ev = extract_pm_evidence(t)
    assert "subject" in ev["source_fields"]
    assert "description" in ev["source_fields"]


def test_source_fields_includes_code_brief_when_given():
    ev = extract_pm_evidence(_ticket(), code_brief="Some brief.")
    assert "code_brief" in ev["source_fields"]


def test_source_fields_excludes_empty_fields():
    t = {"subject": "", "description_text": "", "description": ""}
    ev = extract_pm_evidence(t)
    assert "subject" not in ev["source_fields"]
    assert "description" not in ev["source_fields"]


def test_source_fields_includes_kb_brief():
    ev = extract_pm_evidence(_ticket(), kb_brief="KB content.")
    assert "kb_brief" in ev["source_fields"]


# ── Defensive handling ────────────────────────────────────────────────────────

def test_all_functions_handle_none_values():
    t = {"subject": None, "description_text": None, "description": None}
    assert isinstance(extract_pm_ticket_summary(t), str)
    assert isinstance(extract_pm_current_behaviour(t), str)
    assert isinstance(extract_pm_evidence(t), dict)


def test_all_functions_handle_missing_keys():
    t = {}
    assert isinstance(extract_pm_ticket_summary(t), str)
    assert isinstance(extract_pm_current_behaviour(t), str)
    assert isinstance(extract_pm_evidence(t), dict)
