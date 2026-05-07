"""PM guard persistence helpers.

Two public functions:

  apply_pm_guard_and_collect(output, pm_decision) -> tuple[str, list[dict]]
      Apply the PM output guard to *output*, then collect and categorize any
      PM guard markers found in the result.
      Safe: returns (original_output, []) when pm_decision is empty or guard fails.

  merge_pm_guard_warnings_into_qa_issues(existing_qa_issues, guard_warnings) -> str
      Merge a list of categorised PM guard warning dicts into the qa_issues
      JSON field, deduplicating by raw marker string.
      Safe: never raises; returns valid JSON even on malformed input.
"""
from __future__ import annotations

import json
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)


def apply_pm_guard_and_collect(
    output: str,
    pm_decision: dict,
) -> Tuple[str, List[dict]]:
    """Apply the PM output guard and collect any resulting warnings.

    Parameters
    ----------
    output:
        The draft text to guard.
    pm_decision:
        The PMDecision dict.  Empty/None → output returned unchanged, [] warnings.

    Returns
    -------
    tuple[str, list[dict]]
        (guarded_output, categorised_warning_dicts)
        On any error the original *output* and [] are returned.
    """
    if not pm_decision or not output:
        return output, []

    try:
        from ai.pm_decision_formatter import apply_pm_decision_output_guard
        from ai.pm_guard_review import collect_pm_guard_warnings_from_texts

        guarded = apply_pm_decision_output_guard(output, pm_decision)
        warnings = collect_pm_guard_warnings_from_texts(guarded)
        return guarded, warnings
    except Exception as exc:
        logger.warning("apply_pm_guard_and_collect failed: %s", exc)
        return output, []


def merge_pm_guard_warnings_into_qa_issues(
    existing_qa_issues,
    guard_warnings: List[dict],
) -> str:
    """Merge PM guard warning dicts into the qa_issues JSON field.

    Parameters
    ----------
    existing_qa_issues:
        Current value of the qa_issues DB column.  May be a JSON string, a
        Python list, an empty string, None, or invalid JSON.
    guard_warnings:
        List of categorised warning dicts (each must have a "raw" key).

    Returns
    -------
    str
        A JSON-encoded list (≤ 10 items), deduped by raw marker string.
        Never raises.
    """
    try:
        # ── Parse existing ────────────────────────────────────────────────────
        if isinstance(existing_qa_issues, list):
            existing: list = list(existing_qa_issues)
        elif isinstance(existing_qa_issues, str) and existing_qa_issues.strip():
            try:
                parsed = json.loads(existing_qa_issues)
                existing = parsed if isinstance(parsed, list) else []
            except Exception:
                existing = []
        else:
            existing = []

        # ── Extract raw markers from new warnings ─────────────────────────────
        new_items: List[str] = []
        for w in (guard_warnings or []):
            raw = (w.get("raw") or "").strip()
            if raw and raw not in existing and raw not in new_items:
                new_items.append(raw)

        # ── Deduplicate preserving order ──────────────────────────────────────
        combined = existing + new_items
        seen: set = set()
        deduped: list = []
        for item in combined:
            if item not in seen:
                seen.add(item)
                deduped.append(item)

        return json.dumps(deduped[:10])
    except Exception as exc:
        logger.warning("merge_pm_guard_warnings_into_qa_issues failed: %s", exc)
        return json.dumps([])
