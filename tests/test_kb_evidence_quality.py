"""Unit tests for ai/kb_evidence_quality.py (PR 27).

Covers:
- Empty/invalid entries → overall_quality none
- Strong score with actionable type → strong + strong_kb_evidence
- Existing setting evidence → workaround_or_setting_available
- All low score → weak + low_score_only
- Moderate score → moderate
- Legal evidence present → legal_evidence_present signal
- Legal + workaround → mixed + mixed_legal_and_workaround
- Legal evidence without legal terms in ticket_context → unsupported_legal_context
- Legal evidence with legal terms → no unsupported signal
- Generic content-only low score → generic_match_risk
- Invalid entries skipped
- Summary fields correct
- Function never mutates entries
- Acceptance scenario
"""
from __future__ import annotations

import copy

import pytest

from ai.kb_evidence_quality import assess_kb_evidence_quality


# ── Helpers ────────────────────────────────────────────────────────────────────

def _entry(title="Entry A", evidence_type="workaround_evidence",
           score=10.0, matched_terms=None, score_reasons=None, snippet="text"):
    return {
        "title": title,
        "evidence_type": evidence_type,
        "score": score,
        "matched_terms": matched_terms if matched_terms is not None else ["title:x"],
        "score_reasons": score_reasons if score_reasons is not None else ["title:x +4"],
        "snippet": snippet,
    }


def _signal_codes(result):
    return [s["code"] for s in result["signals"]]


# ── None / empty input ─────────────────────────────────────────────────────────


def test_none_entries_returns_none_quality():
    result = assess_kb_evidence_quality(None)
    assert result["has_data"] is False
    assert result["overall_quality"] == "none"


def test_empty_list_returns_none_quality():
    result = assess_kb_evidence_quality([])
    assert result["has_data"] is False
    assert result["overall_quality"] == "none"


def test_non_list_entries_returns_none_quality():
    result = assess_kb_evidence_quality("not-a-list")
    assert result["has_data"] is False


def test_all_invalid_entries_returns_none_quality():
    result = assess_kb_evidence_quality(["bad", None, 42])
    assert result["has_data"] is False
    assert result["overall_quality"] == "none"


# ── Strong quality ─────────────────────────────────────────────────────────────


def test_high_score_workaround_is_strong():
    result = assess_kb_evidence_quality([_entry(score=12.0)])
    assert result["overall_quality"] == "strong"
    assert result["has_data"] is True


def test_strong_signal_code_present():
    result = assess_kb_evidence_quality([_entry(score=12.0)])
    assert "strong_kb_evidence" in _signal_codes(result)


def test_strong_requires_actionable_type():
    # general_evidence is not actionable → should not be strong even with high score
    e = _entry(score=15.0, evidence_type="general_evidence")
    result = assess_kb_evidence_quality([e])
    assert result["overall_quality"] != "strong"


def test_strong_with_legal_type_is_strong():
    e = _entry(score=11.0, evidence_type="legal_evidence")
    result = assess_kb_evidence_quality([e])
    assert result["overall_quality"] == "strong"


# ── Workaround / setting signal ────────────────────────────────────────────────


def test_workaround_evidence_triggers_signal():
    result = assess_kb_evidence_quality([_entry(evidence_type="workaround_evidence")])
    assert "workaround_or_setting_available" in _signal_codes(result)


def test_existing_setting_evidence_triggers_signal():
    result = assess_kb_evidence_quality([_entry(evidence_type="existing_setting_evidence")])
    assert "workaround_or_setting_available" in _signal_codes(result)


def test_product_evidence_does_not_trigger_workaround_signal():
    result = assess_kb_evidence_quality([_entry(evidence_type="product_evidence", score=12.0)])
    assert "workaround_or_setting_available" not in _signal_codes(result)


# ── Weak quality ───────────────────────────────────────────────────────────────


def test_all_low_score_is_weak():
    entries = [_entry(score=2.0), _entry(score=3.0, title="B")]
    result = assess_kb_evidence_quality(entries)
    assert result["overall_quality"] == "weak"


def test_weak_signal_code_present():
    result = assess_kb_evidence_quality([_entry(score=2.0)])
    assert "weak_kb_evidence" in _signal_codes(result)


def test_low_score_only_in_summary():
    result = assess_kb_evidence_quality([_entry(score=2.0)])
    assert result["summary"]["has_low_score_only"] is True


def test_not_low_score_when_one_high():
    result = assess_kb_evidence_quality([_entry(score=2.0), _entry(score=12.0, title="B")])
    assert result["summary"]["has_low_score_only"] is False


# ── Moderate quality ───────────────────────────────────────────────────────────


def test_moderate_score_is_moderate():
    result = assess_kb_evidence_quality([_entry(score=6.0)])
    assert result["overall_quality"] == "moderate"


def test_moderate_signal_code_present():
    result = assess_kb_evidence_quality([_entry(score=6.0)])
    assert "moderate_kb_evidence" in _signal_codes(result)


