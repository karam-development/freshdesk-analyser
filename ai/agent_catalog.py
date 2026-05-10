"""Agent purpose catalog.

Public functions:

  get_agent_purpose_catalog() -> dict[str, dict]
      Returns a mapping of agent_name → {purpose, used_in, status}.
      Pure data — no DB, no API, no LLM calls.

  build_agent_catalog_rows(config_rows) -> list[dict]
      Merges DB config rows (from agent_model_config) with the purpose catalog.
      Returns rows suitable for template rendering.
      Each row: {agent_name, provider, model, temperature, max_tokens,
                 purpose, used_in, status, enabled}.
      Unknown agents are included with purpose "Purpose not documented yet".
      Defensive — never raises.
"""
from __future__ import annotations

from typing import Any, Dict, List


# ── Catalog ───────────────────────────────────────────────────────────────────

def get_agent_purpose_catalog() -> Dict[str, Dict[str, str]]:
    """Return a static catalog of all known agents with their purpose and usage context.

    Keys are lowercase agent_name values as stored in agent_model_config.
    Values have: purpose (str), used_in (str), status (str).
    status: "active" = in use now, "reserved" = registered but not yet wired.
    """
    return {
        # ── Core pipeline agents (active) ──────────────────────────────────────
        "main_analysis_agent": {
            "purpose": (
                "Classifies the ticket, produces the structured analysis (RICE scores, "
                "risk level, PM decision context). Entry point of the analysis pipeline."
            ),
            "used_in": "Ticket analysis (run on fetch / manual re-analysis)",
            "status": "active",
        },
        "kb_agent": {
            "purpose": (
                "Searches the Knowledge Base for entries relevant to the ticket subject, "
                "template, and workflow. Produces a validated KB brief for draft generation."
            ),
            "used_in": "Draft generation — parallel prep phase",
            "status": "active",
        },
        "code_agent": {
            "purpose": (
                "Analyses template code, finds reference patterns, and assesses technical "
                "feasibility of requested changes. Provides a plain-language code brief "
                "free of raw code."
            ),
            "used_in": "Draft generation — parallel prep phase",
            "status": "active",
        },
        "research_agent": {
            "purpose": (
                "Searches past ticket history for similar resolved issues and patterns. "
                "Surfaces relevant lessons and precedents to guide the draft."
            ),
            "used_in": "Draft generation — parallel prep phase",
            "status": "active",
        },
        "draft_response_agent": {
            "purpose": (
                "Generates the FR and EN draft responses using all agent briefs, KB evidence, "
                "PM decision constraints, and structured lessons. Main output agent."
            ),
            "used_in": "Draft generation, PM-constrained regeneration",
            "status": "active",
        },
        "qa_agent": {
            "purpose": (
                "Reviews generated drafts for quality, tone, completeness, and PM-constraint "
                "compliance. Flags issues and may trigger a single regeneration cycle."
            ),
            "used_in": "Post-draft QA (background automation and manual regeneration)",
            "status": "active",
        },
        "learning_agent": {
            "purpose": (
                "Extracts reusable lessons from PO edits, corrections, and direct Freshdesk "
                "replies. Stores them as structured PM lessons for future ticket drafts."
            ),
            "used_in": "Post-approval learning loop (triggered on ticket approval/edit)",
            "status": "active",
        },
        "prd_agent": {
            "purpose": (
                "Generates Product Requirements Documents (PRDs) for feature requests and "
                "complex changes that require structured specification."
            ),
            "used_in": "PRD generation (manual trigger on ticket page)",
            "status": "active",
        },
        # ── Reserved / planned agents ──────────────────────────────────────────
        "classification_agent": {
            "purpose": (
                "Reserved — dedicated fast classification pass to pre-label ticket type "
                "before full analysis, reducing main agent token usage."
            ),
            "used_in": "Planned: pre-analysis classification",
            "status": "reserved",
        },
        "summary_agent": {
            "purpose": (
                "Reserved — generates compact ticket summaries for dashboard previews "
                "and weekly digests."
            ),
            "used_in": "Planned: dashboard summaries / digests",
            "status": "reserved",
        },
        "feasibility_agent": {
            "purpose": (
                "Reserved — dedicated technical feasibility assessment for complex change "
                "requests, separate from the code agent brief."
            ),
            "used_in": "Planned: feasibility pre-screening",
            "status": "reserved",
        },
        "batch_agent": {
            "purpose": (
                "Reserved — processes multiple tickets in a batch job (nightly re-analysis, "
                "bulk KB refresh, scheduled re-scoring)."
            ),
            "used_in": "Planned: scheduled batch processing",
            "status": "reserved",
        },
        "reply_scanner_agent": {
            "purpose": (
                "Reserved — scans incoming Freshdesk replies for PO corrections, lesson "
                "signals, and approval confirmations to feed the learning loop."
            ),
            "used_in": "Planned: reply monitoring / learning loop intake",
            "status": "reserved",
        },
        "jira_agent": {
            "purpose": (
                "Reserved — searches and summarises Jira issues related to the ticket "
                "subject to surface known bugs and in-flight development work."
            ),
            "used_in": "Planned: Jira context injection into drafts",
            "status": "reserved",
        },
        "notification_agent": {
            "purpose": (
                "Reserved — sends internal notifications (Slack, email) when tickets are "
                "approved, flagged, or require escalation."
            ),
            "used_in": "Planned: internal notification dispatch",
            "status": "reserved",
        },
        "reporting_agent": {
            "purpose": (
                "Reserved — generates weekly/monthly support reports: ticket volumes, "
                "resolution rates, common patterns, PM decision breakdown."
            ),
            "used_in": "Planned: management reporting",
            "status": "reserved",
        },
    }


# ── Row builder ───────────────────────────────────────────────────────────────

def build_agent_catalog_rows(
    config_rows: List[Any],
) -> List[Dict[str, Any]]:
    """Merge agent_model_config DB rows with the purpose catalog.

    Parameters
    ----------
    config_rows:
        Rows from ``SELECT * FROM agent_model_config``.  May be sqlite3.Row
        objects or plain dicts.  May be empty or None.

    Returns
    -------
    list[dict]
        One dict per agent_name with keys:
        agent_name, provider, model, temperature, max_tokens,
        purpose, used_in, status, enabled.
        Unknown agents (not in catalog) are included with
        purpose="Purpose not documented yet".
    """
    try:
        catalog = get_agent_purpose_catalog()
        rows: List[Dict[str, Any]] = []

        if not config_rows:
            return rows

        for row in config_rows:
            try:
                # Support both sqlite3.Row and plain dict
                if hasattr(row, "keys"):
                    row_dict = {k: row[k] for k in row.keys()}
                else:
                    row_dict = dict(row) if row else {}

                agent_name = (row_dict.get("agent_name") or "").strip().lower()
                if not agent_name:
                    continue

                catalog_entry = catalog.get(agent_name, {})

                rows.append({
                    "agent_name": agent_name,
                    "provider": row_dict.get("provider") or "",
                    "model": row_dict.get("model") or "",
                    "temperature": row_dict.get("temperature"),
                    "max_tokens": row_dict.get("max_tokens"),
                    "enabled": bool(row_dict.get("enabled", True)),
                    "purpose": catalog_entry.get("purpose", "Purpose not documented yet"),
                    "used_in": catalog_entry.get("used_in", "—"),
                    "status": catalog_entry.get("status", "unknown"),
                })
            except Exception:
                continue

        return rows

    except Exception:
        return []
