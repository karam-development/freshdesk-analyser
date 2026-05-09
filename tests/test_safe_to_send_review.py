"""Unit tests for ai/safe_to_send_review.py — PR 28.

Tests cover:
- Return structure and types
- Empty / no-input fallback
- Status and risk_level derivation
- Hard-blocker signals
- Medium-issue signals
- Score arithmetic
- Draft quality checks
- KB evidence quality integration
- KB snapshot diff integration
- Existing solution integration
- QA issues integration
- PM guard integration
- Reason structure
- Exception safety
"""
from __future__ import annotations

import pytest

from ai.safe_to_send_review import build_safe_to_send_review


# ── Fixtures / helpers ─────────────────────────────────────────────────────────

def _good_pm_decision(decision_type="support_guidance", needs_prd=False):
    return {"decision_type": decision_type, "needs_prd": needs_prd}


def _pm_guard_warning(severity="low", category="general", text="minor issue"):
    return {"severity": severity, "category": category, "text": text}


def _kb_quality(overall_quality="strong", quality_score=8.0, signal_codes=None):
    signals = [{"code": c} for c in (signal_codes or [])]
    return {
        "has_data": True,
        "overall_quality": overall_quality,
        "quality_score": quality_score,
        "signals": signals,
        "summary": {"entry_count": 1},
    }


def _kb_diff(comparisons=None):
    return {
        "has_data": True,
        "comparisons": comparisons or [],
        "summary": {"comparison_count": len(comparisons or [])},
    }


def _diff_comparison(from_flow="ingest", to_flow="draft", has_changes=True):
    return {
        "from_flow": from_flow,
        "to_flow": to_flow,
        "has_changes": has_changes,
        "added_titles": ["new entry"],
        "removed_titles": [],
    }


def _existing_solution(has_existing=True, mentioned=True):
    return {
        "has_existing_solution": has_existing,
        "mentioned_in_draft": mentioned,
    }


# ── Basic structure ────────────────────────────────────────────────────────────


def test_returns_dict():
    result = build_safe_to_send_review()
    assert isinstance(result, dict)


def test_has_data_key_present():
    result = build_safe_to_send_review()
    assert "has_data" in result


def test_status_key_present():
    result = build_safe_to_send_review(draft_text="Hello this is a reply.")
    assert "status" in result


def test_risk_level_key_present():
    result = build_safe_to_send_review(draft_text="Hello this is a reply.")
    assert "risk_level" in result


def test_score_key_present():
    result = build_safe_to_send_review(draft_text="Hello this is a reply.")
    assert "score" in result


def test_reasons_key_is_list():
    result = build_safe_to_send_review(draft_text="Hello this is a reply.")
    assert isinstance(result["reasons"], list)


def test_summary_key_is_dict():
    result = build_safe_to_send_review(draft_text="Hello this is a reply.")
    assert isinstance(result["summary"], dict)


def test_summary_has_blocker_count():
    result = build_safe_to_send_review(draft_text="Hello.")
    assert "blocker_count" in result["summary"]


def test_summary_has_medium_count():
    result = build_safe_to_send_review(draft_text="Hello.")
    assert "medium_count" in result["summary"]


def test_summary_has_passed_checks():
    result = build_safe_to_send_review(draft_text="Hello this is a reply.")
    assert "passed_checks" in result["summary"]


# ── Empty / fallback ───────────────────────────────────────────────────────────


def test_no_inputs_has_data_false():
    result = build_safe_to_send_review()
    assert result["has_data"] is False


def test_no_inputs_status_needs_review():
    result = build_safe_to_send_review()
    assert result["status"] == "needs_review"


def test_no_inputs_score_zero():
    result = build_safe_to_send_review()
    assert result["score"] == 0


def test_no_inputs_risk_medium():
    result = build_safe_to_send_review()
    assert result["risk_level"] == "medium"


def test_draft_only_has_data_true():
    result = build_safe_to_send_review(draft_text="A reasonable draft reply to the user.")
    assert result["has_data"] is True


# ── Score arithmetic ───────────────────────────────────────────────────────────


def test_clean_inputs_score_100():
    """Good draft, no warnings, strong KB quality → score = 100."""
    result = build_safe_to_send_review(
        pm_decision=_good_pm_decision(),
        pm_guard_warnings=[],
        kb_evidence_quality_review=_kb_quality("strong"),
        kb_snapshot_diff_review=_kb_diff([]),
        existing_solution_review=_existing_solution(False, False),
        draft_text="Thank you for reaching out. Here is the answer to your question.",
    )
    assert result["score"] == 100


