"""Safe-to-send review — no LLM calls, no DB writes.

Public function
---------------
build_safe_to_send_review(
    pm_decision=None,
    pm_guard_warnings=None,
    existing_solution_review=None,
    kb_evidence_quality_review=None,
    kb_snapshot_diff_review=None,
    qa_issues=None,
    draft_text="",
) -> dict

Aggregates all review signals from upstream helpers into a single
safe-to-send assessment for a draft reply.

Returned structure::

    {
      "has_data": bool,
      "status": str,       # safe_to_send / needs_review / do_not_send
      "risk_level": str,   # low / medium / high
      "score": int,        # 0–100  (0 when has_data=False)
      "reasons": [
        {
          "code": str,
          "severity": str,   # blocker / medium / info
          "title": str,
          "message": str,
        },
        ...
      ],
      "summary": {
        "has_blockers": bool,
        "has_medium_issues": bool,
        "blocker_count": int,
        "medium_count": int,
        "info_count": int,
        "passed_checks": int,
      },
    }
"""
from __future__ import annotations

from typing import List, Optional

# ── Phrase lists for draft analysis ───────────────────────────────────────────

_HARD_BLOCKER_PHRASES = [
    "we will implement",
    "we will change globally",
    "we will create a jira",
    "this will be fixed",
]

_PRD_HEADINGS = [
    "## background",
    "## objective",
    "## requirements",
    "## acceptance criteria",
    "## user stories",
    "## technical spec",
    "## scope",
    "## out of scope",
]

_STRONG_DEV_PHRASES = [
    "we will deploy",
    "we will release",
    "we will push a fix",
    "fix will be pushed",
    "hotfix will be",
    "patch will be",
]

_SHORT_DRAFT_THRESHOLD = 40   # characters


# ── Core penalty table ─────────────────────────────────────────────────────────
# (penalty, is_blocker, code, title, message_template)

