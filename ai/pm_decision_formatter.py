"""PM decision formatter.

Two public functions:

  format_pm_decision_for_prompt(pm_decision) -> str
      Converts a PMDecision dict into a compact plain-text block that can be
      prepended to any AI prompt as an explicit constraint section.

  apply_pm_decision_output_guard(output, pm_decision) -> str
      Scans AI output for violations of PM decision constraints and appends
      warning markers.  Does NOT silently rewrite content — POs see the markers
      and can decide what to do.
"""
from __future__ import annotations

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Patterns that signal unwanted content in AI output ────────────────────────

_LEGAL_CITATION_PATTERNS = [
    r"\bArticle\s+\d",
    r"\bLaw of\b",
    r"\blegal requirement\b",
    r"\bmandatory by law\b",
    r"\brequired by law\b",
    r"\bloi\s+\w",               # French: "loi du …"
    r"\bobligat(?:ion|oire)\b",  # French: "obligation", "obligatoire"
    r"\bRGD\b",                  # Règlement Grand-Ducal
    r"\beCDF\b",
    r"\bLoi\s+modifi",
]

_PRD_HEADING_PATTERNS = [
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


# ── Public API ────────────────────────────────────────────────────────────────

def format_pm_decision_for_prompt(pm_decision: Optional[dict]) -> str:
    """Return a compact plain-text block for injection into an AI prompt.

    The block lists the concrete constraints and ends with explicit rules the
    model must follow.  Returns an empty string when *pm_decision* is falsy.
    """
    if not pm_decision:
        return ""

    def _b(v: object) -> str:
        return "true" if v else "false"

    lines = [
        "PM DECISION CONSTRAINTS (deterministic — apply without deviation):",
        f"- Decision:             {pm_decision.get('decision', 'needs_analysis')}",
        f"- Classification:       {pm_decision.get('classification', 'needs_analysis')}",
        f"- Complexity:           {pm_decision.get('complexity', 'needs_analysis')}",
        f"- Answer depth:         {pm_decision.get('answer_depth', 'short')}",
        f"- Max words:            {pm_decision.get('max_words', 250)}",
        f"- Needs PRD:            {_b(pm_decision.get('needs_prd', False))}",
        f"- Needs development:    {_b(pm_decision.get('needs_development', False))}",
        f"- Development type:     {pm_decision.get('development_type', 'unclear')}",
        f"- Legal status:         {pm_decision.get('legal_status', 'unclear')}",
        f"- Mention law:          {_b(pm_decision.get('should_mention_law', False))}",
        f"- Global change risk:   {pm_decision.get('global_change_risk', 'unclear')}",
        f"- Recommended action:   {pm_decision.get('recommended_action', 'needs_analysis')}",
    ]

    reason = (pm_decision.get("reason") or "").strip()
    if reason:
        lines.append(f"- Reason:               {reason[:200]}")

    lines += ["", "Rules for this response (non-negotiable):"]

    answer_depth = pm_decision.get("answer_depth", "short")
    max_words = int(pm_decision.get("max_words") or 250)
    if answer_depth == "short":
        lines.append(
            f"  * Answer depth is SHORT — keep the entire response concise (≤{max_words} words)."
        )

    if not pm_decision.get("needs_prd", False):
        lines.append(
            "  * needs_prd is false — do NOT produce PRD-style analysis, "
            "structured requirements, or multi-section specification documents."
        )

    if pm_decision.get("should_mention_law") is False:
        lines.append(
            "  * should_mention_law is false — do NOT cite law, regulation, "
            "article numbers, or imply any legal obligation."
        )

    global_risk = pm_decision.get("global_change_risk", "unclear")
    if global_risk == "high":
        lines.append(
            "  * global_change_risk is HIGH — do NOT recommend changing the "
            "system default globally for all clients."
        )

    rec_action = pm_decision.get("recommended_action", "")
    if rec_action == "make_editable":
        lines.append(
            "  * recommended_action is make_editable — propose making the "
            "field/text editable per-client instead of a global default change."
        )

    decision_val = pm_decision.get("decision", "")
    if decision_val == "refuse_global_change":
        lines.append(
            "  * decision is refuse_global_change — briefly explain why "
            "a global default change is not appropriate here."
        )

    return "\n".join(lines)


def apply_pm_decision_output_guard(output: str, pm_decision: Optional[dict]) -> str:
    """Check AI output against PM decision constraints; append warning markers.

    Warnings are appended (never silently rewritten) so the PO can review them.
    Returns the original output unchanged when no violations are found.
    """
    if not output or not pm_decision:
        return output

    warnings: list = []

    # ── Guard 1: word count ────────────────────────────────────────────────────
    max_words = int(pm_decision.get("max_words") or 0)
    answer_depth = pm_decision.get("answer_depth", "")
    if max_words and answer_depth == "short":
        word_count = len(output.split())
        if word_count > max_words * 1.5:  # 50 % tolerance before flagging
            warnings.append(
                f"[PM guard: output is {word_count} words; "
                f"recommended max is {max_words}. Manual review required.]"
            )

    # ── Guard 2: legal citation ────────────────────────────────────────────────
    # Only fire when should_mention_law is explicitly False (not just falsy default).
    if pm_decision.get("should_mention_law") is False:
        for pattern in _LEGAL_CITATION_PATTERNS:
            if re.search(pattern, output, re.IGNORECASE | re.MULTILINE):
                warnings.append(
                    "[PM guard: legal reference detected although "
                    "PM decision says should_mention_law=false.]"
                )
                break  # one warning per violation type is sufficient

    # ── Guard 3: PRD headings ──────────────────────────────────────────────────
    # Only fire when needs_prd is explicitly False.
    if pm_decision.get("needs_prd") is False:
        for pattern in _PRD_HEADING_PATTERNS:
            if re.search(pattern, output, re.MULTILINE):
                warnings.append(
                    "[PM guard: PRD-style output detected although "
                    "PM decision says needs_prd=false.]"
                )
                break

    if warnings:
        return output + "\n\n" + "\n".join(warnings)
    return output