def test_score_integer():
    result = build_safe_to_send_review(draft_text="Hello this is a reply.")
    assert isinstance(result["score"], int)


def test_score_range_0_100():
    result = build_safe_to_send_review(
        pm_guard_warnings=[
            _pm_guard_warning("high", "general", "bad thing"),
            _pm_guard_warning("high", "general", "another bad thing"),
            _pm_guard_warning("high", "general", "yet another"),
            _pm_guard_warning("high", "general", "one more"),
        ],
        draft_text="x",
    )
    assert 0 <= result["score"] <= 100


# ── Status derivation ──────────────────────────────────────────────────────────


def test_clean_inputs_status_safe_to_send():
    result = build_safe_to_send_review(
        pm_decision=_good_pm_decision(),
        pm_guard_warnings=[],
        kb_evidence_quality_review=_kb_quality("strong"),
        kb_snapshot_diff_review=_kb_diff([]),
        draft_text="Thank you for reaching out. Here is the answer to your question.",
    )
    assert result["status"] == "safe_to_send"
    assert result["risk_level"] == "low"


def test_blocker_status_do_not_send():
    result = build_safe_to_send_review(
        pm_guard_warnings=[_pm_guard_warning("high", "general", "critical issue")],
        draft_text="We will implement this feature.",
    )
    assert result["status"] == "do_not_send"
    assert result["risk_level"] == "high"


def test_medium_issue_status_needs_review():
    result = build_safe_to_send_review(
        pm_guard_warnings=[_pm_guard_warning("low", "general", "minor")],
        draft_text="Thank you for your message. Here is a full and complete answer to help you.",
    )
    assert result["status"] == "needs_review"
    assert result["risk_level"] == "medium"


# ── PM guard: hard blockers ────────────────────────────────────────────────────


def test_pm_guard_high_severity_is_blocker():
    result = build_safe_to_send_review(
        pm_guard_warnings=[_pm_guard_warning("high", "general", "High risk issue")],
        draft_text="A decent draft reply.",
    )
    blockers = [r for r in result["reasons"] if r["severity"] == "blocker"]
    assert len(blockers) >= 1


def test_pm_guard_critical_severity_is_blocker():
    result = build_safe_to_send_review(
        pm_guard_warnings=[_pm_guard_warning("critical", "general", "Critical issue")],
        draft_text="A decent draft reply.",
    )
    blockers = [r for r in result["reasons"] if r["severity"] == "blocker"]
    assert len(blockers) >= 1


def test_pm_guard_legal_reference_is_blocker():
    result = build_safe_to_send_review(
        pm_guard_warnings=[_pm_guard_warning("low", "legal_reference", "Law mentioned")],
        draft_text="A decent draft reply.",
    )
    blockers = [r for r in result["reasons"] if r["severity"] == "blocker"]
    assert len(blockers) >= 1


def test_pm_guard_prd_category_is_blocker():
    result = build_safe_to_send_review(
        pm_guard_warnings=[_pm_guard_warning("low", "prd", "PRD-style language")],
        draft_text="A decent draft reply.",
    )
    blockers = [r for r in result["reasons"] if r["severity"] == "blocker"]
    assert len(blockers) >= 1


def test_pm_guard_feature_request_is_blocker():
    result = build_safe_to_send_review(
        pm_guard_warnings=[_pm_guard_warning("low", "feature_request", "feature request")],
        draft_text="A decent draft reply.",
    )
    blockers = [r for r in result["reasons"] if r["severity"] == "blocker"]
    assert len(blockers) >= 1


def test_pm_guard_low_severity_is_medium():
    result = build_safe_to_send_review(
        pm_guard_warnings=[_pm_guard_warning("low", "general", "minor note")],
        draft_text="Thank you for your message. Here is a full and complete answer to help you.",
    )
    mediums = [r for r in result["reasons"] if r["severity"] == "medium"]
    assert len(mediums) >= 1


# ── Draft commitment phrases ───────────────────────────────────────────────────