def _build_safe_to_send_review(
    pm_decision: Optional[dict],
    pm_guard_warnings: Optional[list],
    existing_solution_review: Optional[dict],
    kb_evidence_quality_review: Optional[dict],
    kb_snapshot_diff_review: Optional[dict],
    qa_issues: Optional[list],
    draft_text: str,
) -> dict:
    """Internal implementation — see module docstring."""
    reasons: List[dict] = []
    score = 100
    draft_lower = (draft_text or "").lower()
    has_draft = bool((draft_text or "").strip())

    # ── Helpers ────────────────────────────────────────────────────────────────

    def add_reason(
        code: str,
        severity: str,
        title: str,
        message: str,
    ) -> None:
        reasons.append(
            {
                "code": code,
                "severity": severity,
                "title": title,
                "message": message,
            }
        )

    def penalise(points: int) -> None:
        nonlocal score
        score = max(0, score - points)

    # ── 1. PM guard warnings ───────────────────────────────────────────────────

    pm_guard_list = pm_guard_warnings if isinstance(pm_guard_warnings, list) else []
    for warning in pm_guard_list:
        if not isinstance(warning, dict):
            continue
        severity_val = (warning.get("severity") or "").lower()
        category_val = (warning.get("category") or "").lower()
        warn_text = (warning.get("text") or warning.get("message") or "").lower()

        # Hard blockers
        if severity_val in ("high", "critical"):
            penalise(30)
            add_reason(
                "pm_guard_high_severity",
                "blocker",
                "PM Guard: high-severity warning",
                warning.get("text") or warning.get("message") or "High-severity PM guard warning detected.",
            )
        elif "legal_reference" in category_val or "legal" in category_val:
            penalise(30)
            add_reason(
                "pm_guard_legal_reference",
                "blocker",
                "PM Guard: legal reference detected",
                warning.get("text") or warning.get("message") or "Legal reference detected in draft.",
            )
        elif "prd" in category_val or "feature_request" in category_val or "feature request" in warn_text:
            penalise(30)
            add_reason(
                "pm_guard_prd_or_feature_request",
                "blocker",
                "PM Guard: PRD-style or feature-request language",
                warning.get("text") or warning.get("message") or "PRD-style or feature-request language detected.",
            )
        else:
            # Any other PM guard warning → medium
            penalise(10)
            add_reason(
                "pm_guard_warning",
                "medium",
                "PM Guard: warning present",
                warning.get("text") or warning.get("message") or "A PM guard warning was raised.",
            )

    # ── 2. PM decision signals ─────────────────────────────────────────────────

    pm_dec = pm_decision if isinstance(pm_decision, dict) else {}
    pm_type = (pm_dec.get("decision_type") or pm_dec.get("decision") or "").lower()
    needs_prd = pm_dec.get("needs_prd", False)

    # Hard blocker: strong dev-commitment phrases when decision is support_guidance
    if pm_type in ("support_guidance", "support") and has_draft:
        for phrase in _HARD_BLOCKER_PHRASES:
            if phrase in draft_lower:
                penalise(40)
                add_reason(
                    "draft_dev_commitment_phrase",
                    "blocker",
                    "Draft contains development-commitment language",
                    f'Draft contains "{phrase}" which implies a commitment to implement. '
                    "Remove or rephrase before sending.",
                )
                break  # one reason is enough

        # Strong dev phrases
        for phrase in _STRONG_DEV_PHRASES:
            if phrase in draft_lower:
                penalise(30)
                add_reason(
                    "draft_strong_dev_language",
                    "blocker",
                    "Draft contains strong development-commitment language",
                    f'Draft contains "{phrase}". Avoid making deployment/release commitments in support replies.',
                )
                break

    # Medium: PRD headings in draft when needs_prd is False
    if not needs_prd and has_draft:
        for heading in _PRD_HEADINGS:
            if heading in draft_lower:
                penalise(10)
                add_reason(
                    "draft_prd_heading_unexpected",
                    "medium",
                    "Draft contains PRD headings when no PRD is needed",
                    f'Draft contains the heading "{heading}" but this ticket does not require a PRD.',
                )
                break

    # ── 3. KB evidence quality ─────────────────────────────────────────────────

    kb_quality = kb_evidence_quality_review if isinstance(kb_evidence_quality_review, dict) else {}
    overall_quality = (kb_quality.get("overall_quality") or "none").lower()
    kb_signals = kb_quality.get("signals") or []
    if not isinstance(kb_signals, list):
        kb_signals = []
    kb_signal_codes = {
        (s.get("code") or "") for s in kb_signals if isinstance(s, dict)
    }

    # Hard blocker: mixed + unsupported_legal_context
    if overall_quality == "mixed" and "unsupported_legal_context" in kb_signal_codes:
        penalise(40)
        add_reason(
            "kb_mixed_unsupported_legal",
            "blocker",
            "KB evidence: mixed legal context with unsupported legal signals",
            "KB evidence contains conflicting legal signals in an unsupported legal context. "
            "Review carefully before sending.",
        )
    elif overall_quality == "weak":
        penalise(10)
        add_reason(
            "kb_quality_weak",
            "medium",
            "KB evidence quality is weak",
            "The KB evidence matched is low-scoring or generic. "
            "Verify the reply is accurate before sending.",
        )
    elif overall_quality == "mixed":
        penalise(10)
        add_reason(
            "kb_quality_mixed",
            "medium",
            "KB evidence quality is mixed",
            "KB evidence contains a mix of evidence types (e.g., legal and workaround). "
            "Ensure the response addresses all relevant aspects.",
        )

    # ── 4. KB snapshot diff ────────────────────────────────────────────────────

    kb_diff = kb_snapshot_diff_review if isinstance(kb_snapshot_diff_review, dict) else {}
    diff_comparisons = kb_diff.get("comparisons") or []
    if not isinstance(diff_comparisons, list):
        diff_comparisons = []

    for comp in diff_comparisons:
        if not isinstance(comp, dict):
            continue
        if comp.get("has_changes"):
            penalise(5)
            from_flow = comp.get("from_flow", "?")
            to_flow = comp.get("to_flow", "?")
            add_reason(
                "kb_snapshot_changed",
                "medium",
                f"KB evidence changed between {from_flow} and {to_flow}",
                f"KB entries shifted between the {from_flow} and {to_flow} flows. "
                "Check whether the final KB evidence still supports the draft reply.",
            )
            break  # one medium reason is enough for drift

    # ── 5. Existing solution ───────────────────────────────────────────────────

    ex_sol = existing_solution_review if isinstance(existing_solution_review, dict) else {}
    has_existing_sol = ex_sol.get("has_existing_solution", False)
    sol_mentioned = ex_sol.get("mentioned_in_draft", False)

    if has_existing_sol and not sol_mentioned and has_draft:
        penalise(10)
        add_reason(
            "existing_solution_not_mentioned",
            "medium",
            "Existing solution not mentioned in draft",
            "A known existing solution or workaround was found but does not appear to be "
            "referenced in the draft reply.",
        )

    # ── 6. QA issues ──────────────────────────────────────────────────────────

    qa = qa_issues if isinstance(qa_issues, list) else []
    for issue in qa:
        if not isinstance(issue, dict):
            continue
        issue_text = (
            (issue.get("text") or issue.get("message") or issue.get("description") or "")
        ).lower()
        if "critical" in issue_text or "failed" in issue_text or "manual review required" in issue_text:
            penalise(30)
            add_reason(
                "qa_critical_issue",
                "blocker",
                "QA issue requires manual review",
                issue.get("text") or issue.get("message") or issue.get("description") or
                "A critical QA issue was detected.",
            )
            break

    # ── 7. Draft quality ──────────────────────────────────────────────────────

    draft_stripped = (draft_text or "").strip()
    if not draft_stripped:
        penalise(15)
        add_reason(
            "draft_empty",
            "medium",
            "No draft reply available",
            "No draft reply has been generated yet. Generate a draft before reviewing.",
        )
    elif len(draft_stripped) < _SHORT_DRAFT_THRESHOLD:
        penalise(10)
        add_reason(
            "draft_too_short",
            "medium",
            "Draft reply is very short",
            f"The draft reply is only {len(draft_stripped)} characters. "
            "A complete, helpful reply is typically longer.",
        )

    # ── 8. Determine status and risk level ────────────────────────────────────

    has_blockers = any(r["severity"] == "blocker" for r in reasons)
    has_medium = any(r["severity"] == "medium" for r in reasons)

    if has_blockers or score < 50:
        status = "do_not_send"
        risk_level = "high"
    elif has_medium or score < 85:
        status = "needs_review"
        risk_level = "medium"
    else:
        status = "safe_to_send"
        risk_level = "low"

    blocker_count = sum(1 for r in reasons if r["severity"] == "blocker")
    medium_count = sum(1 for r in reasons if r["severity"] == "medium")
    info_count = sum(1 for r in reasons if r["severity"] == "info")

    # Passed checks = number of check categories that produced no reason
    _total_checks = 7
    _failed_checks = len(set(r["code"].split("_")[0] for r in reasons))
    passed_checks = max(0, _total_checks - _failed_checks)

    return {
        "has_data": True,
        "status": status,
        "risk_level": risk_level,
        "score": score,
        "reasons": reasons,
        "summary": {
            "has_blockers": has_blockers,
            "has_medium_issues": has_medium,
            "blocker_count": blocker_count,
            "medium_count": medium_count,
            "info_count": info_count,
            "passed_checks": passed_checks,
        },
    }


