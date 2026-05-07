"""Tests for the global change risk gate."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.gates.global_change_risk_gate import evaluate_global_change_risk


def test_correct_wording_client_preference_is_high_risk():
    result = evaluate_global_change_risk(
        ticket_summary="Client wants to change the wording to match their company style",
        current_behaviour="The current wording is correct and standard",
        legal_status="client_preference",
    )
    assert result["global_change_risk"] == "high"
    assert result["safe_to_change_default"] is False
    assert result["recommended_action"] in ("make_editable", "refuse_global_change")


def test_client_preference_without_correct_signal_is_still_high_risk():
    result = evaluate_global_change_risk(
        ticket_summary="Client prefers their own wording",
        legal_status="client_preference",
    )
    assert result["global_change_risk"] == "high"
    assert result["safe_to_change_default"] is False


def test_legally_wrong_wording_is_safe_to_fix():
    result = evaluate_global_change_risk(
        ticket_summary="The wording is incorrect per accounting standards",
        current_behaviour="The current output is wrong and not correct",
        legal_status="accounting_required",
    )
    assert result["global_change_risk"] == "low"
    assert result["safe_to_change_default"] is True


def test_mandatory_fix_for_wrong_behaviour_is_low_risk():
    result = evaluate_global_change_risk(
        ticket_summary="The label is wrong and must be fixed per Luxembourg law",
        current_behaviour="The wording is incorrect",
        legal_status="mandatory",
    )
    assert result["global_change_risk"] == "low"
    assert result["safe_to_change_default"] is True
    assert result["recommended_action"] == "accept_global_fix"


def test_optional_status_with_correct_behaviour_is_high_risk():
    result = evaluate_global_change_risk(
        ticket_summary="Client would like an optional change to the default label",
        current_behaviour="The current standard wording is correct",
        legal_status="optional",
    )
    assert result["global_change_risk"] == "high"
    assert result["safe_to_change_default"] is False


# ── PR #9: evidence signal tests ─────────────────────────────────────────────

def test_product_standard_status_is_high_risk():
    """legal_status=product_standard → high risk, make_editable."""
    result = evaluate_global_change_risk(
        ticket_summary="Client wants a different label",
        current_behaviour="Label is as designed",
        legal_status="product_standard",
    )
    assert result["global_change_risk"] == "high"
    assert result["safe_to_change_default"] is False
    assert result["recommended_action"] == "make_editable"


def test_evidence_mentions_custom_wording_triggers_high_risk():
    """evidence['mentions_custom_wording']=True with no wrong output → high risk."""
    result = evaluate_global_change_risk(
        ticket_summary="Client requests a change",
        current_behaviour="",
        legal_status="unclear",
        evidence={"mentions_custom_wording": True},
    )
    assert result["global_change_risk"] == "high"
    assert result["safe_to_change_default"] is False
    assert result["recommended_action"] == "make_editable"


def test_evidence_mentions_wrong_output_with_mandatory_is_low_risk():
    """evidence['mentions_wrong_output']=True + legal_status='mandatory' → low risk."""
    result = evaluate_global_change_risk(
        ticket_summary="The label is incorrect",
        current_behaviour="",
        legal_status="mandatory",
        evidence={"mentions_wrong_output": True},
    )
    assert result["global_change_risk"] == "low"
    assert result["safe_to_change_default"] is True
    assert result["recommended_action"] == "accept_global_fix"


def test_evidence_mentions_correct_behaviour_supplements_keywords():
    """evidence['mentions_correct_current_behaviour']=True without keyword → high risk."""
    result = evaluate_global_change_risk(
        ticket_summary="Client wants their own phrasing",
        current_behaviour="",   # no "correct" keyword in text
        legal_status="unclear",
        evidence={"mentions_correct_current_behaviour": True},
    )
    assert result["global_change_risk"] == "high"
    assert result["safe_to_change_default"] is False
