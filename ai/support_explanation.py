"""Support explanation context builder.

Public function:

  build_support_explanation_context(pm_decision, existing_solution, kb_evidence) -> str
      Returns an instruction block for injection into draft generation prompts when the
      PM decision indicates the ticket is a support/guidance/explanation case (not a
      development request, not a hard refuse).

      Returns "" when not applicable.  Never raises.  No LLM calls, no DB writes.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


# ── Decision / classification values that trigger support explanation mode ─────

_TRIGGER_DECISIONS = frozenset({
    "explain_workaround",
    "support_guidance",
    "make_editable",
    "reuse_existing_pattern",
})

_TRIGGER_CLASSIFICATIONS = frozenset({
    "how_to",
    "client_preference",
    "expected_behaviour",
})


def _is_support_explanation_ticket(pm_decision: Optional[Dict[str, Any]]) -> bool:
    """Return True when the PM decision indicates a support/explanation case."""
    if not pm_decision or not isinstance(pm_decision, dict):
        return False

    decision = (pm_decision.get("decision") or "").strip().lower()
    classification = (pm_decision.get("classification") or "").strip().lower()

    # Explicit decision match
    if decision in _TRIGGER_DECISIONS:
        return True

    # Classification match
    if classification in _TRIGGER_CLASSIFICATIONS:
        return True

    # Tickets not requiring development and not a hard refuse are guidance territory
    needs_development = pm_decision.get("needs_development", True)
    if needs_development is False and decision not in (
        "refuse_global_change",
        "feature_request",
    ):
        return True

    return False


def build_support_explanation_context(
    pm_decision: Optional[Dict[str, Any]] = None,
    existing_solution: Optional[Dict[str, Any]] = None,
    kb_evidence: Optional[List[Any]] = None,
) -> str:
    """Build a support-explanation instruction block for draft prompt injection.

    Activates when:
    - PM decision is ``explain_workaround``, ``support_guidance``, ``make_editable``,
      or ``reuse_existing_pattern``; OR
    - Classification is ``how_to``, ``client_preference``, or ``expected_behaviour``; OR
    - ``needs_development`` is False and the decision is not a hard refuse.

    Returns ``""`` when not applicable.  Defensive — never raises.
    """
    try:
        if not _is_support_explanation_ticket(pm_decision):
            return ""

        decision = (pm_decision.get("decision") or "").strip().lower() if pm_decision else ""
        classification = (pm_decision.get("classification") or "").strip().lower() if pm_decision else ""
        reason = (pm_decision.get("reason") or "").strip() if pm_decision else ""
        recommended_action = (pm_decision.get("recommended_action") or "").strip() if pm_decision else ""

        lines: List[str] = [
            "SUPPORT EXPLANATION GUIDANCE",
            "=" * 40,
            "This ticket is a support/guidance case — not a development request.",
            "The client needs explanation, direction, or a workaround, not a product change.",
            "",
            "When writing the draft response:",
            "1. Explain clearly what the current product behaviour is and why it works this way.",
            "2. State whether this is by design (expected behaviour), a configuration option,",
            "   a training/how-to topic, or a client preference that can be achieved differently.",
            "3. If a workaround or existing setting exists, describe it step by step.",
            "4. Include a clear 'Next step' for the client (e.g. 'To do this, go to … and click …').",
            "5. Avoid bare statements like 'we will not act on this' or 'BSO cannot change this'.",
            "   Instead, redirect: 'Here is how you can achieve the same result …'",
            "6. Use neutral, helpful wording — do not imply the client is wrong.",
            "7. Keep the explanation concise and actionable.",
        ]

        # Add decision-specific guidance
        if decision == "explain_workaround":
            lines += [
                "",
                "Decision type: EXPLAIN WORKAROUND",
                "→ Focus on the alternative approach or workaround the client can use today.",
                "→ Be specific: name the menu, field, or action the client should take.",
            ]
        elif decision == "support_guidance":
            lines += [
                "",
                "Decision type: SUPPORT GUIDANCE",
                "→ Provide clear, step-by-step guidance.",
                "→ If training resources exist in the KB, reference them.",
            ]
        elif decision == "make_editable":
            lines += [
                "",
                "Decision type: MAKE EDITABLE",
                "→ The client can control this themselves — explain where and how.",
                "→ Walk through the exact steps to find and change the setting.",
            ]
        elif decision == "reuse_existing_pattern":
            lines += [
                "",
                "Decision type: EXISTING PATTERN / TEMPLATE",
                "→ An existing template or workflow already covers this.",
                "→ Point the client to the existing solution rather than requesting a new one.",
            ]

        # Add classification-specific guidance
        if classification == "expected_behaviour":
            lines += [
                "",
                "Classification: EXPECTED BEHAVIOUR",
                "→ Acknowledge the client's experience, then explain why this is the expected flow.",
                "→ Do not apologise for the behaviour — validate it as intentional design.",
            ]
        elif classification == "how_to":
            lines += [
                "",
                "Classification: HOW-TO",
                "→ The client wants to know how to do something. Prioritise clarity and steps.",
                "→ Number each step. Keep instructions short.",
            ]
        elif classification == "client_preference":
            lines += [
                "",
                "Classification: CLIENT PREFERENCE",
                "→ Acknowledge the preference, then show what the product currently allows.",
                "→ If a workaround partially meets the need, present it.",
            ]

        # Append reason from PM decision if available
        if reason:
            lines += [
                "",
                f"PM reasoning: {reason}",
            ]
        if recommended_action and recommended_action != "needs_analysis":
            lines += [
                f"Recommended action: {recommended_action}",
            ]

        # Existing solution summary if provided
        if existing_solution and isinstance(existing_solution, dict):
            sol_summary = (existing_solution.get("summary") or "").strip()
            sol_detail = (existing_solution.get("detail") or existing_solution.get("description") or "").strip()
            if sol_summary or sol_detail:
                lines += ["", "Existing solution context:"]
                if sol_summary:
                    lines.append(f"  {sol_summary}")
                if sol_detail:
                    lines.append(f"  {sol_detail}")

        lines += [
            "",
            "=" * 40,
        ]

        return "\n".join(lines)

    except Exception:
        # Never raise — return empty string on any failure
        return ""
