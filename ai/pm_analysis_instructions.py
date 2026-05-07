"""PM analysis instruction builder.

Two public functions:

  get_pm_analysis_mode(pm_decision: dict) -> str
      Return the analysis mode string that best describes how the analysis
      should be framed.  Allowed values:
          short_client_preference_analysis
          workaround_analysis
          bug_analysis
          feature_request_analysis
          needs_analysis
          normal_analysis

  build_pm_analysis_instructions(pm_decision: dict) -> str
      Return concise analysis instructions derived from a PMDecision dict.
      Returns "" when pm_decision is falsy.  No LLM calls.
"""
from __future__ import annotations

from typing import Optional


# ── Analysis mode logic ───────────────────────────────────────────────────────

def get_pm_analysis_mode(pm_decision: Optional[dict]) -> str:
    """Return the analysis mode string for a PMDecision dict.

    Priority order (first match wins):
      1. make_editable / refuse_global_change  OR
         client_preference / product_standard / expected_behaviour
         → short_client_preference_analysis
      2. explain_workaround / support_guidance decision  OR
         support_guidance / no_dev development type
         → workaround_analysis
      3. accept_bug decision  OR  bug_fix development type
         → bug_analysis
      4. feature_request decision  OR  feature_request development type
         → feature_request_analysis
      5. needs_analysis decision  OR  needs_analysis complexity
         → needs_analysis
      6. else → normal_analysis
    """
    if not pm_decision:
        return "normal_analysis"

    decision         = pm_decision.get("decision", "")
    classification   = pm_decision.get("classification", "")
    development_type = pm_decision.get("development_type", "")
    complexity       = pm_decision.get("complexity", "")

    if decision in ("make_editable", "refuse_global_change") or \
            classification in ("client_preference", "product_standard", "expected_behaviour"):
        return "short_client_preference_analysis"

    if decision in ("explain_workaround", "support_guidance") or \
            development_type in ("support_guidance", "no_dev"):
        return "workaround_analysis"

    if decision == "accept_bug" or development_type == "bug_fix":
        return "bug_analysis"

    if decision == "feature_request" or development_type == "feature_request":
        return "feature_request_analysis"

    if decision == "needs_analysis" or complexity == "needs_analysis":
        return "needs_analysis"

    return "normal_analysis"


# ── Instruction builder ───────────────────────────────────────────────────────

def build_pm_analysis_instructions(pm_decision: Optional[dict]) -> str:
    """Return concise analysis instructions derived from a PMDecision dict.

    Returns an empty string when *pm_decision* is falsy so callers can safely
    skip injection rather than injecting a blank block.  No LLM calls.
    """
    if not pm_decision:
        return ""

    lines = ["PM ANALYSIS INSTRUCTIONS:"]

    # ── Analysis mode ─────────────────────────────────────────────────────────
    mode = get_pm_analysis_mode(pm_decision)
    lines.append(f"- Analysis mode: {mode}")

    # ── Answer length / depth ─────────────────────────────────────────────────
    if pm_decision.get("answer_depth") == "short":
        lines.append(
            "- Keep the analysis concise and focused; "
            "avoid unnecessary depth or length."
        )

    # ── No PRD ────────────────────────────────────────────────────────────────
    if pm_decision.get("needs_prd") is False:
        lines.append(
            "- Do NOT produce PRD sections such as Objective, User Story, "
            "Acceptance Criteria, or Definition of Done."
        )

    # ── No law ────────────────────────────────────────────────────────────────
    if pm_decision.get("should_mention_law") is False:
        lines.append(
            "- Do NOT mention law, article numbers, legal obligations, "
            "or compliance claims."
        )

    # ── No global default change ──────────────────────────────────────────────
    if pm_decision.get("global_change_risk") == "high":
        lines.append(
            "- Do NOT recommend changing the global default for all clients."
        )

    # ── Make editable ─────────────────────────────────────────────────────────
    if pm_decision.get("recommended_action") == "make_editable":
        lines.append(
            "- Frame the solution as configurable, editable, or adjustable "
            "per client.  Do NOT propose a global default change."
        )

    # ── Refuse global change ──────────────────────────────────────────────────
    if pm_decision.get("decision") == "refuse_global_change":
        lines.append(
            "- Explain why a global default change is not appropriate and "
            "propose per-client configurability instead."
        )

    # ── Support guidance / no dev ─────────────────────────────────────────────
    dev_type = pm_decision.get("development_type", "")
    if dev_type in ("support_guidance", "no_dev"):
        lines.append(
            "- Do NOT create a development or backlog request unless a "
            "workaround or existing setting is truly insufficient."
        )

    # ── Bug fix ───────────────────────────────────────────────────────────────
    if dev_type == "bug_fix" or pm_decision.get("decision") == "accept_bug":
        lines.append(
            "- Classify the issue as a bug, defect, or fix — "
            "NOT as a feature request or enhancement."
        )

    return "\n".join(lines)
