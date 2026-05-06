"""Tests for the legal/preference gate."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.gates.legal_preference_gate import evaluate_legal_preference


def test_custom_wording_no_evidence_is_client_preference():
    result = evaluate_legal_preference(
        ticket_summary="Client asks to use their preferred wording instead of the default",
        current_behaviour="Standard wording is currently displayed",
        evidence={},
    )
    assert result["legal_status"] == "client_preference"
    assert result["should_mention_law"] is False


def test_we_want_our_wording_is_client_preference():
    result = evaluate_legal_preference(
        ticket_summary="We want our own wording in this field",
    )
    assert result["legal_status"] == "client_preference"
    assert result["should_mention_law"] is False


def test_explicit_mandatory_evidence_sets_mandatory():
    result = evaluate_legal_preference(
        ticket_summary="Change the wording",
        evidence={"legal_requirement": "mandatory"},
    )
    assert result["legal_status"] == "mandatory"
    assert result["should_mention_law"] is True


def test_accounting_standard_evidence_sets_accounting_required():
    result = evaluate_legal_preference(
        ticket_summary="Adjust the label",
        evidence={"accounting_standard": "IFRS IAS 1"},
    )
    assert result["legal_status"] == "accounting_required"
    assert result["should_mention_law"] is True


def test_no_signal_is_unclear():
    result = evaluate_legal_preference(
        ticket_summary="Some change to a template field",
        evidence={},
    )
    assert result["legal_status"] == "unclear"
    assert result["should_mention_law"] is False


def test_no_evidence_never_sets_should_mention_law_true():
    """Even when the ticket mentions legal terms, should_mention_law needs evidence."""
    result = evaluate_legal_preference(
        ticket_summary="The client mentions legal requirements but no evidence is provided",
        evidence={},
    )
    assert result["should_mention_law"] is False


def test_empty_evidence_key_does_not_trigger_mandatory():
    result = evaluate_legal_preference(
        ticket_summary="Change the text",
        evidence={"legal_requirement": ""},  # empty value
    )
    # Empty value → no mandatory trigger
    assert result["should_mention_law"] is False
