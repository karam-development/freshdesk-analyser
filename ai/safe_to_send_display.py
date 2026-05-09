"""Safe-to-send display helper — no LLM calls, no DB writes.

Public function
---------------
build_safe_to_send_display(review: dict | None) -> dict

Transforms a ``build_safe_to_send_review`` result into a stable display
dict suitable for the draft-area banner in ticket.html.

Returned structure::

    {
      "has_data": bool,
      "status": str,            # safe_to_send / needs_review / do_not_send
      "risk_level": str,        # low / medium / high
      "score": int,             # 0–100
      "badge_label": str,       # "Safe to send" / "Needs review" / "Do not send yet"
      "severity": str,          # success / warning / danger
      "banner_title": str,
      "banner_message": str,
      "copy_warning": str,      # empty for safe_to_send
      "top_reasons": list[dict] # at most 3; prioritised by severity
    }
"""
from __future__ import annotations

from typing import Optional

# ── Severity priority for sorting reasons ────────────────────────────────────

_SEVERITY_ORDER = {
    "blocker": 0,
    "danger":  1,
    "high":    2,
    "medium":  3,
    "warning": 4,
    "info":    5,
    "success": 6,
    "neutral": 7,
    "low":     8,
}

# ── Status → display mappings ────────────────────────────────────────────────

_BADGE_LABEL = {
    "safe_to_send": "Safe to send",
    "needs_review": "Needs review",
    "do_not_send":  "Do not send yet",
}

_SEVERITY = {
    "safe_to_send": "success",
    "needs_review": "warning",
    "do_not_send":  "danger",
}

_BANNER_TITLE = {
    "safe_to_send": "Draft looks good",
    "needs_review": "Review warnings present",
    "do_not_send":  "Do not send this draft",
}

_BANNER_MESSAGE = {
    "safe_to_send": "No blocking review risks detected.",
    "needs_review": "Review the warnings before sending this draft.",
    "do_not_send":  "Do not send this draft until the blocking issues are resolved.",
}

_COPY_WARNING = {
    "safe_to_send": "",
    "needs_review": (
        "This draft has review warnings. "
        "Please check the Safe to Send Review before copying."
    ),
    "do_not_send": (
        "This draft is marked Do not send yet. "
        "Resolve blocking issues before copying or sending."
    ),
}

_EMPTY_RESULT: dict = {
    "has_data": False,
    "status": "needs_review",
    "risk_level": "medium",
    "score": 0,
    "badge_label": "Needs review",
    "severity": "warning",
    "banner_title": "Safe-to-send review unavailable",
    "banner_message": "Review the draft manually before sending.",
    "copy_warning": "Safe-to-send review is unavailable. Please review manually.",
    "top_reasons": [],
}


def build_safe_to_send_display(review: Optional[dict] = None) -> dict:
    """Build a draft-area display dict from a safe_to_send_review result.

    Parameters
    ----------
    review:
        Dict as returned by ``build_safe_to_send_review``.
        May be None or invalid — handled defensively.

    Returns
    -------
    dict
        Stable display dict. Never raises.
    """
    try:
        if not review or not isinstance(review, dict):
            return dict(_EMPTY_RESULT)

        has_data = bool(review.get("has_data"))
        if not has_data:
            return dict(_EMPTY_RESULT)

        status = (review.get("status") or "needs_review").strip()
        if status not in _BADGE_LABEL:
            status = "needs_review"

        risk_level = (review.get("risk_level") or "medium").strip()
        score_raw = review.get("score")
        try:
            score = int(score_raw) if score_raw is not None else 0
            score = max(0, min(100, score))
        except (TypeError, ValueError):
            score = 0

        # Build top_reasons (prioritised, max 3)
        raw_reasons = review.get("reasons") or []
        if not isinstance(raw_reasons, list):
            raw_reasons = []

        valid_reasons = [r for r in raw_reasons if isinstance(r, dict)]
        sorted_reasons = sorted(
            valid_reasons,
            key=lambda r: _SEVERITY_ORDER.get(
                (r.get("severity") or "neutral").lower(), 99
            ),
        )
        top_reasons = sorted_reasons[:3]

        return {
            "has_data": True,
            "status": status,
            "risk_level": risk_level,
            "score": score,
            "badge_label": _BADGE_LABEL[status],
            "severity": _SEVERITY[status],
            "banner_title": _BANNER_TITLE[status],
            "banner_message": _BANNER_MESSAGE[status],
            "copy_warning": _COPY_WARNING[status],
            "top_reasons": top_reasons,
        }

    except Exception:
        return dict(_EMPTY_RESULT)
