"""Tests for the PM decision runner and the critical acceptance scenario."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.pm_decision_runner import build_pm_decision_for_ticket
from ai.schemas import REQUIRED_FIELDS


# ── Field completeness ────────────────────────────────────────────────────────

def test_runner_returns_all_required_fields():
    result = build_pm_decision_for_ticket("Some ticket about a template")
    for field in REQUIRED_FIELDS:
        assert field in result, f"Missing required field: {field}"


def test_runner_includes_gate_results_debug_key():
    result = build_pm_decision_for_ticket("Some ticket")
    assert "_gate_results" in result, "_gate_results debug key should be present"
    assert isinstance(result["_gate_results"], dict)
    for gate in ("complexity", "legal_preference", "global_change_risk", "development_need"):
        assert gate in result["_gate_results"], f"Gate {gate} missing from _gate_results"


def test_runner_never_crashes_on_empty_input():
    """Empty input must produce safe defaults, not raise."""
    result = build_pm_decision_for_ticket("")
    assert result["decision"] == "needs_analysis"
    assert result["should_mention_law"] is False
    assert result["needs_prd"] is False
    assert result["max_words"] <= 250


# ── Client wording preference scenario ───────────────────────────────────────

def test_client_wording_preference_produces_high_risk_short_decision():
    """Client wants a wording change on correct current wording — must be high risk,
    short answer, no PRD, no law mention."""
    result = build_pm_decision_for_ticket(
        ticket_summary="Client wants to change the default wording to their preferred wording.",
        current_behaviour="Current wording is correct and standard.",
    )
    assert result["global_change_risk"] == "high", (
        f"Expected high global_change_risk, got {result['global_change_risk']}"
    )
    assert result["answer_depth"] == "short", (
        f"Expected short answer_depth, got {result['answer_depth']}"
    )
    assert result["needs_prd"] is False, (
        f"Expected needs_prd=False, got {result['needs_prd']}"
    )
    assert result["should_mention_law"] is False, (
        f"Expected should_mention_law=False, got {result['should_mention_law']}"
    )
    assert result["max_words"] <= 250, (
        f"Expected max_words<=250, got {result['max_words']}"
    )


def test_client_wording_preference_decision_not_accept():
    """The decision for a wording preference must not be a simple accept."""
    result = build_pm_decision_for_ticket(
        ticket_summary="Client wants to use their own preferred wording in the note.",
        current_behaviour="The current wording is correct.",
    )
    assert result["decision"] not in ("accept", "accept_global_fix"), (
        f"Decision should not accept global change, got {result['decision']}"
    )
    assert result["classification"] in (
        "client_preference", "needs_analysis"
    ), f"Unexpected classification: {result['classification']}"


# ── Bug scenario ──────────────────────────────────────────────────────────────

def test_bug_scenario_returns_bug_classification():
    result = build_pm_decision_for_ticket(
        ticket_summary="The template is producing the wrong output for account 601."
    )
    assert result["classification"] == "bug", (
        f"Expected bug classification, got {result['classification']}"
    )
    assert result["decision"] == "accept_bug", (
        f"Expected accept_bug decision, got {result['decision']}"
    )
    assert result["needs_development"] is True


def test_broken_calculation_is_bug_fix():
    result = build_pm_decision_for_ticket(
        "The calculation is incorrect — the result is clearly wrong."
    )
    assert result["classification"] == "bug"
    assert result["needs_development"] is True


# ── Support / workaround scenario ─────────────────────────────────────────────

def test_workaround_ticket_returns_support_guidance():
    result = build_pm_decision_for_ticket(
        "Client asks how to use the existing workaround for the reconciliation note."
    )
    assert result["needs_development"] is False, (
        f"Expected no development needed, got needs_development={result['needs_development']}"
    )
    assert result["decision"] in ("explain_workaround", "support_guidance"), (
        f"Expected explain_workaround or support_guidance, got {result['decision']}"
    )


def test_support_question_no_development():
    result = build_pm_decision_for_ticket(
        "Client wants guidance on how to set up the template correctly."
    )
    assert result["needs_development"] is False


# ── pm_decision_json serialisation ───────────────────────────────────────────

def test_runner_output_is_json_serialisable():
    """The result (minus _gate_results) must be JSON-serialisable for DB storage."""
    result = build_pm_decision_for_ticket("Test ticket")
    stripped = {k: v for k, v in result.items() if k != "_gate_results"}
    serialised = json.dumps(stripped)  # must not raise
    reloaded = json.loads(serialised)
    for field in REQUIRED_FIELDS:
        assert field in reloaded, f"Field {field} missing after JSON round-trip"


def test_safe_defaults_when_gate_raises(monkeypatch):
    """If a gate function raises, the runner should still return safe defaults."""
    import ai.gates.complexity_gate as cg
    monkeypatch.setattr(cg, "evaluate_complexity", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("forced")))

    result = build_pm_decision_for_ticket("Any ticket")
    # Must not raise and must still return required fields
    for field in REQUIRED_FIELDS:
        assert field in result, f"Missing required field after gate failure: {field}"
    assert result["should_mention_law"] is False
    assert result["needs_prd"] is False


# ── Critical acceptance scenario ──────────────────────────────────────────────

def test_acceptance_wording_preference_full_end_to_end():
    """End-to-end acceptance test: client wants wording change, current wording
    is correct, no legal evidence.

    Expected:
    - classification = client_preference
    - global_change_risk = high
    - decision = make_editable OR refuse_global_change
    - recommended_action = make_editable OR refuse_global_change
    - answer_depth = short
    - max_words <= 250
    - needs_prd = false
    - should_mention_law = false
    """
    result = build_pm_decision_for_ticket(
        ticket_summary=(
            "Client wants to change the default wording to their preferred wording."
        ),
        current_behaviour="Current wording is correct and standard.",
    )

    assert result["classification"] == "client_preference", (
        f"classification should be client_preference, got {result['classification']}"
    )
    assert result["global_change_risk"] == "high", (
        f"global_change_risk should be high, got {result['global_change_risk']}"
    )
    assert result["decision"] in ("refuse_global_change", "make_editable"), (
        f"decision should be refuse_global_change or make_editable, got {result['decision']}"
    )
    assert result["recommended_action"] in ("refuse_global_change", "make_editable"), (
        f"recommended_action should be refuse_global_change or make_editable, "
        f"got {result['recommended_action']}"
    )
    assert result["answer_depth"] == "short", (
        f"answer_depth should be short, got {result['answer_depth']}"
    )
    assert result["max_words"] <= 250, (
        f"max_words should be <= 250, got {result['max_words']}"
    )
    assert result["needs_prd"] is False, (
        f"needs_prd should be False, got {result['needs_prd']}"
    )
    assert result["should_mention_law"] is False, (
        f"should_mention_law should be False, got {result['should_mention_law']}"
    )


# ── PR #9 acceptance scenarios (A/B/C/D) ─────────────────────────────────────

def test_scenario_a_evidence_custom_wording_and_correct_behaviour():
    """Scenario A: evidence signals custom wording + correct current behaviour.
    Expected: classification=client_preference, global_change_risk=high,
    decision=make_editable, should_mention_law=False, needs_prd=False, max_words<=250.
    """
    from ai.pm_decision_evidence import extract_pm_evidence, extract_pm_current_behaviour

    ticket = {
        "subject": "Change the wording on the reconciliation note",
        "description_text": "We want our own wording in this field instead of the default.",
    }
    code_brief = "The template currently shows the standard wording as designed."
    analysis = "The current wording is correct and expected."

    evidence = extract_pm_evidence(ticket, code_brief=code_brief, analysis=analysis)
    current_behaviour = extract_pm_current_behaviour(ticket, code_brief=code_brief, analysis=analysis)

    result = build_pm_decision_for_ticket(
        ticket_summary="Change the wording on the reconciliation note\n"
                       "We want our own wording in this field instead of the default.",
        current_behaviour=current_behaviour,
        evidence=evidence,
    )

    assert result["classification"] == "client_preference", (
        f"Scenario A: expected client_preference, got {result['classification']}"
    )
    assert result["global_change_risk"] == "high", (
        f"Scenario A: expected high global_change_risk, got {result['global_change_risk']}"
    )
    assert result["decision"] in ("make_editable", "refuse_global_change"), (
        f"Scenario A: expected make_editable/refuse_global_change, got {result['decision']}"
    )
    assert result["should_mention_law"] is False, (
        f"Scenario A: expected should_mention_law=False"
    )
    assert result["needs_prd"] is False, (
        f"Scenario A: expected needs_prd=False"
    )
    assert result["max_words"] <= 250, (
        f"Scenario A: expected max_words<=250, got {result['max_words']}"
    )


def test_scenario_b_legal_terms_only_no_law_mention():
    """Scenario B: ticket mentions legal terms but no explicit mandatory evidence.
    Expected: should_mention_law=False (keyword alone is never sufficient).
    """
    from ai.pm_decision_evidence import extract_pm_evidence

    ticket = {
        "subject": "Legal requirement for wording",
        "description_text": "Client mentions this might be a legal requirement per Luxembourg law.",
    }
    evidence = extract_pm_evidence(ticket)

    result = build_pm_decision_for_ticket(
        ticket_summary="Legal requirement for wording\n"
                       "Client mentions this might be a legal requirement per Luxembourg law.",
        evidence=evidence,
    )

    assert result["should_mention_law"] is False, (
        f"Scenario B: legal terms alone must not set should_mention_law=True, "
        f"got {result['should_mention_law']}"
    )
    # No explicit mandatory keys → legal_status must NOT be "mandatory"
    assert result["legal_status"] != "mandatory", (
        f"Scenario B: legal_status should not be mandatory without explicit evidence, "
        f"got {result['legal_status']}"
    )


def test_scenario_c_existing_workaround_no_development():
    """Scenario C: existing workaround detected → no development, explain_workaround.
    """
    from ai.pm_decision_evidence import extract_pm_evidence

    ticket = {
        "subject": "How to customise the note",
        "description_text": "How can I use the existing workaround to set this field?",
    }
    evidence = extract_pm_evidence(ticket)

    result = build_pm_decision_for_ticket(
        ticket_summary="How to customise the note\n"
                       "How can I use the existing workaround to set this field?",
        evidence=evidence,
    )

    assert result["needs_development"] is False, (
        f"Scenario C: expected needs_development=False, got {result['needs_development']}"
    )
    assert result["decision"] in ("explain_workaround", "support_guidance"), (
        f"Scenario C: expected explain_workaround/support_guidance, got {result['decision']}"
    )


def test_scenario_d_wrong_output_is_bug():
    """Scenario D: evidence confirms wrong output → bug classification, accept_bug.
    """
    from ai.pm_decision_evidence import extract_pm_evidence

    ticket = {
        "subject": "Incorrect calculation result",
        "description_text": "The template is producing the wrong output for account 601.",
    }
    evidence = extract_pm_evidence(ticket)

    result = build_pm_decision_for_ticket(
        ticket_summary="Incorrect calculation result\n"
                       "The template is producing the wrong output for account 601.",
        evidence=evidence,
    )

    assert result["classification"] == "bug", (
        f"Scenario D: expected bug classification, got {result['classification']}"
    )
    assert result["decision"] == "accept_bug", (
        f"Scenario D: expected accept_bug, got {result['decision']}"
    )
    assert result["needs_development"] is True, (
        f"Scenario D: expected needs_development=True"
    )
