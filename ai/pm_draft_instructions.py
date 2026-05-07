"""PM draft instructions builder.

Two public functions:

  build_pm_draft_instructions(pm_decision: dict) -> str
      Converts a PMDecision dict into concise, explicit writing instructions
      for the LLM.  Different from format_pm_decision_for_prompt which shows
      raw constraint values — this function gives *writing* guidance.

  get_pm_draft_mode(pm_decision: dict) -> str
      Deterministic preflight classification for draft mode.
      Allowed values:
          short_preference_response
          workaround_response
          bug_fix_response
          feature_request_response
          needs_analysis_response
          normal_response
"""
from __future__ import annotations

from typing import Optional


# ── Draft mode logic ──────────────────────────────────────────────────────────

def get_pm_draft_mode(pm_decision: Optional[dict]) -> str:
    """Return the draft mode string that best describes how the response should be framed.

    Priority order (first match wins):
      1. make_editable / refuse_global_change  OR  client_preference / product_standard
         → short_preference_response
      2. explain_workaround / support_guidance decision  OR  support_guidance dev type
         → workaround_response
      3. accept_bug decision  OR  bug_fix dev type
         → bug_fix_response
      4. feature_request decision  OR  feature_request dev type
         → feature_request_response
      5. needs_analysis decision  OR  needs_analysis complexity
         → needs_analysis_response
      6. else → normal_response
    """
    if not pm_decision:
        return "normal_response"

    decision        = pm_decision.get("decision", "")
    classification  = pm_decision.get("classification", "")
    development_type = pm_decision.get("development_type", "")
    complexity      = pm_decision.get("complexity", "")

    if decision in ("make_editable", "refuse_global_change") or \
            classification in ("client_preference", "product_standard"):
        return "short_preference_response"

    if decision in ("explain_workaround", "support_guidance") or \
            development_type == "support_guidance":
        return "workaround_response"

    if decision == "accept_bug" or development_type == "bug_fix":
        return "bug_fix_response"

    if decision == "feature_request" or development_type == "feature_request":
        return "feature_request_response"

    if decision == "needs_analysis" or complexity == "needs_analysis":
        return "needs_analysis_response"

    return "normal_response"


# ── Instruction builder ───────────────────────────────────────────────────────

def build_pm_draft_instructions(pm_decision: Optional[dict]) -> str:
    """Return concise writing instructions derived from a PMDecision dict.

    Returns an empty string when *pm_decision* is falsy (so callers can safely
    skip injection rather than injecting a blank block).
    """
    if not pm_decision:
        return ""

    lines = ["PM DRAFTING INSTRUCTIONS (apply to the customer-facing response):"]

    # ── Draft mode ────────────────────────────────────────────────────────────
    draft_mode = get_pm_draft_mode(pm_decision)
    lines.append(f"- Draft mode: {draft_mode}")

    # ── Answer length / depth ─────────────────────────────────────────────────
    answer_depth = pm_decision.get("answer_depth", "")
    max_words = int(pm_decision.get("max_words") or 250)
    if answer_depth == "short":
        lines.append(
            f"- Keep the full customer-facing answer short and practical: "
            f"max 2 short paragraphs, ≤{max_words} words. "
            "No long explanations. No PRD-style structure."
        )

    # ── Law / legal citations ─────────────────────────────────────────────────
    if pm_decision.get("should_mention_law") is False:
        lines.append(
            "- Do NOT cite law, article numbers, legal obligations, "
            "mandatory legal language, or compliance claims."
        )

    # ── Global default change ─────────────────────────────────────────────────
    if pm_decision.get("global_change_risk") == "high":
        lines.append(
            "- Do NOT propose changing the global default for all clients."
        )

    # ── Make editable ─────────────────────────────────────────────────────────
    recommended_action = pm_decision.get("recommended_action", "")
    if recommended_action == "make_editable":
        lines.append(
            "- Propose making the wording or field editable/configurable per client; "
            "do NOT propose changing the global wording for everyone."
        )

    # ── Refuse global change ──────────────────────────────────────────────────
    decision = pm_decision.get("decision", "")
    if decision == "refuse_global_change":
        lines.append(
            "- Politely explain that the current default wording should remain unchanged "
            "and why; offer per-client configurability instead."
        )

    # ── Workaround / support guidance ────────────────────────────────────────
    development_type = pm_decision.get("development_type", "")
    if decision in ("explain_workaround", "support_guidance") or \
            development_type == "support_guidance":
        lines.append(
            "- Provide the workaround or available setting that addresses the request; "
            "do NOT create a development request unless the workaround is truly insufficient."
        )

    # ── Bug fix ───────────────────────────────────────────────────────────────
    if development_type == "bug_fix" or decision == "accept_bug":
        lines.append(
            "- Acknowledge the defect and keep the explanation focused on the fix; "
            "do NOT frame this as a feature request or enhancement."
        )

    # ── No PRD ────────────────────────────────────────────────────────────────
    if pm_decision.get("needs_prd") is False:
        lines.append(
            "- Do NOT generate Objective / User Story / "
            "Acceptance Criteria / PRD sections."
        )

    return "\n".join(lines)
