"""Unit tests for ai/safe_to_send_display.py — PR 29.

Tests cover:
- Return structure and types
- None / invalid input fallback
- Status-to-badge_label / severity mapping
- banner_title and banner_message correctness
- copy_warning rules
- top_reasons capping (max 3) and priority ordering
- Invalid reason entries are skipped
- Input dict is never mutated
- Acceptance scenarios from the PR spec
"""
from __future__ import annotations

import copy

import pytest

from ai.safe_to_send_display import build_safe_to_send_display


# ── Helpers ────────────────────────────────────────────────────────────────────

def _review(
    status="safe_to_send",
    risk_level="low",
    score=95,
    reasons=None,
    has_data=True,
):
    return {
        "has_data": has_data,
        "status": status,
        "risk_level": risk_level,
        "score": score,
        "reasons": reasons if reasons is not None else [],
        "summary": {"blocker_count": 0, "medium_count": 0},
    }


def _reason(severity="info", title="A reason", code="some_code", message="detail"):
    return {"code": code, "severity": severity, "title": title, "message": message}


# ── Basic structure ────────────────────────────────────────────────────────────


def test_returns_dict():
    assert isinstance(build_safe_to_send_display(_review()), dict)


def test_has_data_key():
    assert "has_data" in build_safe_to_send_display(_review())


def test_status_key():
    assert "status" in build_safe_to_send_display(_review())


def test_risk_level_key():
    assert "risk_level" in build_safe_to_send_display(_review())


def test_score_key():
    assert "score" in build_safe_to_send_display(_review())


def test_badge_label_key():
    assert "badge_label" in build_safe_to_send_display(_review())


def test_severity_key():
    assert "severity" in build_safe_to_send_display(_review())


def test_banner_title_key():
    assert "banner_title" in build_safe_to_send_display(_review())


def test_banner_message_key():
    assert "banner_message" in build_safe_to_send_display(_review())


def test_copy_warning_key():
    assert "copy_warning" in build_safe_to_send_display(_review())


def test_top_reasons_key():
    assert "top_reasons" in build_safe_to_send_display(_review())


def test_top_reasons_is_list():
    assert isinstance(build_safe_to_send_display(_review())["top_reasons"], list)


# ── None / invalid input fallback ─────────────────────────────────────────────


def test_none_input_has_data_false():
    assert build_safe_to_send_display(None)["has_data"] is False


def test_empty_dict_has_data_false():
    assert build_safe_to_send_display({})["has_data"] is False


def test_string_input_has_data_false():
    assert build_safe_to_send_display("bad")["has_data"] is False  # type: ignore


def test_has_data_false_review_returns_fallback():
    assert build_safe_to_send_display(_review(has_data=False))["has_data"] is False


def test_fallback_status_is_needs_review():
    result = build_safe_to_send_display(None)
    assert result["status"] == "needs_review"


def test_fallback_badge_label_is_needs_review():
    result = build_safe_to_send_display(None)
    assert result["badge_label"] == "Needs review"


def test_fallback_severity_is_warning():
    result = build_safe_to_send_display(None)
    assert result["severity"] == "warning"


def test_fallback_score_is_zero():
    assert build_safe_to_send_display(None)["score"] == 0


def test_fallback_copy_warning_not_empty():
    result = build_safe_to_send_display(None)
    assert result["copy_warning"]  # non-empty


def test_unknown_status_maps_to_needs_review():
    result = build_safe_to_send_display(_review(status="mystery_status"))
    assert result["status"] == "needs_review"
    assert result["badge_label"] == "Needs review"
    assert result["severity"] == "warning"


# ── badge_label and severity per status ───────────────────────────────────────


def test_safe_to_send_badge_label():
    assert build_safe_to_send_display(_review("safe_to_send"))["badge_label"] == "Safe to send"


def test_safe_to_send_severity():
    assert build_safe_to_send_display(_review("safe_to_send"))["severity"] == "success"


def test_needs_review_badge_label():
    assert build_safe_to_send_display(_review("needs_review"))["badge_label"] == "Needs review"


def test_needs_review_severity():
    assert build_safe_to_send_display(_review("needs_review"))["severity"] == "warning"


def test_do_not_send_badge_label():
    assert build_safe_to_send_display(_review("do_not_send"))["badge_label"] == "Do not send yet"


def test_do_not_send_severity():
    assert build_safe_to_send_display(_review("do_not_send"))["severity"] == "danger"


# ── banner_message ─────────────────────────────────────────────────────────────


def test_safe_to_send_banner_message():
    msg = build_safe_to_send_display(_review("safe_to_send"))["banner_message"]
    assert "No blocking review risks detected" in msg


def test_needs_review_banner_message():
    msg = build_safe_to_send_display(_review("needs_review"))["banner_message"]
    assert "warnings" in msg.lower() or "review" in msg.lower()


def test_do_not_send_banner_message():
    msg = build_safe_to_send_display(_review("do_not_send"))["banner_message"]
    assert "blocking" in msg.lower() or "do not send" in msg.lower()


# ── copy_warning ───────────────────────────────────────────────────────────────


def test_safe_to_send_copy_warning_empty():
    assert build_safe_to_send_display(_review("safe_to_send"))["copy_warning"] == ""


def test_needs_review_copy_warning_not_empty():
    result = build_safe_to_send_display(_review("needs_review"))
    assert result["copy_warning"]
    assert "warning" in result["copy_warning"].lower() or "review" in result["copy_warning"].lower()


def test_do_not_send_copy_warning_not_empty():
    result = build_safe_to_send_display(_review("do_not_send"))
    assert result["copy_warning"]
    assert "do not send" in result["copy_warning"].lower() or "blocking" in result["copy_warning"].lower()