def test_avg_score_above_threshold_is_moderate():
    entries = [_entry(score=4.0), _entry(score=5.0, title="B")]
    result = assess_kb_evidence_quality(entries)
    assert result["overall_quality"] == "moderate"


# ── Legal evidence signals ─────────────────────────────────────────────────────


def test_legal_evidence_triggers_signal():
    e = _entry(evidence_type="legal_evidence", score=8.0)
    result = assess_kb_evidence_quality([e])
    assert "legal_evidence_present" in _signal_codes(result)


def test_legal_signal_severity_warning_without_context():
    e = _entry(evidence_type="legal_evidence", score=8.0)
    result = assess_kb_evidence_quality([e])
    sig = next(s for s in result["signals"] if s["code"] == "legal_evidence_present")
    assert sig["severity"] == "warning"


def test_legal_signal_severity_info_with_legal_context():
    e = _entry(evidence_type="legal_evidence", score=8.0)
    ctx = {"subject": "Client asks about legal compliance with RGD"}
    result = assess_kb_evidence_quality([e], ticket_context=ctx)
    sig = next(s for s in result["signals"] if s["code"] == "legal_evidence_present")
    assert sig["severity"] == "info"


def test_summary_has_legal_evidence_true():
    e = _entry(evidence_type="legal_evidence", score=8.0)
    result = assess_kb_evidence_quality([e])
    assert result["summary"]["has_legal_evidence"] is True


def test_summary_has_legal_evidence_false():
    result = assess_kb_evidence_quality([_entry()])
    assert result["summary"]["has_legal_evidence"] is False


# ── Mixed quality ──────────────────────────────────────────────────────────────


def test_legal_plus_workaround_is_mixed():
    entries = [
        _entry(evidence_type="legal_evidence", score=8.0, title="Legal"),
        _entry(evidence_type="workaround_evidence", score=14.0, title="Workaround"),
    ]
    result = assess_kb_evidence_quality(entries)
    assert result["overall_quality"] == "mixed"


def test_mixed_signal_code_present():
    entries = [
        _entry(evidence_type="legal_evidence", score=8.0, title="Legal"),
        _entry(evidence_type="workaround_evidence", score=14.0, title="WA"),
    ]
    result = assess_kb_evidence_quality(entries)
    assert "mixed_legal_and_workaround" in _signal_codes(result)


def test_legal_plus_setting_is_mixed():
    entries = [
        _entry(evidence_type="legal_evidence", score=8.0, title="Legal"),
        _entry(evidence_type="existing_setting_evidence", score=10.0, title="Setting"),
    ]
    result = assess_kb_evidence_quality(entries)
    assert result["overall_quality"] == "mixed"


def test_conflicting_evidence_types_in_summary():
    entries = [
        _entry(evidence_type="legal_evidence", score=8.0, title="Legal"),
        _entry(evidence_type="workaround_evidence", score=14.0, title="WA"),
    ]
    result = assess_kb_evidence_quality(entries)
    assert result["summary"]["has_conflicting_evidence_types"] is True


def test_no_conflict_workaround_only():
    result = assess_kb_evidence_quality([_entry()])
    assert result["summary"]["has_conflicting_evidence_types"] is False


# ── Unsupported legal context signal ──────────────────────────────────────────


def test_legal_without_legal_terms_creates_unsupported_signal():
    e = _entry(evidence_type="legal_evidence", score=8.0)
    ctx = {"subject": "Client wants custom wording in staff cost note"}
    result = assess_kb_evidence_quality([e], ticket_context=ctx)
    assert "unsupported_legal_context" in _signal_codes(result)


def test_legal_with_legal_terms_does_not_create_unsupported_signal():
    e = _entry(evidence_type="legal_evidence", score=8.0)
    ctx = {"subject": "Client asks about mandatory RGD compliance"}
    result = assess_kb_evidence_quality([e], ticket_context=ctx)
    assert "unsupported_legal_context" not in _signal_codes(result)


def test_legal_with_ecdf_in_subject_no_unsupported():
    e = _entry(evidence_type="legal_evidence", score=8.0)
    ctx = {"subject": "eCDF report generation issue"}
    result = assess_kb_evidence_quality([e], ticket_context=ctx)
    assert "unsupported_legal_context" not in _signal_codes(result)


def test_unsupported_signal_only_when_legal_evidence_present():
    e = _entry(evidence_type="workaround_evidence", score=8.0)
    ctx = {"subject": "Client wants custom wording"}
    result = assess_kb_evidence_quality([e], ticket_context=ctx)
    assert "unsupported_legal_context" not in _signal_codes(result)


def test_none_ticket_context_does_not_crash():
    e = _entry(evidence_type="legal_evidence", score=8.0)
    result = assess_kb_evidence_quality([e], ticket_context=None)
    assert result["has_data"] is True
    assert "unsupported_legal_context" in _signal_codes(result)


