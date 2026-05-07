"""PM guard display helpers.

Two public functions:

  get_clean_draft_for_display(text: str) -> str
      Return a copy of *text* with all PM guard marker lines removed,
      suitable for display and copy.  Does NOT modify the stored value.

  has_pm_guard_warnings(text: str) -> bool
      Return True when *text* contains at least one PM guard marker.
"""
from __future__ import annotations

from ai.pm_decision_formatter import extract_pm_guard_warnings, strip_pm_guard_warnings


def get_clean_draft_for_display(text: str) -> str:
    """Return *text* with PM guard markers stripped, safe for display/copy.

    Returns "" for empty/None input.  Does NOT mutate the original string.
    """
    if not text:
        return ""
    return strip_pm_guard_warnings(text)


def has_pm_guard_warnings(text: str) -> bool:
    """Return True when *text* contains at least one [PM guard: …] marker."""
    if not text:
        return False
    return len(extract_pm_guard_warnings(text)) > 0