_EMPTY_RESULT: dict = {
    "has_data": False,
    "status": "needs_review",
    "risk_level": "medium",
    "score": 0,
    "reasons": [],
    "summary": {
        "has_blockers": False,
        "has_medium_issues": False,
        "blocker_count": 0,
        "medium_count": 0,
        "info_count": 0,
        "passed_checks": 0,
    },
}


def build_safe_to_send_review(
    pm_decision: Optional[dict] = None,
    pm_guard_warnings: Optional[list] = None,
    existing_solution_review: Optional[dict] = None,
    kb_evidence_quality_review: Optional[dict] = None,
    kb_snapshot_diff_review: Optional[dict] = None,
    qa_issues: Optional[list] = None,
    draft_text: str = "",
) -> dict:
    """Build a safe-to-send review from all available review signals.

    Parameters
    ----------
    pm_decision:
        Dict as returned by the PM decision classifier (may be None).
    pm_guard_warnings:
        List of warning dicts from ``collect_pm_guard_warnings_from_texts``.
    existing_solution_review:
        Dict from ``extract_existing_solution_from_pm_decision``.
    kb_evidence_quality_review:
        Dict from ``assess_kb_evidence_quality``.
    kb_snapshot_diff_review:
        Dict from ``build_kb_snapshot_diff_review``.
    qa_issues:
        List of QA issue dicts (may be None).
    draft_text:
        Raw draft reply text. Falls back to empty string.

    Returns
    -------
    dict
        Stable display dict. ``has_data`` is False when no useful inputs
        are present and no draft exists.  Never raises.
    """
    try:
        # Fallback: no inputs at all and no draft
        # Use `is not None` for list/dict inputs so empty list/dict counts as provided
        has_any_input = any([
            pm_decision is not None,
            pm_guard_warnings is not None,
            existing_solution_review is not None,
            kb_evidence_quality_review is not None,
            kb_snapshot_diff_review is not None,
            qa_issues is not None,
            bool((draft_text or "").strip()),
        ])
        if not has_any_input:
            return dict(_EMPTY_RESULT)

        return _build_safe_to_send_review(
            pm_decision=pm_decision,
            pm_guard_warnings=pm_guard_warnings,
            existing_solution_review=existing_solution_review,
            kb_evidence_quality_review=kb_evidence_quality_review,
            kb_snapshot_diff_review=kb_snapshot_diff_review,
            qa_issues=qa_issues,
            draft_text=draft_text,
        )
    except Exception:
        return dict(_EMPTY_RESULT)