# ── Generic match risk signal ─────────────────────────────────────────────────


def test_content_only_low_score_triggers_generic_risk():
    e = _entry(score=3.0, matched_terms=["content:invoice", "content:fee"])
    result = assess_kb_evidence_quality([e])
    assert "generic_match_risk" in _signal_codes(result)


def test_title_match_prevents_generic_risk():
    e = _entry(score=3.0, matched_terms=["title:invoice", "content:fee"])
    result = assess_kb_evidence_quality([e])
    assert "generic_match_risk" not in _signal_codes(result)


def test_high_score_prevents_generic_risk():
    e = _entry(score=8.0, matched_terms=["content:invoice"])
    result = assess_kb_evidence_quality([e])
    assert "generic_match_risk" not in _signal_codes(result)


def test_category_match_prevents_generic_risk():
    e = _entry(score=3.0, matched_terms=["category:payroll"])
    result = assess_kb_evidence_quality([e])
    assert "generic_match_risk" not in _signal_codes(result)


# ── Invalid entries skipped ────────────────────────────────────────────────────


def test_invalid_entries_skipped():
    entries = ["bad", None, _entry(score=12.0)]
    result = assess_kb_evidence_quality(entries)
    assert result["has_data"] is True
    assert result["summary"]["entry_count"] == 1


# ── Summary fields ─────────────────────────────────────────────────────────────


def test_summary_entry_count():
    entries = [_entry(), _entry(title="B"), _entry(title="C")]
    result = assess_kb_evidence_quality(entries)
    assert result["summary"]["entry_count"] == 3


def test_summary_max_score():
    entries = [_entry(score=5.0), _entry(score=12.0, title="B")]
    result = assess_kb_evidence_quality(entries)
    assert result["summary"]["max_score"] == 12.0


def test_summary_avg_score():
    entries = [_entry(score=4.0), _entry(score=8.0, title="B")]
    result = assess_kb_evidence_quality(entries)
    assert result["summary"]["avg_score"] == 6.0


def test_summary_evidence_types_sorted():
    entries = [
        _entry(evidence_type="workaround_evidence"),
        _entry(evidence_type="legal_evidence", title="L"),
    ]
    result = assess_kb_evidence_quality(entries)
    types = result["summary"]["evidence_types"]
    assert types == sorted(types)


def test_summary_has_product_evidence():
    e = _entry(evidence_type="product_evidence")
    result = assess_kb_evidence_quality([e])
    assert result["summary"]["has_product_evidence"] is True


def test_summary_has_existing_setting_evidence():
    e = _entry(evidence_type="existing_setting_evidence")
    result = assess_kb_evidence_quality([e])
    assert result["summary"]["has_existing_setting_evidence"] is True


# ── Immutability ───────────────────────────────────────────────────────────────


def test_function_does_not_mutate_entries():
    entries = [_entry(score=10.0)]
    original = copy.deepcopy(entries)
    assess_kb_evidence_quality(entries)
    assert entries == original


# ── quality_score ──────────────────────────────────────────────────────────────


def test_quality_score_capped_at_10():
    e = _entry(score=30.0)
    result = assess_kb_evidence_quality([e])
    assert result["quality_score"] <= 10.0


def test_quality_score_proportional():
    e = _entry(score=10.0)
    result = assess_kb_evidence_quality([e])
    assert result["quality_score"] == 5.0


# ── Acceptance scenario ────────────────────────────────────────────────────────


def test_acceptance_scenario():
    """Legal + workaround entries with non-legal ticket context."""
    entries = [
        {
            "title": "Invoice VAT legal disclosure",
            "evidence_type": "legal_evidence",
            "score": 8,
            "matched_terms": ["content:invoice"],
            "score_reasons": ["content:invoice +1"],
            "snippet": "Required by law to display VAT number.",
        },
        {
            "title": "Existing workaround for staff wording",
            "evidence_type": "workaround_evidence",
            "score": 14,
            "matched_terms": ["title:staff", "content:editable"],
            "score_reasons": ["title:staff +4", "evidence_type:workaround +3"],
            "snippet": "Use the editable text field.",
        },
    ]
    ctx = {"subject": "Client wants custom wording in staff cost note"}

    result = assess_kb_evidence_quality(entries, ticket_context=ctx)

    assert result["has_data"] is True
    assert result["overall_quality"] == "mixed"
    assert result["summary"]["has_legal_evidence"] is True
    assert result["summary"]["has_workaround_evidence"] is True
    assert result["summary"]["has_conflicting_evidence_types"] is True

    codes = _signal_codes(result)
    assert "mixed_legal_and_workaround" in codes
    assert "workaround_or_setting_available" in codes
    assert "unsupported_legal_context" in codes
    # No legal terms in subject → unsupported_legal_context should appear
    assert "legal_evidence_present" in codes

    # quality_score from max_score=14 → min(14/2, 10) = 7.0
    assert result["quality_score"] == 7.0
