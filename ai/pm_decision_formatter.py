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

# Guard A: global default change phrases (risk when global_change_risk=high)
_GLOBAL_DEFAULT_PHRASES = [
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

# Guard B: editability / configurability phrases (expected when make_editable)
_EDITABLE_PHRASES = [
    "editable",
    "configurable",
    "configuration",
    "per-client",
    "client-specific",
    "make the text editable",
    "rendre le texte éditable",
    "configurable par client",
    "rendre ce champ",
    "champ modifiable",
    "personnalisable",
]

# Guard C: feature request framing (bad when development_type=bug_fix)
_FEATURE_REQUEST_PHRASES = [
    "feature request",
    "new feature",
    "enhancement request",
    "demande de fonctionnalité",
    "nouvelle fonctionnalité",
]

_BUG_FIX_PHRASES = [
    "bug",
    "defect",
    "fix",
    "anomalie",
    "correction",
    "bogue",
]

# Guard D: strong development language (bad when development_type=support_guidance)
_STRONG_DEV_PHRASES = [
    "create a jira",
    "créer un jira",
    "development required",
    "développement requis",
    "implement a change",
    "implémenter un changement",
    "build a new feature",
    "construire une nouvelle fonctionnalité",
    "requires development",
    "nécessite un développement",
]

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

    if rec_action == "explain_existing_setting":
        lines.append(
            "  * recommended_action is explain_existing_setting — "
            "an existing setting or configuration option already covers this request; "
            "explain it to the client without suggesting development."
        )

    if rec_action in ("explain_workaround", "explain_existing_setting"):
        lines.append(
            "  * No development is needed — the solution already exists; "
            "do NOT create a Jira or suggest any code change."
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

    # ── Guard A: global default change ────────────────────────────────────────
    # Fire when global_change_risk=high and output suggests a global default change.
    if pm_decision.get("global_change_risk") == "high":
        output_lower = output.lower()
        if any(phrase in output_lower for phrase in _GLOBAL_DEFAULT_PHRASES):
            warnings.append(
                "[PM guard: global default change suggested although global_change_risk=high.]"
            )

    # ── Guard B: make editable — editability not mentioned ────────────────────
    # Fire when recommended_action=make_editable but output skips editability language.
    if pm_decision.get("recommended_action") == "make_editable":
        output_lower = output.lower()
        if not any(phrase in output_lower for phrase in _EDITABLE_PHRASES):
            warnings.append(
                "[PM guard: recommended_action=make_editable but output does not "
                "mention editability/configurability.]"
            )

    # ── Guard C: bug framed as feature request ────────────────────────────────
    # Fire when development_type=bug_fix but output only uses feature-request language.
    if pm_decision.get("development_type") == "bug_fix":
        output_lower = output.lower()
        has_feature_framing = any(phrase in output_lower for phrase in _FEATURE_REQUEST_PHRASES)
        has_bug_framing = any(phrase in output_lower for phrase in _BUG_FIX_PHRASES)
        if has_feature_framing and not has_bug_framing:
            warnings.append(
                "[PM guard: bug_fix decision may have been framed as a feature request.]"
            )

    # ── Guard D: support guidance escalated to development ───────────────────
    # Fire when development_type=support_guidance but output calls for dev work.
    if pm_decision.get("development_type") == "support_guidance":
        output_lower = output.lower()
        if any(phrase in output_lower for phrase in _STRONG_DEV_PHRASES):
            warnings.append(
                "[PM guard: support guidance decision may have been escalated to development.]"
            )

    if warnings:
        return output + "\n\n" + "\n".join(warnings)
    return output


# ── Guard warning extraction helpers ─────────────────────────────────────────

_GUARD_MARKER_RE = re.compile(r"\[PM guard:[^\]]+\]", re.IGNORECASE)


def extract_pm_guard_warnings(output: str) -> list:
    """Return a list of all PM guard marker strings found in *output*.

    Returns [] when *output* is empty/None.  Does NOT modify *output*.
    """
    if not output:
        return []
    return _GUARD_MARKER_RE.findall(output)


def strip_pm_guard_warnings(output: str) -> str:
    """Return *output* with all PM guard marker lines removed.

    Cleans up trailing blank lines left behind by the removal.
    Does NOT change any other content.  Returns "" for empty/None input.
    """
    if not output:
        return output or ""
    cleaned = _GUARD_MARKER_RE.sub("", output)
    # Collapse runs of 3+ newlines to at most 2
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.rstrip()
