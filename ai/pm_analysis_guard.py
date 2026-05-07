"""PM analysis output guard.

Public function:

  apply_pm_analysis_guard(output, pm_decision) -> tuple[str, list[str]]
      Scan analysis output for PM decision constraint violations and append
      warning markers.  Warning-only — never silently rewrites content.
      Returns (guarded_output, raw_warning_strings).
      Returns (original_output, []) when no violations are found or inputs empty.
"""
from __future__ import annotations

import re
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Phrase / pattern lists (shared with pm_decision_formatter conventions) ────

_PRD_HEADING_PATTERNS: List[str] = [
    r"^#{1,4}\s+\w",
    r"^##\s",
    r"\bObjective:\s",
    r"\bUser Stor(?:y|ies):\s",
    r"\bAcceptance Criteria:\s",
    r"\bDefinition of Done:\s",
    r"\bOut of Scope:\s",
    r"\bStakeholders?:\s",
    r"\bFunctional Requirements?:\s",
    r"\bNon-Functional Requirements?:\s",
    r"\bTimeline:\s",
    r"\bMilestones?:\s",
]

_LEGAL_CITATION_PATTERNS: List[str] = [
    r"\bArticle\s+\d",
    r"\bLaw of\b",
    r"\blegal requirement\b",
    r"\bmandatory by law\b",
    r"\brequired by law\b",
    r"\bloi\s+\w",
    r"\bobligat(?:ion|oire)\b",
    r"\bRGD\b",
    r"\beCDF\b",
    r"\bLoi\s+modifi",
]

_GLOBAL_DEFAULT_PHRASES: List[str] = [
    "change the default globally",
    "changing the default globally",
    "update the default wording",
    "change this for all clients",
    "global default change",
    "change the standard wording",
    "changing the standard wording",
    "default globally",
    "modifier le libellé par défaut pour tous",
    "changer le défaut global",
    "changer le libellé standard",
]

_EDITABLE_PHRASES: List[str] = [
    "editable",
    "configurable",
    "configuration",
    "per-client",
    "client-specific",
    "per client",
    "make the text editable",
    "rendre le texte éditable",
    "configurable par client",
    "personnalisable",
    "champ modifiable",
]


def apply_pm_analysis_guard(
    output: str,
    pm_decision: Optional[dict],
) -> Tuple[str, List[str]]:
    """Scan analysis output for PM decision violations; append warning markers.

    Parameters
    ----------
    output:
        The analysis text to scan.
    pm_decision:
        The PMDecision dict.  Empty/None → (output, []) returned immediately.

    Returns
    -------
    tuple[str, list[str]]
        (guarded_output, raw_warning_strings).
        *guarded_output* has warning markers appended when violations exist.
        The raw list is empty when no violations are found.
        Never raises.
    """
    if not output or not pm_decision:
        return output, []

    warnings: List[str] = []

    # ── Guard 1: PRD-style headings ───────────────────────────────────────────
    if pm_decision.get("needs_prd") is False:
        for pattern in _PRD_HEADING_PATTERNS:
            if re.search(pattern, output, re.MULTILINE | re.IGNORECASE):
                warnings.append(
                    "[PM analysis guard: PRD-style analysis detected although needs_prd=false.]"
                )
                break

    # ── Guard 2: legal citation ───────────────────────────────────────────────
    if pm_decision.get("should_mention_law") is False:
        for pattern in _LEGAL_CITATION_PATTERNS:
            if re.search(pattern, output, re.IGNORECASE | re.MULTILINE):
                warnings.append(
                    "[PM analysis guard: legal reference detected although should_mention_law=false.]"
                )
                break

    # ── Guard 3: global default change ───────────────────────────────────────
    if pm_decision.get("global_change_risk") == "high":
        output_lower = output.lower()
        if any(phrase in output_lower for phrase in _GLOBAL_DEFAULT_PHRASES):
            warnings.append(
                "[PM analysis guard: global default change suggested although global_change_risk=high.]"
            )

    # ── Guard 4: make_editable — editability not mentioned ───────────────────
    if pm_decision.get("recommended_action") == "make_editable":
        output_lower = output.lower()
        if not any(phrase in output_lower for phrase in _EDITABLE_PHRASES):
            warnings.append(
                "[PM analysis guard: make_editable decision but analysis does not "
                "mention editability/configurability.]"
            )

    # ── Guard 5: output too long for short answer_depth ──────────────────────
    answer_depth = pm_decision.get("answer_depth", "")
    max_words = int(pm_decision.get("max_words") or 0)
    if answer_depth == "short" and max_words:
        word_count = len(output.split())
        if word_count > max_words * 2:
            warnings.append(
                "[PM analysis guard: analysis is longer than recommended for answer_depth=short.]"
            )

    if warnings:
        return output + "\n\n" + "\n".join(warnings), warnings
    return output, []
