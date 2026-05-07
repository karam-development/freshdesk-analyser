"""PM guard warning categorizer.

Three public functions:

  categorize_pm_guard_warning(warning: str) -> dict
      Map a single raw PM guard marker string to a structured dict with:
        code, severity, title, message, raw

  categorize_pm_guard_warnings(warnings: list[str]) -> list[dict]
      Categorize a list of raw markers; returns list of dicts.

  collect_pm_guard_warnings_from_texts(*texts) -> list[dict]
      Extract, deduplicate, and categorize PM guard markers from any number
      of text values.  Defensive against None/empty inputs.

Allowed codes:
  output_too_long | legal_reference_blocked | prd_style_blocked |
  global_default_change_blocked | editability_missing |
  bug_framed_as_feature | support_escalated_to_dev | unknown

Severity:
  high   — legal_reference_blocked, global_default_change_blocked,
            bug_framed_as_feature
  medium — support_escalated_to_dev, editability_missing, prd_style_blocked
  low    — output_too_long, unknown
"""
from __future__ import annotations

from typing import List

# ── Category rules (ordered — first substring match wins) ────────────────────
# Each entry: (substring_to_match, code, severity, title, message)

_RULES: list = [
    (
        "legal reference detected",
        "legal_reference_blocked",
        "high",
        "Legal reference blocked",
        "The AI cited law, article numbers, or legal obligations although "
        "should_mention_law=false.",
    ),
    (
        "global default change suggested",
        "global_default_change_blocked",
        "high",
        "Global default change blocked",
        "The AI proposed changing the global default although "
        "global_change_risk=high.",
    ),
    (
        "bug_fix decision may have been framed as a feature request",
        "bug_framed_as_feature",
        "high",
        "Bug framed as feature request",
        "The AI described a bug fix as a feature request or enhancement.",
    ),
    (
        "support guidance decision may have been escalated to development",
        "support_escalated_to_dev",
        "medium",
        "Support guidance escalated to development",
        "The AI escalated a support guidance ticket to a development request.",
    ),
    (
        "recommended_action=make_editable but output does not mention",
        "editability_missing",
        "medium",
        "Editability not mentioned",
        "The AI did not mention editability or configurability although "
        "recommended_action=make_editable.",
    ),
    (
        "prd-style output detected",
        "prd_style_blocked",
        "medium",
        "PRD-style output blocked",
        "The AI generated PRD-style headings although needs_prd=false.",
    ),
    (
        "words; recommended max",
        "output_too_long",
        "low",
        "Output too long",
        "The AI response exceeded the recommended word count.",
    ),
]


def categorize_pm_guard_warning(warning: str) -> dict:
    """Categorize a single raw PM guard marker string.

    Returns a dict with keys: code, severity, title, message, raw.
    Falls back to code='unknown' / severity='low' for unrecognised patterns.
    """
    if not warning:
        return {
            "code": "unknown",
            "severity": "low",
            "title": "Unknown guard warning",
            "message": "",
            "raw": warning or "",
        }

    w_lower = warning.lower()
    for substring, code, severity, title, message in _RULES:
        if substring.lower() in w_lower:
            return {
                "code": code,
                "severity": severity,
                "title": title,
                "message": message,
                "raw": warning,
            }

    return {
        "code": "unknown",
        "severity": "low",
        "title": "Unknown guard warning",
        "message": warning,
        "raw": warning,
    }


def categorize_pm_guard_warnings(warnings: List[str]) -> List[dict]:
    """Categorize a list of raw PM guard markers.

    Skips empty/None items.  Returns an empty list for empty input.
    """
    if not warnings:
        return []
    return [categorize_pm_guard_warning(w) for w in warnings if w]


def collect_pm_guard_warnings_from_texts(*texts) -> List[dict]:
    """Extract, deduplicate, and categorize PM guard markers from multiple texts.

    Accepts any number of positional string arguments.  None and empty values
    are silently skipped.  Duplicate raw markers across texts are collapsed to
    a single entry.  Returns a list of categorised warning dicts.
    """
    from ai.pm_decision_formatter import extract_pm_guard_warnings

    seen: set = set()
    raw: List[str] = []
    for text in texts:
        for marker in extract_pm_guard_warnings(text or ""):
            if marker not in seen:
                seen.add(marker)
                raw.append(marker)
    return categorize_pm_guard_warnings(raw)
