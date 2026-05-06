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