def test_draft_we_will_implement_is_blocker():
    result = build_safe_to_send_review(
        pm_decision=_good_pm_decision("support_guidance"),
        draft_text="We will implement this feature for you.",
    )
    blockers = [r for r in result["reasons"] if r["severity"] == "blocker"]
    assert any("draft_dev_commitment_phrase" in r["code"] for r in blockers)


def test_draft_we_will_change_globally_is_blocker():
    result = build_safe_to_send_review(
        pm_decision=_good_pm_decision("support_guidance"),
        draft_text="We will change globally the settings.",
    )
    blockers = [r for r in result["reasons"] if r["severity"] == "blocker"]
    assert any("draft_dev_commitment_phrase" in r["code"] for r in blockers)


def test_draft_we_will_create_a_jira_is_blocker():
    result = build_safe_to_send_review(
        pm_decision=_good_pm_decision("support_guidance"),
        draft_text="We will create a jira ticket to track this.",
    )
    blockers = [r for r in result["reasons"] if r["severity"] == "blocker"]
    assert any("draft_dev_commitment_phrase" in r["code"] for r in blockers)


def test_draft_this_will_be_fixed_is_blocker():
    result = build_safe_to_send_review(
        pm_decision=_good_pm_decision("support_guidance"),
        draft_text="This will be fixed in the next release.",
    )
    blockers = [r for r in result["reasons"] if r["severity"] == "blocker"]
    assert any("draft_dev_commitment_phrase" in r["code"] for r in blockers)


def test_commitment_phrase_not_flagged_for_non_support_decision():
    """If decision is not support_guidance, commitment phrases are not flagged."""
    result = build_safe_to_send_review(
        pm_decision=_good_pm_decision("prd"),
        draft_text="We will implement this feature for you.",
    )
    codes = [r["code"] for r in result["reasons"]]
    assert "draft_dev_commitment_phrase" not in codes


# ── PRD headings ───────────────────────────────────────────────────────────────


def test_prd_heading_medium_when_no_prd_needed():
    result = build_safe_to_send_review(
        pm_decision=_good_pm_decision(needs_prd=False),
        draft_text="## Background\nSome content here for review.",
    )
    mediums = [r for r in result["reasons"] if r["severity"] == "medium"]
    assert any("prd_heading" in r["code"] for r in mediums)


def test_prd_heading_not_flagged_when_prd_needed():
    result = build_safe_to_send_review(
        pm_decision=_good_pm_decision(needs_prd=True),
        draft_text="## Background\nSome content here for review.",
    )
    codes = [r["code"] for r in result["reasons"]]
    assert "draft_prd_heading_unexpected" not in codes


# ── KB evidence quality ────────────────────────────────────────────────────────


def test_kb_quality_weak_is_medium():
    result = build_safe_to_send_review(
        kb_evidence_quality_review=_kb_quality("weak"),
        draft_text="A decent draft reply with good content.",
    )
    mediums = [r for r in result["reasons"] if r["severity"] == "medium"]
    assert any("kb_quality_weak" in r["code"] for r in mediums)


def test_kb_quality_mixed_is_medium():
    result = build_safe_to_send_review(
        kb_evidence_quality_review=_kb_quality("mixed"),
        draft_text="A decent draft reply with good content.",
    )
    mediums = [r for r in result["reasons"] if r["severity"] == "medium"]
    assert any("kb_quality_mixed" in r["code"] for r in mediums)


def test_kb_mixed_unsupported_legal_is_blocker():
    result = build_safe_to_send_review(
        kb_evidence_quality_review=_kb_quality(
            "mixed", signal_codes=["unsupported_legal_context"]
        ),
        draft_text="A decent draft reply with good content.",
    )
    blockers = [r for r in result["reasons"] if r["severity"] == "blocker"]
    assert any("kb_mixed_unsupported_legal" in r["code"] for r in blockers)


def test_kb_quality_strong_no_kb_reason():
    result = build_safe_to_send_review(
        kb_evidence_quality_review=_kb_quality("strong"),
        draft_text="A decent draft reply with good content.",
    )
    kb_reasons = [r for r in result["reasons"] if r["code"].startswith("kb_quality")]
    assert len(kb_reasons) == 0


# ── KB snapshot diff ───────────────────────────────────────────────────────────


def test_kb_diff_changed_is_medium():
    result = build_safe_to_send_review(
        kb_snapshot_diff_review=_kb_diff([_diff_comparison(has_changes=True)]),
        draft_text="A decent draft reply with good content.",
    )
    mediums = [r for r in result["reasons"] if r["severity"] == "medium"]
    assert any("kb_snapshot_changed" in r["code"] for r in mediums)


