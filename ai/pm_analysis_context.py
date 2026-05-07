"""PM analysis prompt block builder.

Public function:

  build_pm_analysis_prompt_block(pm_decision) -> str
      Combines:
        1. PM ANALYSIS INSTRUCTIONS  (build_pm_analysis_instructions)
        2. PM DECISION CONSTRAINTS   (format_pm_decision_for_prompt)
      Returns "" when both parts are empty.
      No LLM calls.  Defensive with None/empty inputs.
"""
from __future__ import annotations

from typing import Optional

from ai.pm_analysis_instructions import build_pm_analysis_instructions
from ai.pm_decision_formatter import format_pm_decision_for_prompt


def build_pm_analysis_prompt_block(pm_decision: Optional[dict]) -> str:
    """Return a combined PM context block for injection into the analysis prompt.

    Order:
      1. PM ANALYSIS INSTRUCTIONS
      2. PM DECISION CONSTRAINTS

    Sections are joined with a blank line.  Returns "" when every part
    evaluates to an empty/whitespace string.
    """
    parts: list = []

    instr = build_pm_analysis_instructions(pm_decision)
    if instr:
        parts.append(instr)

    ctx = format_pm_decision_for_prompt(pm_decision)
    if ctx:
        parts.append(ctx)

    if not parts:
        return ""

    return "\n\n".join(parts)