# ── top_reasons ────────────────────────────────────────────────────────────────


def test_top_reasons_capped_at_3():
    reasons = [_reason("info", f"R{i}") for i in range(8)]
    result = build_safe_to_send_display(_review("needs_review", reasons=reasons))
    assert len(result["top_reasons"]) == 3


def test_top_reasons_empty_when_no_reasons():
    result = build_safe_to_send_display(_review("safe_to_send", reasons=[]))
    assert result["top_reasons"] == []


def test_top_reasons_prioritises_blocker_over_info():
    reasons = [
        _reason("info", "Info reason"),
        _reason("blocker", "Blocker reason"),
        _reason("info", "Another info"),
        _reason("info", "Yet another info"),
    ]
    result = build_safe_to_send_display(_review("do_not_send", reasons=reasons))
    assert result["top_reasons"][0]["severity"] == "blocker"


def test_top_reasons_prioritises_danger_over_warning():
    reasons = [
        _reason("warning", "Warn"),
        _reason("danger", "Danger"),
        _reason("info", "Info"),
    ]
    result = build_safe_to_send_display(_review("do_not_send", reasons=reasons))
    assert result["top_reasons"][0]["severity"] == "danger"


def test_top_reasons_prioritises_warning_over_info():
    reasons = [
        _reason("info", "Info A"),
        _reason("warning", "Warn A"),
        _reason("info", "Info B"),
        _reason("info", "Info C"),
    ]
    result = build_safe_to_send_display(_review("needs_review", reasons=reasons))
    assert result["top_reasons"][0]["severity"] == "warning"


def test_invalid_reason_entries_skipped():
    reasons = ["not a dict", None, 42, _reason("info", "Valid")]
    result = build_safe_to_send_display(_review("needs_review", reasons=reasons))
    assert all(isinstance(r, dict) for r in result["top_reasons"])


def test_non_list_reasons_handled():
    review = _review("needs_review")
    review["reasons"] = "bad"
    result = build_safe_to_send_display(review)
    assert isinstance(result["top_reasons"], list)


# ── Score passthrough ──────────────────────────────────────────────────────────


def test_score_passthrough():
    result = build_safe_to_send_display(_review(score=72))
    assert result["score"] == 72


def test_score_clamped_to_100():
    review = _review(score=150)
    result = build_safe_to_send_display(review)
    assert result["score"] == 100


def test_score_clamped_to_0():
    review = _review(score=-10)
    result = build_safe_to_send_display(review)
    assert result["score"] == 0


def test_score_invalid_defaults_to_0():
    review = _review()
    review["score"] = "bad"
    result = build_safe_to_send_display(review)
    assert result["score"] == 0


# ── Input mutation check ───────────────────────────────────────────────────────


def test_does_not_mutate_input():
    original = _review("needs_review", reasons=[_reason("warning", "Warn")])
    original_copy = copy.deepcopy(original)
    build_safe_to_send_display(original)
    assert original == original_copy


# ── has_data passthrough ───────────────────────────────────────────────────────


def test_has_data_true_for_valid_review():
    assert build_safe_to_send_display(_review("safe_to_send"))["has_data"] is True


# ── risk_level passthrough ────────────────────────────────────────────────────


def test_risk_level_passthrough_low():
    assert build_safe_to_send_display(_review("safe_to_send", risk_level="low"))["risk_level"] == "low"


def test_risk_level_passthrough_high():
    assert build_safe_to_send_display(_review("do_not_send", risk_level="high"))["risk_level"] == "high"


# ── Exception safety ───────────────────────────────────────────────────────────


def test_does_not_raise_on_none():
    result = build_safe_to_send_display(None)
    assert isinstance(result, dict)


def test_does_not_raise_on_garbage():
    result = build_safe_to_send_display({"status": object(), "has_data": True})  # type: ignore
    assert isinstance(result, dict)


# ── Acceptance scenarios from PR spec ─────────────────────────────────────────


def test_acceptance_do_not_send_scenario():
    """do_not_send review: badge=Do not send yet, copy_warning present, danger reasons first."""
    review = {
        "has_data": True,
        "status": "do_not_send",
        "risk_level": "high",
        "score": 40,
        "reasons": [
            {"code": "critical_qa_issue", "severity": "danger",
             "title": "Critical QA issue", "message": "Manual review required."},
            {"code": "mixed_kb_evidence", "severity": "warning",
             "title": "Mixed KB evidence", "message": "Legal and workaround evidence both present."},
        ],
    }
    result = build_safe_to_send_display(review)

    assert result["has_data"] is True
    assert result["badge_label"] == "Do not send yet"
    assert result["severity"] == "danger"
    assert "do not send" in result["banner_title"].lower() or "do not send" in result["banner_message"].lower()
    assert result["copy_warning"]
    assert len(result["top_reasons"]) == 2
    assert result["top_reasons"][0]["severity"] == "danger"
    assert result["score"] == 40


def test_acceptance_safe_to_send_scenario():
    """safe_to_send review: badge=Safe to send, copy_warning empty, success severity."""
    review = {
        "has_data": True,
        "status": "safe_to_send",
        "risk_level": "low",
        "score": 95,
        "reasons": [
            {"code": "safe_summary", "severity": "success",
             "title": "No blocking risks", "message": "Ready for review."},
        ],
    }
    result = build_safe_to_send_display(review)

    assert result["has_data"] is True
    assert result["badge_label"] == "Safe to send"
    assert result["severity"] == "success"
    assert "No blocking review risks detected" in result["banner_message"]
    assert result["copy_warning"] == ""
    assert result["score"] == 95