def test_kb_diff_no_changes_no_reason():
    result = build_safe_to_send_review(
        kb_snapshot_diff_review=_kb_diff([_diff_comparison(has_changes=False)]),
        draft_text="A decent draft reply with good content.",
    )
    kb_reasons = [r for r in result["reasons"] if "kb_snapshot" in r["code"]]
    assert len(kb_reasons) == 0


def test_kb_diff_only_one_medium_reason_for_multiple_changed_comparisons():
    """Multiple changed comparisons still produce at most one medium reason for diff."""
    result = build_safe_to_send_review(
        kb_snapshot_diff_review=_kb_diff([
            _diff_comparison("ingest", "draft", True),
            _diff_comparison("draft", "regeneration", True),
        ]),
        draft_text="A decent draft reply with good content.",
    )
    kb_reasons = [r for r in result["reasons"] if "kb_snapshot" in r["code"]]
    assert len(kb_reasons) == 1


# ── Existing solution ──────────────────────────────────────────────────────────


def test_existing_solution_not_mentioned_is_medium():
    result = build_safe_to_send_review(
        existing_solution_review=_existing_solution(has_existing=True, mentioned=False),
        draft_text="A decent draft reply with good content.",
    )
    mediums = [r for r in result["reasons"] if r["severity"] == "medium"]
    assert any("existing_solution_not_mentioned" in r["code"] for r in mediums)


def test_existing_solution_mentioned_no_reason():
    result = build_safe_to_send_review(
        existing_solution_review=_existing_solution(has_existing=True, mentioned=True),
        draft_text="A decent draft reply with good content.",
    )
    codes = [r["code"] for r in result["reasons"]]
    assert "existing_solution_not_mentioned" not in codes


def test_no_existing_solution_no_reason():
    result = build_safe_to_send_review(
        existing_solution_review=_existing_solution(has_existing=False, mentioned=False),
        draft_text="A decent draft reply with good content.",
    )
    codes = [r["code"] for r in result["reasons"]]
    assert "existing_solution_not_mentioned" not in codes


# ── QA issues ─────────────────────────────────────────────────────────────────


def test_qa_critical_issue_is_blocker():
    result = build_safe_to_send_review(
        qa_issues=[{"text": "critical error detected"}],
        draft_text="A decent draft reply.",
    )
    blockers = [r for r in result["reasons"] if r["severity"] == "blocker"]
    assert any("qa_critical" in r["code"] for r in blockers)


def test_qa_failed_issue_is_blocker():
    result = build_safe_to_send_review(
        qa_issues=[{"text": "check failed in review"}],
        draft_text="A decent draft reply.",
    )
    blockers = [r for r in result["reasons"] if r["severity"] == "blocker"]
    assert any("qa_critical" in r["code"] for r in blockers)


def test_qa_manual_review_required_is_blocker():
    result = build_safe_to_send_review(
        qa_issues=[{"text": "manual review required for this item"}],
        draft_text="A decent draft reply.",
    )
    blockers = [r for r in result["reasons"] if r["severity"] == "blocker"]
    assert any("qa_critical" in r["code"] for r in blockers)


def test_qa_non_critical_no_blocker():
    result = build_safe_to_send_review(
        qa_issues=[{"text": "minor note about formatting"}],
        draft_text="A decent draft reply with good content here.",
    )
    blockers = [r for r in result["reasons"] if r["severity"] == "blocker"]
    assert len(blockers) == 0


# ── Draft quality ──────────────────────────────────────────────────────────────


def test_empty_draft_is_medium():
    result = build_safe_to_send_review(draft_text="")
    assert result["has_data"] is False  # no inputs at all → fallback


def test_whitespace_only_draft_is_medium():
    result = build_safe_to_send_review(
        pm_guard_warnings=[],
        draft_text="   ",
    )
    # has_data should still be True because pm_guard_warnings provided
    assert result["has_data"] is True
    mediums = [r for r in result["reasons"] if r["severity"] == "medium"]
    assert any("draft_empty" in r["code"] for r in mediums)


def test_short_draft_is_medium():
    result = build_safe_to_send_review(draft_text="Hi.")
    assert result["has_data"] is True
    mediums = [r for r in result["reasons"] if r["severity"] == "medium"]
    assert any("draft_too_short" in r["code"] for r in mediums)


def test_adequate_draft_no_length_reason():
    draft = "Thank you for your message. Here is the answer to your question with full detail."
    result = build_safe_to_send_review(draft_text=draft)
    codes = [r["code"] for r in result["reasons"]]
    assert "draft_empty" not in codes
    assert "draft_too_short" not in codes


# ── Reason structure ───────────────────────────────────────────────────────────


def test_reason_has_code_key():
    result = build_safe_to_send_review(
        pm_guard_warnings=[_pm_guard_warning("high", "general", "issue")],
        draft_text="A decent draft reply.",
    )
    for r in result["reasons"]:
        assert "code" in r


def test_reason_has_severity_key():
    result = build_safe_to_send_review(
        pm_guard_warnings=[_pm_guard_warning("high", "general", "issue")],
        draft_text="A decent draft reply.",
    )
    for r in result["reasons"]:
        assert "severity" in r


def test_reason_has_title_key():
    result = build_safe_to_send_review(
        pm_guard_warnings=[_pm_guard_warning("high", "general", "issue")],
        draft_text="A decent draft reply.",
    )
    for r in result["reasons"]:
        assert "title" in r


def test_reason_has_message_key():
    result = build_safe_to_send_review(
        pm_guard_warnings=[_pm_guard_warning("high", "general", "issue")],
        draft_text="A decent draft reply.",
    )
    for r in result["reasons"]:
        assert "message" in r


def test_reason_severity_valid_values():
    result = build_safe_to_send_review(
        pm_guard_warnings=[_pm_guard_warning("high", "general", "issue")],
        draft_text="A decent draft reply.",
    )
    valid = {"blocker", "medium", "info"}
    for r in result["reasons"]:
        assert r["severity"] in valid


# ── Summary counts match reasons ──────────────────────────────────────────────


def test_summary_blocker_count_matches_reasons():
    result = build_safe_to_send_review(
        pm_guard_warnings=[_pm_guard_warning("high", "general", "issue")],
        draft_text="A decent draft reply.",
    )
    expected = sum(1 for r in result["reasons"] if r["severity"] == "blocker")
    assert result["summary"]["blocker_count"] == expected


def test_summary_medium_count_matches_reasons():
    result = build_safe_to_send_review(
        pm_guard_warnings=[_pm_guard_warning("low", "general", "minor issue")],
        draft_text="Thank you for your message. Here is a full and complete answer.",
    )
    expected = sum(1 for r in result["reasons"] if r["severity"] == "medium")
    assert result["summary"]["medium_count"] == expected


def test_summary_has_blockers_true_when_blockers():
    result = build_safe_to_send_review(
        pm_guard_warnings=[_pm_guard_warning("high", "general", "critical")],
        draft_text="A decent draft reply.",
    )
    assert result["summary"]["has_blockers"] is True


def test_summary_has_blockers_false_when_no_blockers():
    result = build_safe_to_send_review(
        draft_text="Thank you for your message. Here is a full and complete helpful answer.",
    )
    assert result["summary"]["has_blockers"] is False


# ── Exception safety ───────────────────────────────────────────────────────────


def test_none_inputs_does_not_crash():
    result = build_safe_to_send_review(
        pm_decision=None,
        pm_guard_warnings=None,
        existing_solution_review=None,
        kb_evidence_quality_review=None,
        kb_snapshot_diff_review=None,
        qa_issues=None,
        draft_text=None,
    )
    assert isinstance(result, dict)
    assert "has_data" in result


def test_invalid_pm_guard_warnings_type_does_not_crash():
    result = build_safe_to_send_review(
        pm_guard_warnings="not a list",
        draft_text="A decent draft reply.",
    )
    assert isinstance(result, dict)


def test_invalid_kb_diff_type_does_not_crash():
    result = build_safe_to_send_review(
        kb_snapshot_diff_review="bad",
        draft_text="A decent draft reply.",
    )
    assert isinstance(result, dict)


def test_pm_guard_non_dict_entries_skipped():
    result = build_safe_to_send_review(
        pm_guard_warnings=["not a dict", None, 42],
        draft_text="A decent draft reply.",
    )
    assert isinstance(result, dict)
    # No crashes — non-dict entries are skipped
