#!/usr/bin/env python3
"""
Multi-Agent Pipeline for Freshdesk AI Analyzer.

Architecture:
  Orchestrator (Python code — your app.py)
      │
      ├─► KB Agent (Haiku) — finds relevant KB entries for this specific ticket
      ├─► Code Agent (Haiku) — analyzes template code, finds reference patterns, assesses feasibility
      ├─► Research Agent (Haiku) — finds similar past tickets, lessons learned, historical patterns
      │
      ├─► Main Agent (Sonnet) — analysis, drafts, PRD — uses KB + Code + Research briefs
      │
      ├─► QA Agent (Haiku) — validates Main Agent output against rules, KB, and code analysis
      │
      └─► Learning Agent (Haiku) — after PO review, extracts lessons for future improvement
                                    (controlled by orchestrator: only runs if changes are meaningful)

Each agent is a focused API call with a specific prompt. The orchestrator is Python code
that manages the flow, decides which agents to call, and passes data between them.
"""

import collections
import json
import logging
import os
import re
import time
import hashlib
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from anthropic import Anthropic

try:
    from ai.llm.router import LLMRouter
except ImportError:
    LLMRouter = None

logger = logging.getLogger("agents")

# ─── Agent Models ────────────────────────────────────────────────────────────
# KB, Research, QA, Learning agents use Haiku (fast, cheap, focused)
# Main analysis/draft agents continue using Sonnet (deep reasoning)
AGENT_MODEL_FAST = "claude-haiku-4-5-20251001"
AGENT_MODEL_MAIN = "claude-sonnet-4-5"

# ─── Cost Estimation (per 1M tokens, approximate) ────────────────────────────
COST_PER_1M = {
    AGENT_MODEL_FAST: {"input": 1.00, "output": 5.00},
    AGENT_MODEL_MAIN: {"input": 3.00, "output": 15.00},
}


def _call_with_retry(client, max_retries=3, **kwargs):
    """Call Anthropic API with exponential backoff on rate limit errors.
    Returns (response_text, usage_dict) where usage_dict has input_tokens, output_tokens, model."""
    for attempt in range(max_retries + 1):
        try:
            resp = client.messages.create(**kwargs)
            text = resp.content[0].text.strip() if resp.content else ""
            usage = {
                "input_tokens": getattr(resp.usage, "input_tokens", 0),
                "output_tokens": getattr(resp.usage, "output_tokens", 0),
                "model": kwargs.get("model", "unknown"),
            }
            return text, usage
        except Exception as e:
            error_str = str(e)
            is_rate_limit = "429" in error_str or "rate_limit" in error_str.lower()
            if is_rate_limit and attempt < max_retries:
                wait = 15 * (2 ** attempt)
                logger.warning(f"Rate limited (attempt {attempt+1}/{max_retries+1}), waiting {wait}s...")
                time.sleep(wait)
            else:
                raise


def _estimate_cost(usage):
    """Estimate API cost from usage dict."""
    model = usage.get("model", "")
    rates = COST_PER_1M.get(model, {"input": 3.0, "output": 15.0})
    input_cost = (usage.get("input_tokens", 0) / 1_000_000) * rates["input"]
    output_cost = (usage.get("output_tokens", 0) / 1_000_000) * rates["output"]
    return round(input_cost + output_cost, 6)


def _usage_from_llm_response(resp):
    """Normalise a routed LLMResponse usage to the legacy dict format."""
    u = getattr(resp, "usage", None)
    if u is None:
        return {}
    return {
        "input_tokens": getattr(u, "input_tokens", 0),
        "output_tokens": getattr(u, "output_tokens", 0),
        "model": getattr(resp, "model", "unknown"),
        "provider": getattr(resp, "provider", "unknown"),
    }


def _cache_key(content):
    """Generate a hash key for caching agent results.
    Uses the full content for hashing (not truncated) to avoid collisions."""
    return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()[:24]


# ═══════════════════════════════════════════════════════════════════════════════
#  1. KB AGENT — Knowledge Base Specialist
# ═══════════════════════════════════════════════════════════════════════════════

def kb_agent(client, ticket_subject, ticket_summary, full_kb_context, terminology_context="",
             code_context_summary="", max_output_tokens=3000, llm_router=None):
    """
    KB Agent: Reads the FULL knowledge base and returns ONLY the relevant information
    for this specific ticket. Also performs feasibility and accounting validation.

    Returns a structured brief with:
    - Relevant chart of accounts entries and account ranges
    - Relevant reconciliation rules
    - Liquid template capabilities/limitations relevant to this request
    - Accounting feasibility assessment
    - Technical feasibility assessment
    - Similar patterns or precedents found in KB
    """
    system = """You are the Knowledge Base Specialist agent for Silverfin's Luxembourg templates team.

YOUR ONLY JOB: Read the full knowledge base provided and extract EVERYTHING relevant to the specific
Freshdesk ticket described. You are the team's institutional memory.

You must be THOROUGH — the main analysis agent will ONLY see what you provide. If you miss something
relevant, it won't be considered. Read every KB entry carefully.

YOUR OUTPUT must include ALL of these sections (skip a section only if truly nothing is relevant):

1. RELEVANT ACCOUNTS & RANGES:
   List every chart of accounts entry, account class, or account range relevant to this ticket.
   Include the account numbers, names, and which class they belong to.
   If the ticket mentions specific accounts, VERIFY they exist and are in the correct class.

2. RELEVANT RECONCILIATION RULES:
   Any reconciliation logic, account mappings, or template rules that apply.
   How do related templates handle similar accounts or sections?

3. LIQUID TEMPLATE CONTEXT:
   Any known limitations, patterns, or capabilities of Silverfin Liquid relevant to this request.
   Can the requested change actually be implemented? Are there known constraints?

4. ACCOUNTING VALIDATION:
   Is the client's request accounting-correct?
   - Do the accounts they mention belong to the right class for what they want?
   - Is the debit/credit logic correct?
   - Are intercompany mappings standard?
   - Does this align with Luxembourg PCN (Plan Comptable Normalisé)?
   If something seems WRONG → state clearly: "ACCOUNTING CONCERN: [reason]"

5. TECHNICAL FEASIBILITY:
   Is this technically feasible in Silverfin Liquid?
   - Can Liquid do what the client is asking? (cross-template lookups, dynamic tables, etc.)
   - Are there known workarounds or patterns for this type of request?
   If something seems INFEASIBLE → state clearly: "TECHNICAL CONCERN: [reason]"

6. RELEVANT PRECEDENTS:
   Any KB entries about similar past fixes, known issues, or established patterns.
   Template documentation that describes how similar features currently work.

7. TERMINOLOGY:
   Any specific Luxembourg legal/accounting terms that must be used correctly in the response.

Be GENEROUS with what you include — better to give too much relevant context than too little.
Write in plain language. Never output code or variable names."""

    user_msg = f"""TICKET TO ANALYZE:
Subject: {ticket_subject}
Summary: {ticket_summary}

{f"CODE CONTEXT (summary of affected template): {code_context_summary}" if code_context_summary else ""}

FULL KNOWLEDGE BASE — READ ALL OF THIS:
{full_kb_context}

{f"TERMINOLOGY GLOSSARY: {terminology_context}" if terminology_context else ""}

Extract everything relevant to this ticket. Be thorough — the main agent only sees what you provide."""

    try:
        if llm_router is not None:
            resp = llm_router.complete(
                agent_name="kb_agent",
                system=system,
                messages=[{"role": "user", "content": user_msg}],
                max_tokens=max_output_tokens,
            )
            result = resp.text.strip() if resp.text else ""
            usage = _usage_from_llm_response(resp)
        else:
            result, usage = _call_with_retry(
                client,
                model=AGENT_MODEL_FAST,
                max_tokens=max_output_tokens,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            )
        logger.info(f"KB Agent returned {len(result)} chars for: {ticket_subject[:60]}")
        return result, usage
    except Exception as e:
        logger.error(f"KB Agent failed: {e}")
        raise


# ═══════════════════════════════════════════════════════════════════════════════
#  1b. CODE AGENT — Template Code Analyst
# ═══════════════════════════════════════════════════════════════════════════════

def code_agent(client, ticket_subject, ticket_summary, full_code_context,
               kb_brief="", max_output_tokens=3000, llm_router=None):
    """
    Code Agent: Reads the FULL template code (no truncation) and returns a targeted
    functional analysis for this specific ticket.

    Its job:
    - Identify which section(s) of the template are relevant to the ticket
    - Describe what the template currently does (in plain language, NO code)
    - Find REFERENCE PATTERNS in other sections of the same template
    - Identify Liquid-specific constraints or limitations
    - Flag complexity (simple label change vs deep logic restructure)

    Returns a functional brief that the main agent uses instead of raw code.
    """
    system = """You are the Code Analyst agent for Silverfin's Luxembourg templates team.
You are an expert in Silverfin Liquid templates — reconciliation texts, working papers, account templates.

YOUR ONLY JOB: Read the full template code provided and produce a FUNCTIONAL ANALYSIS
relevant to the specific Freshdesk ticket. The main analysis agent will ONLY see what you provide —
it will NOT see the raw code. You are the code expert.

CRITICAL: Your output must be in PLAIN HUMAN LANGUAGE. Never output:
- Variable names (employees_cy, hide_breakdown, company.custom.people)
- File paths (main.liquid, text_parts/translations.liquid)
- Template IDs (lux_aa_an_staff_cost, lux_ci_general_information)
- Code logic (if X == 0, unless condition, for loop)
- Section markers from code (INTRO SECTION, BREAKDOWN TABLE)

Instead, describe FUNCTIONALLY what the code does:
BAD: "The variable hide_breakdown_due_to_no_fte controls visibility"
GOOD: "The breakdown table is hidden when the company has zero employees"

YOUR OUTPUT must include ALL relevant sections:

1. TEMPLATE OVERVIEW:
   - What template is this? (human-readable name)
   - What workflow does it belong to?
   - What does it produce? (which note, which form, which document section)

2. RELEVANT SECTION ANALYSIS:
   For the section(s) related to the ticket:
   - What does this section display?
   - What inputs does it use? (dropdowns, checkboxes, editable text fields — describe functionally)
   - What visibility conditions exist? (when is it shown/hidden, and why)
   - What text does it produce? (describe the output sentence structure)
   - What period logic exists? (N, N-1, N-2 — how does it handle prior years)

3. REFERENCE PATTERNS — THIS IS CRITICAL:
   Look at OTHER sections in the SAME template that are already well-implemented.
   For each relevant pattern found:
   - Which section uses this pattern? (human-readable name)
   - What does the pattern do? (e.g., "mandatory dropdown that controls an editable text field
     with conditional second dropdown when the first selection requires it")
   - How does the visibility work? (when shown/hidden)
   - How does the infobox structure work? (dropdown → text field → sentence construction)
   Describe the pattern so the developer can replicate it for the section being fixed.

4. CURRENT BEHAVIOUR (what the code actually does NOW):
   - What text is currently generated for the reported scenario?
   - Is the client's report accurate, or does the code actually do something different?
   - Are there edge cases the client might not be aware of?

4B. DOES THE SOLUTION ALREADY EXIST? — CRITICAL CHECK:
   Many clients report "missing features" that actually ALREADY EXIST in the template but are hidden behind:
   - A setting or dropdown they haven't configured
   - A visibility condition that depends on data they haven't entered
   - A checkbox or toggle they haven't enabled
   - A different section or tab they haven't looked at
   You MUST check: does the template already handle what the client is asking for?
   If YES → clearly state: "SOLUTION EXISTS: [describe where and how to enable/use it]"
   If NO → clearly state: "SOLUTION DOES NOT EXIST: this would require new development"
   This is the single most important part of your analysis — getting this wrong wastes the PO's time.

5. TECHNICAL CONSTRAINTS:
   - Liquid limitations relevant to this fix (e.g., no cross-template lookups, no dynamic tables)
   - Dependencies: does this section depend on data from other templates or settings?
   - Linked templates: would changes here affect other templates?
   - Complexity assessment: is this a simple text change, a condition change, or a restructure?

6. SUGGESTED APPROACH (based on code patterns):
   - Based on the reference patterns found, what approach should the fix follow?
   - What specific pattern should the developer replicate?
   - What are the risks or things to watch out for?

Be THOROUGH. The main agent depends entirely on your analysis to understand the code."""

    user_msg = f"""TICKET TO ANALYZE:
Subject: {ticket_subject}
Summary: {ticket_summary}

{f"KB CONTEXT (accounting/business rules): {kb_brief[:2000]}" if kb_brief else ""}

FULL TEMPLATE CODE — READ ALL OF THIS CAREFULLY:
{full_code_context}

Analyze this code in relation to the ticket. Find reference patterns in other sections.
Output in plain language only — no code, no variable names, no file paths."""

    try:
        if llm_router is not None:
            resp = llm_router.complete(
                agent_name="code_agent",
                system=system,
                messages=[{"role": "user", "content": user_msg}],
                max_tokens=max_output_tokens,
            )
            result = resp.text.strip() if resp.text else ""
            usage = _usage_from_llm_response(resp)
        else:
            result, usage = _call_with_retry(
                client,
                model=AGENT_MODEL_FAST,
                max_tokens=max_output_tokens,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            )
        logger.info(f"Code Agent returned {len(result)} chars for: {ticket_subject[:60]}")
        return result, usage
    except Exception as e:
        logger.error(f"Code Agent failed: {e}")
        # NEVER inject raw code as fallback — the main agent would copy it into output.
        # Return a minimal functional description instead.
        fallback = "[Code Agent unavailable — no template analysis available. Assess based on ticket description only.]"
        return fallback, {}


# ═══════════════════════════════════════════════════════════════════════════════
#  2. RESEARCH AGENT — Similar Tickets & Historical Context
# ═══════════════════════════════════════════════════════════════════════════════

def research_agent(client, db, ticket_id, ticket_subject, ticket_summary, template_name="",
                   workflow_name="", jira_context="", max_output_tokens=2000,
                   _prefetched_tickets=None, _prefetched_lessons=None, llm_router=None):
    """
    Research Agent: Searches past tickets for similar issues and extracts patterns
    from how the PO handled them. Builds historical context.

    Searches by:
    - Same template name
    - Same workflow
    - Similar keywords in subject/analysis
    - Previously approved tickets with PO edits (these are the gold standard)

    If _prefetched_tickets/_prefetched_lessons are provided, skips DB queries
    (used when called from ThreadPoolExecutor to avoid thread-safety issues).
    """
    # Step 1: Find similar past tickets from the database
    if _prefetched_tickets is not None:
        similar_tickets = _prefetched_tickets
    else:
        similar_tickets = _find_similar_tickets(db, ticket_id, ticket_subject, template_name, workflow_name)

    # Step 2: Find lessons learned that might apply
    if _prefetched_lessons is not None:
        lessons = _prefetched_lessons
    else:
        lessons = _find_relevant_lessons(db, ticket_subject, template_name)

    if not similar_tickets and not lessons:
        return "No similar past tickets or lessons found in the database."

    # Step 3: Use AI to synthesize the relevant patterns
    similar_context = ""
    for t in similar_tickets[:5]:  # Max 5 similar tickets
        similar_context += f"""
--- Similar Ticket #{t['ticket_id']} ---
Subject: {t['subject']}
Classification: {t['classification']}
PO Decision: {t.get('po_decision', 'unknown')}
Analysis: {(t.get('analysis', '') or '')[:500]}
Draft Response: {(t.get('draft_response', '') or '')[:800]}
"""

    lessons_context = ""
    for lesson in lessons[:10]:
        lessons_context += f"""
- [{lesson['category']}] {lesson['lesson']} (from ticket #{lesson.get('source_ticket_id', '?')})"""

    system = """You are the Research Specialist agent for Silverfin's Luxembourg templates team.

YOUR JOB: Analyze similar past tickets, lessons learned, and related Jira issues to provide
the main analysis agent with historical context. This helps ensure consistency and learn from past decisions.

YOUR OUTPUT must include:

1. SIMILAR PAST TICKETS:
   - How were similar issues handled before?
   - What did the PO approve or decline?
   - Were there specific patterns in the solutions?

2. LESSONS LEARNED:
   - What past mistakes should be avoided?
   - What approaches worked well?
   - Any specific guidance from previous PO reviews?

3. RELATED JIRA ISSUES (if any):
   - Are there existing Jira tickets for this template or issue?
   - Is this a known bug already being worked on?
   - What priority/status do related Jira issues have?
   - Should the Freshdesk ticket reference an existing Jira issue?

4. CONSISTENCY CHECK:
   - If a similar ticket was handled differently before, flag it.
   - If there's an established pattern, describe it so the main agent follows it.

5. RECOMMENDATIONS:
   - Based on history, what approach should the main agent take?
   - Any specific things to watch out for?

Be concise but complete. The main agent will use this to make better decisions."""

    jira_section = ""
    if jira_context:
        jira_section = f"""

RELATED JIRA ISSUES:
{jira_context}
"""

    user_msg = f"""CURRENT TICKET:
Subject: {ticket_subject}
Summary: {ticket_summary}
Template: {template_name or 'Unknown'}
Workflow: {workflow_name or 'Unknown'}

SIMILAR PAST TICKETS:
{similar_context if similar_context else "None found."}

LESSONS LEARNED:
{lessons_context if lessons_context else "None recorded yet."}
{jira_section}
Synthesize what's relevant for the current ticket."""

    try:
        if llm_router is not None:
            resp = llm_router.complete(
                agent_name="research_agent",
                system=system,
                messages=[{"role": "user", "content": user_msg}],
                max_tokens=max_output_tokens,
            )
            result = resp.text.strip() if resp.text else ""
            usage = _usage_from_llm_response(resp)
        else:
            result, usage = _call_with_retry(
                client,
                model=AGENT_MODEL_FAST,
                max_tokens=max_output_tokens,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            )
        logger.info(f"Research Agent returned {len(result)} chars for: {ticket_subject[:60]}")
        return result, usage
    except Exception as e:
        logger.error(f"Research Agent failed: {e}")
        return "Research agent unavailable — proceeding without historical context.", {}


def _find_similar_tickets(db, current_ticket_id, subject, template_name="", workflow_name="", limit=5):
    """Find similar past tickets by template name, workflow, and keywords."""
    similar = []
    if not subject or not isinstance(subject, str):
        return similar

    # Strategy 1: Same template name (strongest signal)
    if template_name:
        rows = db.execute("""
            SELECT ticket_id, subject, classification, po_decision, analysis, draft_response
            FROM tickets
            WHERE template_name = ? AND ticket_id != ? AND po_decision IN ('approved', 'declined')
            ORDER BY processing_date DESC LIMIT ?
        """, (template_name, current_ticket_id, limit)).fetchall()
        similar.extend([dict(r) for r in rows])

    # Strategy 2: Same workflow (exclude already-found tickets with parameterized query)
    if workflow_name and len(similar) < limit:
        exclude_ids = [int(t["ticket_id"]) for t in similar]
        exclude_ids.append(int(current_ticket_id))
        placeholders = ",".join("?" * len(exclude_ids))
        rows = db.execute(f"""
            SELECT ticket_id, subject, classification, po_decision, analysis, draft_response
            FROM tickets
            WHERE workflow_name = ? AND po_decision IN ('approved', 'declined')
            AND ticket_id NOT IN ({placeholders})
            ORDER BY processing_date DESC LIMIT ?
        """, [workflow_name] + exclude_ids + [limit - len(similar)]).fetchall()
        similar.extend([dict(r) for r in rows])

    # Strategy 3: Keyword matching from subject
    if len(similar) < limit:
        stop_words = {"the", "a", "an", "in", "on", "at", "for", "to", "of", "and", "or", "is", "are",
                      "le", "la", "les", "de", "du", "des", "en", "un", "une", "et", "ou", "est",
                      "silverfin", "template", "issue", "bug", "error", "problem", "request", "-", "–"}
        words = [w.lower() for w in subject.split() if len(w) > 2 and w.lower() not in stop_words]
        existing_ids = [int(t["ticket_id"]) for t in similar]
        existing_ids.append(int(current_ticket_id))

        for word in words[:5]:
            if len(similar) >= limit:
                break
            placeholders = ",".join("?" * len(existing_ids))
            rows = db.execute(f"""
                SELECT ticket_id, subject, classification, po_decision, analysis, draft_response
                FROM tickets
                WHERE subject LIKE ? AND po_decision IN ('approved', 'declined')
                AND ticket_id NOT IN ({placeholders})
                ORDER BY processing_date DESC LIMIT 2
            """, [f"%{word}%"] + existing_ids).fetchall()
            for r in rows:
                if r["ticket_id"] not in set(existing_ids) and len(similar) < limit:
                    similar.append(dict(r))
                    existing_ids.append(int(r["ticket_id"]))

    return similar


def _find_relevant_lessons(db, subject, template_name="", limit=40):
    """Find lessons learned relevant to this ticket.

    Strategy — we never want to drop a lesson just because it's old. Retrieval is
    tiered so the prompt always carries the durable rules plus recent specifics:

      1. ALL pinned lessons (manually marked by the PO as always-on)             → always included
      2. ALL high-importance lessons (global + template-matched, any age)        → always included
      3. ALL lessons for this exact template_name (any importance, any age)      → always included
      4. Medium-importance global lessons ordered by (hit_count DESC, recency)   → until `limit`
      5. Keyword matches on subject (LIKE against lesson/category)               → fill remainder

    Duplicates across tiers are skipped. Returns a list of dicts ordered so the
    prompt caller can simply take them in order (pinned + high first)."""
    if not subject or not isinstance(subject, str):
        return []
    try:
        collected = []
        seen_ids = set()

        def add_rows(rows):
            for r in rows:
                rid = r["id"]
                if rid in seen_ids:
                    continue
                seen_ids.add(rid)
                collected.append(dict(r))

        # Tier 1: pinned (always on, no cap)
        rows = db.execute("""
            SELECT * FROM agent_lessons
            WHERE active = 1 AND pinned = 1
            ORDER BY importance = 'high' DESC, hit_count DESC, created_at DESC
        """).fetchall()
        add_rows(rows)

        # Tier 2: high-importance (all of them — these are the durable rules)
        rows = db.execute("""
            SELECT * FROM agent_lessons
            WHERE active = 1 AND importance = 'high'
            ORDER BY hit_count DESC, created_at DESC
        """).fetchall()
        add_rows(rows)

        # Tier 3: every active lesson for this exact template (no age cap)
        if template_name:
            rows = db.execute("""
                SELECT * FROM agent_lessons
                WHERE active = 1 AND template_name = ?
                ORDER BY importance = 'high' DESC,
                         importance = 'medium' DESC,
                         hit_count DESC,
                         created_at DESC
            """, (template_name,)).fetchall()
            add_rows(rows)

        # Tier 4: medium-importance global lessons, ranked by reinforcement
        remaining = max(limit - len(collected), 0)
        if remaining > 0:
            rows = db.execute("""
                SELECT * FROM agent_lessons
                WHERE active = 1 AND importance = 'medium'
                ORDER BY hit_count DESC, created_at DESC
                LIMIT ?
            """, (remaining,)).fetchall()
            add_rows(rows)

        # Tier 5: keyword fill from the ticket subject
        remaining = max(limit - len(collected), 0)
        if remaining > 0:
            words = [w.lower() for w in subject.split() if len(w) > 3]
            for word in words[:5]:
                if remaining <= 0:
                    break
                if seen_ids:
                    placeholders = ",".join("?" * len(seen_ids))
                    rows = db.execute(f"""
                        SELECT * FROM agent_lessons
                        WHERE active = 1
                        AND (lesson LIKE ? OR category LIKE ?)
                        AND id NOT IN ({placeholders})
                        ORDER BY hit_count DESC, created_at DESC
                        LIMIT ?
                    """, [f"%{word}%", f"%{word}%"] + list(seen_ids) + [remaining]).fetchall()
                else:
                    rows = db.execute("""
                        SELECT * FROM agent_lessons
                        WHERE active = 1 AND (lesson LIKE ? OR category LIKE ?)
                        ORDER BY hit_count DESC, created_at DESC
                        LIMIT ?
                    """, (f"%{word}%", f"%{word}%", remaining)).fetchall()
                add_rows(rows)
                remaining = max(limit - len(collected), 0)

        return collected
    except sqlite3.OperationalError:
        # Table might not exist yet
        return []


# ═══════════════════════════════════════════════════════════════════════════════
#  3. QA AGENT — Quality Assurance / Rule Police
# ═══════════════════════════════════════════════════════════════════════════════

def qa_agent(client, agent_output, output_type, ticket_subject, kb_brief, rules_context="", llm_router=None):
    """
    QA Agent: Reviews the output of the main analysis agent and checks for:
    - Rule violations (code references, mixed languages, markdown, etc.)
    - KB inconsistencies (accounting errors, wrong accounts, infeasible requests not flagged)
    - Structural issues (missing sections, wrong order, etc.)
    - Blind agreement (did the AI just agree without validating?)

    Returns a QA report with pass/fail and specific issues found.

    output_type: "analysis" | "draft_response" | "prd_analysis"
    """
    rules_by_type = {
        "analysis": """
RULES TO CHECK FOR ANALYSIS OUTPUT:
1. Classification must be one of: bug, feature_request, how_to, sync, data, other
2. Summary must mention the specific template/note name — never vague
3. Analysis must include: template name, what's wrong, legitimacy check, classification reasoning
4. Risk level must match the actual severity (not client's claimed urgency)
5. RICE scores must use fixed scales (Reach 1-10, Impact 1-5, Confidence 1-5, Effort 1-10)
6. NO code references (variable names, file paths, template IDs, code logic)
7. Output must be valid JSON""",

        "draft_response": """
RULES TO CHECK FOR DRAFT RESPONSE OUTPUT:
1. Must contain exactly 3 sections: --- CLIENT RESPONSE ---, --- INTERNAL NOTE (BSO LUX) ---, --- BACKLOG TICKET ---
   EXCEPTION: For simple wording/translation fixes, BACKLOG TICKET section may be skipped entirely — this is OK.
2. ZERO code in output (no variable names, file paths, template IDs, programming logic)
3. NO mixed languages (FR version = 100% French, EN = 100% English, EXCEPT proposed wording has both)
4. NO markdown (no **, no #, no ```)
5. Internal note order: Hi team → position → issue → conditions → "Next step:" → "Proposed new wording" → edge cases → Thanks
6. "Next step:" MUST come BEFORE "Proposed new wording" — mandatory order
7. Luxembourg legal terminology must be exact (Gérant Unique, Conseil de Gérance, etc.)
8. Proposed wording must have BOTH FR and EN versions
9. Must NOT blindly agree — if the request is wrong/infeasible, it should say so
10. COMPLEXITY CHECK — STRICT ENFORCEMENT:
    - Translation fix, wording change, label update, typo → total response MUST be under 250 words. If over 250 words → CRITICAL: "overcomplicated — this is a simple fix, response must be under 250 words"
    - Simple fix should have NO BACKLOG TICKET section. If present → CRITICAL: "BACKLOG TICKET should be skipped for simple fixes"
    - Simple fix internal note should be: state issue + exact new wording (FR + EN). If it includes lengthy context paragraphs, template logic explanation, or edge case analysis → flag as "overcomplicated"
    - If the draft is 500+ words for ANY wording/translation/label change → CRITICAL: "overcomplicated — response should be drastically shorter for this type of fix"
11. Check each ticket on a case-by-case basis. Not every ticket needs a detailed response. Match the response depth to what the fix actually requires.""",

        "prd_analysis": """
RULES TO CHECK FOR PRD ANALYSIS OUTPUT:
1. Must be valid JSON with ALL required fields: template_name, workflow, period_logic, linked_templates, intro_sentence, context, problem_statement, current_behaviour, new_behaviour_summary, new_behaviour_subsections, visibility_rules, test_scenarios
2. ZERO code references anywhere (no variable names, file paths, template IDs, Liquid syntax)
3. new_behaviour_subsections: MUST be empty [] for simple wording fixes, MUST have 4-7 subsections for complex dropdown/infobox changes
4. Tables MUST use correct format (DROPDOWN_TABLE:, COMBINATION_TABLE:, VISIBILITY_TABLE:, OUTPUT_TABLE:) — not prose descriptions
5. Must NOT include "Next step" — that belongs only in BSO note, NEVER in PRD
6. If PO draft exists, ALL functional logic from the PO draft MUST be preserved and expanded — never simplified or omitted
7. current_behaviour and new behaviour MUST include exact FR: and EN: wording on separate lines
8. test_scenarios MUST have specific inputs (checkbox state, dropdown value) and expected output (exact text) — not vague descriptions
9. Complexity must match content: simple wording fix = concise PRD with empty subsections, complex infobox = full detail
10. Must NOT invent business rules, account ranges, or wording not in the PO draft or ticket — use <<<ADD>>> for missing info
11. Must NOT agree with infeasible requests — should flag them with <<<INFEASIBLE>>>

STRICT FORMAT ENFORCEMENT (flag as CRITICAL if violated):
12. The JSON structure must match EXACTLY what the prompt specifies — no extra fields, no missing fields
13. If complexity_assessment says "Simple fix" but new_behaviour_subsections has more than 2 items → CRITICAL: overcomplicated for a simple fix
14. If complexity_assessment says "Complex" but new_behaviour_subsections is empty → CRITICAL: undersized for a complex fix
15. All table formats must use the pipe-separated syntax (DROPDOWN_TABLE:, VISIBILITY_TABLE:, etc.) — prose descriptions of tables are CRITICAL violations
16. test_scenarios count must match complexity: Simple = 3-5, Medium = 4-6, Complex = 8-10. If >10 for a simple fix → CRITICAL: overcomplicated
17. Every field that says FR:/EN: must have BOTH languages present — missing one is a CRITICAL violation""",
    }

    system = f"""You are the Quality Assurance agent for Silverfin's Luxembourg templates team.

YOUR JOB: Review the output of another AI agent and check it follows ALL rules and is consistent
with the knowledge base. You are the "police" — strict, thorough, no exceptions.

{rules_by_type.get(output_type, "")}

UNIVERSAL RULES (apply to ALL output types):
- NEVER reference code, variable names, file paths, or programming logic
- Responses must be in the correct language (no mixing)
- Accounting claims must be validated against the KB brief
- If the agent blindly agreed with a client request that seems wrong, FLAG IT
- If the agent missed relevant KB context, FLAG IT
- If Luxembourg legal terminology is wrong, FLAG IT

KNOWLEDGE BASE BRIEF (what the KB agent found relevant):
{kb_brief[:3000]}

YOUR OUTPUT must be valid JSON:
{{
  "passed": true/false,
  "score": 0-100,
  "critical_issues": ["list of critical problems that MUST be fixed"],
  "warnings": ["list of non-critical issues that should be improved"],
  "suggestions": ["list of optional improvements"],
  "blind_agreement": true/false,
  "accounting_validated": true/false,
  "rules_followed": true/false,
  "summary": "one sentence overall assessment"
}}

Be STRICT. If there's a critical issue, passed must be false."""

    user_msg = f"""TICKET: {ticket_subject}

OUTPUT TYPE: {output_type}

AGENT OUTPUT TO REVIEW:
{agent_output[:8000]}

Review this output against all rules. Be thorough."""

    try:
        if llm_router is not None:
            resp = llm_router.complete(
                agent_name="qa_agent",
                system=system,
                messages=[{"role": "user", "content": user_msg}],
                max_tokens=1500,
            )
            text = resp.text.strip() if resp.text else ""
            usage = _usage_from_llm_response(resp)
        else:
            text, usage = _call_with_retry(
                client,
                model=AGENT_MODEL_FAST,
                max_tokens=1500,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            )
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        try:
            result = json.loads(text)
            result.setdefault("passed", False)
            result.setdefault("score", 0)
            result.setdefault("critical_issues", [])
            result.setdefault("warnings", [])
            result.setdefault("suggestions", [])
            result.setdefault("blind_agreement", False)
            result.setdefault("summary", "")
            result["_usage"] = usage  # Attach usage for cost tracking
            logger.info(f"QA Agent: score={result['score']}, passed={result['passed']} for: {ticket_subject[:40]}")
            return result
        except json.JSONDecodeError:
            logger.error(f"QA Agent JSON parse failed: {text[:200]}")
            return {"passed": False, "score": 0, "critical_issues": ["QA agent output could not be parsed"],
                    "warnings": [], "suggestions": [], "_usage": usage,
                    "summary": "QA check failed — output could not be parsed"}
    except Exception as e:
        logger.error(f"QA Agent failed: {e}")
        # IMPORTANT: default to passed=False when QA fails, so issues are never silently skipped.
        # A failed QA check is NOT the same as a passed one — we'd rather flag a false positive
        # than let a broken output through unchecked.
        return {"passed": False, "score": 0, "critical_issues": ["QA agent could not run — manual review required"],
                "warnings": [f"QA agent unavailable: {str(e)[:100]}"], "suggestions": [],
                "summary": "QA check failed — manual review required"}


# ═══════════════════════════════════════════════════════════════════════════════
#  4. LEARNING AGENT — Continuous Improvement
# ═══════════════════════════════════════════════════════════════════════════════

def _lesson_fingerprint(text):
    """Normalised fingerprint for duplicate detection.
    Keeps only alphanumerics (lowercased), takes the first 180 chars.
    This catches lessons that are worded almost identically across tickets."""
    if not text:
        return ""
    normalised = re.sub(r"[^a-z0-9]+", "", text.lower())
    return normalised[:180]


def _upsert_lesson(db, row):
    """Insert a new lesson, or — if a near-identical one already exists — increment
    its hit_count and bump last_reinforced_at. Returns (lesson_id, was_duplicate)."""
    from datetime import datetime, timezone as _tz
    fp = _lesson_fingerprint(row.get("lesson", ""))
    now = datetime.now(_tz.utc).isoformat()

    if fp:
        try:
            candidates = db.execute("""
                SELECT id, lesson, hit_count, importance FROM agent_lessons
                WHERE active = 1
                AND (template_name = ? OR template_name = '' OR ? = '')
                ORDER BY created_at DESC LIMIT 500
            """, (row.get("template_name", ""), row.get("template_name", ""))).fetchall()
            for c in candidates:
                if _lesson_fingerprint(c["lesson"]) == fp:
                    # duplicate — reinforce
                    new_hits = (c["hit_count"] or 1) + 1
                    # If a lesson gets reinforced 3+ times, promote to high importance
                    new_imp = "high" if new_hits >= 3 else c["importance"]
                    db.execute("""
                        UPDATE agent_lessons
                        SET hit_count = ?, last_reinforced_at = ?, importance = ?
                        WHERE id = ?
                    """, (new_hits, now, new_imp, c["id"]))
                    return c["id"], True
        except Exception as e:
            logger.warning(f"Dedup check failed, inserting anyway: {e}")

    # No match → insert fresh
    cur = db.execute("""
        INSERT INTO agent_lessons
        (source_ticket_id, template_name, workflow_name, category, lesson,
         importance, applies_to, output_type, active, created_at,
         hit_count, last_reinforced_at, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 1, ?, ?)
    """, (
        row.get("source_ticket_id"),
        row.get("template_name", ""),
        row.get("workflow_name", ""),
        row.get("category", "general"),
        row.get("lesson"),
        row.get("importance", "medium"),
        row.get("applies_to", "all"),
        row.get("output_type", "draft_response"),
        now,
        now,
        row.get("source", "po_edit"),
    ))
    return cur.lastrowid, False


def learning_agent(client, db, ticket_id, ticket_subject, template_name, workflow_name,
                   original_ai_output, final_po_output, output_type="draft_response",
                   source="po_edit", llm_router=None, include_usage=False):
    """
    Learning Agent: Compares the AI's original output with the PO's final edited version.
    Extracts lessons about what the PO changed and WHY, then stores them for future reference.

    Called AFTER the PO reviews and edits a response. Also called from the background
    Freshdesk-reply scanner when an agent replies directly on Freshdesk without editing
    the draft in the tool — in that case `source="freshdesk_reply"` and
    `final_po_output` is the reply body from Freshdesk.

    Lessons are stored in the agent_lessons table and used by the Research Agent
    to provide historical context to future analysis.
    """
    if not original_ai_output or not final_po_output:
        return ([], {}) if include_usage else []

    # Skip if outputs are identical (PO didn't change anything)
    if original_ai_output.strip() == final_po_output.strip():
        logger.info(f"Learning Agent: No changes detected for ticket {ticket_id}, skipping.")
        return ([], {}) if include_usage else []

    system = """You are the Learning Specialist agent for Silverfin's Luxembourg templates team.

YOUR JOB: Compare the AI's original draft with the PO's final edited version and extract
concrete, reusable LESSONS that will help the AI do better next time.

Focus on WHAT the PO changed and WHY. Extract patterns, not one-off corrections.

For each lesson, categorize it:
- "accounting": PO corrected an accounting concept or account reference
- "terminology": PO corrected Luxembourg legal/accounting terminology
- "feasibility": PO flagged something as infeasible or technically impossible
- "tone": PO adjusted the writing style or professionalism
- "structure": PO reorganised sections, added/removed content blocks
- "logic": PO corrected the functional analysis or business logic
- "pattern": PO used a specific pattern that should be replicated
- "wording": PO changed proposed template wording (FR or EN)
- "scope": PO adjusted which templates, periods, or entities are affected
- "validation": PO pushed back on client's request (didn't just agree)

YOUR OUTPUT must be a JSON array of lessons:
[
  {
    "category": "one of the categories above",
    "lesson": "Concrete, reusable lesson. Not 'PO changed X' but 'For template Y, always Z because...'",
    "importance": "high" | "medium" | "low",
    "applies_to": "specific template name, or 'all' if it's a general rule"
  }
]

Rules:
- Only extract MEANINGFUL lessons (not trivial typo fixes)
- Each lesson must be actionable — something the AI can apply to future tickets
- If the PO completely rewrote a section, that's a HIGH importance lesson
- Maximum 5 lessons per review (focus on the most important ones)
- Write lessons as instructions: "Always...", "Never...", "For X template, use..."
- Return an empty array [] if no meaningful lessons can be extracted"""

    user_msg = f"""TICKET: {ticket_subject}
Template: {template_name or "Unknown"}
Workflow: {workflow_name or "Unknown"}
Output type: {output_type}

AI'S ORIGINAL OUTPUT:
{original_ai_output[:4000]}

PO'S FINAL EDITED VERSION:
{final_po_output[:4000]}

Extract lessons from what the PO changed. Focus on patterns, not one-off fixes."""

    try:
        if llm_router is not None:
            resp = llm_router.complete(
                agent_name="learning_agent",
                system=system,
                messages=[{"role": "user", "content": user_msg}],
                max_tokens=1500,
            )
            text = resp.text.strip() if resp.text else ""
            usage = _usage_from_llm_response(resp)
        else:
            text, usage = _call_with_retry(
                client,
                model=AGENT_MODEL_FAST,
                max_tokens=1500,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            )
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        try:
            lessons = json.loads(text)
            if not isinstance(lessons, list):
                lessons = []
        except json.JSONDecodeError:
            logger.error(f"Learning Agent JSON parse failed: {text[:200]}")
            lessons = []

        # Store lessons in the database (with deduplication + reinforcement)
        stored_count = 0
        reinforced_count = 0
        for lesson in lessons:
            if not lesson.get("lesson"):
                continue
            try:
                _, was_dup = _upsert_lesson(db, {
                    "source_ticket_id": ticket_id,
                    "template_name": template_name or "",
                    "workflow_name": workflow_name or "",
                    "category": lesson.get("category", "general"),
                    "lesson": lesson["lesson"],
                    "importance": lesson.get("importance", "medium"),
                    "applies_to": lesson.get("applies_to", "all"),
                    "output_type": output_type,
                    "source": source,
                })
                if was_dup:
                    reinforced_count += 1
                else:
                    stored_count += 1
            except Exception as e:
                logger.warning(f"Failed to store lesson: {e}")

        if stored_count or reinforced_count:
            db.commit()
            logger.info(
                f"Learning Agent (source={source}) on ticket {ticket_id}: "
                f"{stored_count} new, {reinforced_count} reinforced"
            )

        return (lessons, usage) if include_usage else lessons

    except Exception as e:
        logger.error(f"Learning Agent failed: {e}")
        return ([], {}) if include_usage else []


# ═══════════════════════════════════════════════════════════════════════════════
#  5. ORCHESTRATOR — Coordinates the Full Pipeline
# ═══════════════════════════════════════════════════════════════════════════════

class AgentOrchestrator:
    """
    Orchestrator that coordinates all agents for ticket processing.

    Pipeline for ANALYSIS (initial fetch):
      1. KB Agent → targeted knowledge brief
      2. Code Agent → functional code analysis + reference patterns
      3. Research Agent → similar tickets + lessons
      4. Main Analysis Agent → classification, RICE, summary, analysis
      5. QA Agent → validate output

    Pipeline for DRAFT RESPONSE (after PO approval):
      1. KB Agent → targeted knowledge brief
      2. Code Agent → functional code analysis + reference patterns
      3. Research Agent → how similar tickets were responded to
      4. Main Draft Agent → generate draft response
      5. QA Agent → validate draft

    Pipeline for PRD ANALYSIS (deep analysis):
      1. KB Agent → targeted knowledge brief
      2. Code Agent → functional code analysis + reference patterns
      3. Research Agent → similar PRDs
      4. Main PRD Agent → generate structured analysis
      5. QA Agent → validate PRD

    Post-PO-review (called when PO saves edits):
      Learning Agent → extract lessons from PO's changes
    """

    def __init__(self, anthropic_key, db=None):
        self.client = Anthropic(api_key=anthropic_key)
        self.db = db
        self._api_key = anthropic_key  # Keep key for per-thread client creation
        self._db_lock = threading.Lock()  # Serialize DB access across worker threads
        self._agent_log = collections.deque(maxlen=500)  # Bounded in-memory log
        self._batch_kb_cache = {}  # In-memory cache for batch KB optimization
        # Provider-agnostic LLM router (reads per-agent config from DB)
        if LLMRouter is not None:
            try:
                self.llm_router = LLMRouter(db=db)
            except Exception:
                self.llm_router = None
        else:
            self.llm_router = None

    # ── Logging with cost tracking ────────────────────────────────────────────

    def _log_agent(self, agent_name, ticket_id, input_size, output_size, duration_ms,
                   success=True, error=None, usage=None):
        """Log agent execution with cost tracking."""
        u = usage or {}
        cost = _estimate_cost(u) if u else 0
        entry = {
            "agent": agent_name, "ticket_id": ticket_id,
            "input_chars": input_size, "output_chars": output_size,
            "input_tokens": u.get("input_tokens", 0),
            "output_tokens": u.get("output_tokens", 0),
            "estimated_cost": cost,
            "duration_ms": duration_ms, "success": success,
            "error": str(error)[:200] if error else None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provider": u.get("provider", ""),
            "model": u.get("model", ""),
        }
        self._agent_log.append(entry)

        if self.db:
            try:
                with self._db_lock:
                    try:
                        self.db.execute("""
                            INSERT INTO agent_logs (agent_name, ticket_id, input_chars, output_chars,
                                input_tokens, output_tokens, estimated_cost,
                                duration_ms, success, error, provider, model, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (agent_name, ticket_id, input_size, output_size,
                              u.get("input_tokens", 0), u.get("output_tokens", 0), cost,
                              duration_ms, 1 if success else 0, entry["error"],
                              entry["provider"], entry["model"], entry["timestamp"]))
                    except Exception:
                        # Fallback to old schema without provider/model columns
                        self.db.execute("""
                            INSERT INTO agent_logs (agent_name, ticket_id, input_chars, output_chars,
                                input_tokens, output_tokens, estimated_cost,
                                duration_ms, success, error, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (agent_name, ticket_id, input_size, output_size,
                              u.get("input_tokens", 0), u.get("output_tokens", 0), cost,
                              duration_ms, 1 if success else 0, entry["error"], entry["timestamp"]))
                    self.db.commit()
            except Exception as e:
                logger.warning(f"Failed to log agent execution to DB: {e}")

    # ── Caching ───────────────────────────────────────────────────────────────

    def _get_cached(self, agent_name, ticket_id, content_hash, max_age_hours=4):
        """Check cache for a previous agent result."""
        if not self.db:
            return None
        try:
            with self._db_lock:
                row = self.db.execute("""
                    SELECT result, created_at FROM agent_cache
                    WHERE agent_name = ? AND ticket_id = ? AND cache_key = ?
                """, (agent_name, ticket_id, content_hash)).fetchone()
            if row:
                created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
                if datetime.now(timezone.utc) - created < timedelta(hours=max_age_hours):
                    logger.info(f"Cache hit: {agent_name} for ticket {ticket_id}")
                    return row["result"]
        except Exception as e:
            logger.warning(f"Cache read failed for {agent_name}: {e}")
        return None

    def _set_cached(self, agent_name, ticket_id, content_hash, result):
        """Store agent result in cache."""
        if not self.db:
            return
        try:
            with self._db_lock:
                expires = (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()
                self.db.execute("""
                    INSERT OR REPLACE INTO agent_cache (agent_name, ticket_id, cache_key, result, created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (agent_name, ticket_id, content_hash, result,
                      datetime.now(timezone.utc).isoformat(), expires))
                self.db.commit()
        except Exception as e:
            logger.warning(f"Cache write failed for {agent_name}: {e}")

    def _cleanup_expired_cache(self):
        """Remove expired cache entries to prevent unbounded DB growth."""
        if not self.db:
            return
        try:
            with self._db_lock:
                self.db.execute(
                    "DELETE FROM agent_cache WHERE expires_at < ?",
                    (datetime.now(timezone.utc).isoformat(),)
                )
                self.db.commit()
        except Exception as e:
            logger.warning(f"Cache cleanup failed: {e}")

    # ── Individual agent runners ──────────────────────────────────────────────

    def get_kb_brief(self, ticket_id, ticket_subject, ticket_summary,
                     full_kb_context, terminology_context="", code_context_summary=""):
        """Run KB Agent with caching."""
        if not full_kb_context:
            return ""

        # Check cache
        ck = _cache_key(f"{ticket_subject}:{full_kb_context}")
        cached = self._get_cached("kb_agent", ticket_id, ck)
        if cached:
            return cached

        start = time.time()
        try:
            result, usage = kb_agent(
                self.client, ticket_subject, ticket_summary,
                full_kb_context, terminology_context, code_context_summary,
                llm_router=self.llm_router,
            )
            duration = int((time.time() - start) * 1000)
            self._log_agent("kb_agent", ticket_id, len(full_kb_context), len(result), duration, usage=usage)
            self._set_cached("kb_agent", ticket_id, ck, result)
            return result
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            self._log_agent("kb_agent", ticket_id, len(full_kb_context), 0, duration, False, e)
            logger.error(f"KB Agent failed for ticket {ticket_id}: {e}")
            return f"KB Agent failed: {str(e)[:200]}"

    def get_code_brief(self, ticket_id, ticket_subject, ticket_summary,
                       full_code_context, kb_brief=""):
        """Run Code Agent with caching."""
        if not full_code_context:
            return ""

        ck = _cache_key(f"{ticket_subject}:{full_code_context}")
        cached = self._get_cached("code_agent", ticket_id, ck)
        if cached:
            return cached

        start = time.time()
        try:
            result, usage = code_agent(
                self.client, ticket_subject, ticket_summary,
                full_code_context, kb_brief,
                llm_router=self.llm_router,
            )
            duration = int((time.time() - start) * 1000)
            self._log_agent("code_agent", ticket_id, len(full_code_context), len(result), duration, usage=usage)
            self._set_cached("code_agent", ticket_id, ck, result)
            return result
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            self._log_agent("code_agent", ticket_id, len(full_code_context), 0, duration, False, e)
            logger.error(f"Code Agent failed for ticket {ticket_id}: {e}")
            # NEVER return raw code as fallback — it leaks into AI output
            return "Code Agent unavailable — no template analysis available."

    def get_research_brief(self, ticket_id, ticket_subject, ticket_summary,
                           template_name="", workflow_name="", jira_context=""):
        """Run Research Agent (no cache — needs fresh DB data).
        DB queries are serialized with the lock to support ThreadPoolExecutor."""
        if not self.db:
            return ""

        # Do DB queries under lock BEFORE calling the AI (which is the slow part)
        similar_tickets = []
        lessons = []
        try:
            with self._db_lock:
                similar_tickets = _find_similar_tickets(self.db, ticket_id, ticket_subject, template_name, workflow_name)
                lessons = _find_relevant_lessons(self.db, ticket_subject, template_name)
        except Exception as e:
            logger.warning(f"Research Agent DB queries failed: {e}")

        start = time.time()
        try:
            result, usage = research_agent(
                self.client, self.db, ticket_id, ticket_subject, ticket_summary,
                template_name, workflow_name, jira_context=jira_context,
                _prefetched_tickets=similar_tickets, _prefetched_lessons=lessons,
                llm_router=self.llm_router,
            )
            duration = int((time.time() - start) * 1000)
            self._log_agent("research_agent", ticket_id, 0, len(result), duration, usage=usage)
            return result
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            self._log_agent("research_agent", ticket_id, 0, 0, duration, False, e)
            logger.error(f"Research Agent failed for ticket {ticket_id}: {e}")
            return "Research agent unavailable — proceeding without historical context."

    def run_qa(self, ticket_id, agent_output, output_type, ticket_subject, kb_brief):
        """Run QA Agent."""
        start = time.time()
        try:
            result = qa_agent(
                self.client, agent_output, output_type, ticket_subject, kb_brief,
                llm_router=self.llm_router,
            )
            usage = result.pop("_usage", {})
            duration = int((time.time() - start) * 1000)
            self._log_agent("qa_agent", ticket_id, len(agent_output), 0, duration, usage=usage)
            return result
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            self._log_agent("qa_agent", ticket_id, len(agent_output), 0, duration, False, e)
            return {"passed": False, "score": 0,
                    "critical_issues": ["QA execution failed; manual review required"],
                    "warnings": [str(e)[:200]], "suggestions": [],
                    "summary": "QA check failed — manual review required"}

    # ── Parallel execution ────────────────────────────────────────────────────

    def run_preparation_agents_parallel(self, ticket_id, ticket_subject, ticket_summary,
                                         full_kb_context, full_code_context,
                                         terminology_context="", template_name="", workflow_name="",
                                         jira_context=""):
        """Run KB, Code, and Research agents in parallel using ThreadPoolExecutor.
        Returns (kb_brief, code_brief, research_brief) — all strings."""
        kb_brief = ""
        code_brief = ""
        research_brief = ""

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {}

            # Submit KB Agent
            if full_kb_context:
                futures["kb"] = executor.submit(
                    self.get_kb_brief, ticket_id, ticket_subject, ticket_summary,
                    full_kb_context, terminology_context,
                    full_code_context[:500] if full_code_context else ""
                )

            # Submit Research Agent (doesn't depend on KB brief)
            if self.db:
                futures["research"] = executor.submit(
                    self.get_research_brief, ticket_id, ticket_subject, ticket_summary,
                    template_name, workflow_name, jira_context
                )

            # Wait for KB brief first (Code Agent needs it)
            if "kb" in futures:
                try:
                    kb_brief = futures["kb"].result(timeout=30)
                except Exception as e:
                    logger.warning(f"KB Agent parallel failed: {e}")
                    kb_brief = full_kb_context[:5000] if full_kb_context else ""

            # Now submit Code Agent (can use KB brief for context)
            if full_code_context:
                futures["code"] = executor.submit(
                    self.get_code_brief, ticket_id, ticket_subject, ticket_summary,
                    full_code_context, kb_brief
                )

            # Collect remaining results
            if "code" in futures:
                try:
                    code_brief = futures["code"].result(timeout=30)
                except Exception as e:
                    logger.warning(f"Code Agent parallel failed: {e}")
                    # NEVER use raw code as fallback — it leaks into AI output
                    code_brief = "[Code Agent unavailable — no template analysis available.]"

            if "research" in futures:
                try:
                    research_brief = futures["research"].result(timeout=30)
                except Exception as e:
                    logger.warning(f"Research Agent parallel failed: {e}")

        return kb_brief, code_brief, research_brief

    # ── QA with retry ─────────────────────────────────────────────────────────

    def run_qa_with_retry(self, ticket_id, agent_output, output_type, ticket_subject,
                          kb_brief, retry_fn=None, max_retries=1):
        """Run QA Agent. If critical issues found AND a retry function is provided,
        feed QA feedback back to the main agent and re-validate once.

        retry_fn: callable(qa_feedback) -> new_output  (optional)
        """
        qa_result = self.run_qa(ticket_id, agent_output, output_type, ticket_subject, kb_brief)

        if not qa_result.get("critical_issues") or not retry_fn or max_retries < 1:
            return qa_result, agent_output

        # Retry: feed QA feedback to main agent
        logger.info(f"QA retry for ticket {ticket_id}: {qa_result['critical_issues']}")
        qa_feedback = "QA AGENT FOUND THESE ISSUES — FIX THEM:\n"
        for issue in qa_result["critical_issues"]:
            qa_feedback += f"- {issue}\n"
        for warning in qa_result.get("warnings", [])[:3]:
            qa_feedback += f"- (warning) {warning}\n"

        try:
            new_output = retry_fn(qa_feedback)
            # Re-validate
            qa_result_2 = self.run_qa(ticket_id, new_output, output_type, ticket_subject, kb_brief)
            return qa_result_2, new_output
        except Exception as e:
            logger.warning(f"QA retry failed for ticket {ticket_id}: {e}")
            return qa_result, agent_output

    # ── Learning (with orchestrator control) ──────────────────────────────────

    def should_learn(self, original_output, final_output, min_diff_ratio=0.05):
        """Decide whether the Learning Agent should run."""
        if not original_output or not final_output:
            return False
        orig = original_output.strip()
        final = final_output.strip()
        if orig == final:
            return False
        shorter = min(len(orig), len(final))
        if shorter == 0:
            return True
        common = sum(1 for a, b in zip(orig, final) if a == b)
        diff_ratio = 1.0 - (common / shorter)
        return diff_ratio >= min_diff_ratio

    def run_learning(self, ticket_id, ticket_subject, template_name, workflow_name,
                     original_output, final_output, output_type="draft_response",
                     source="po_edit"):
        """Run Learning Agent if changes are meaningful.

        source: "po_edit" (PO edited draft in the tool) or "freshdesk_reply"
        (learned from a direct Freshdesk reply the agent sent without using the tool)."""
        if not self.db:
            return []
        if not self.should_learn(original_output, final_output):
            logger.info(f"Learning Agent skipped for ticket {ticket_id}: changes too small")
            return []

        start = time.time()
        try:
            result, usage = learning_agent(
                self.client, self.db, ticket_id, ticket_subject,
                template_name, workflow_name,
                original_output, final_output, output_type,
                source=source,
                llm_router=self.llm_router,
                include_usage=True,
            )
            duration = int((time.time() - start) * 1000)
            self._log_agent("learning_agent", ticket_id, 0, len(str(result)), duration, usage=usage)
            return result
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            self._log_agent("learning_agent", ticket_id, 0, 0, duration, False, e)
            return []

    # ── Batch KB optimization ─────────────────────────────────────────────────

    def preload_kb_index(self, full_kb_context, terminology_context=""):
        """Pre-index the KB once for batch processing (called before processing multiple tickets).
        Stores the raw KB + terminology so individual ticket calls can skip the full reload."""
        self._batch_kb_cache = {
            "kb": full_kb_context,
            "terminology": terminology_context,
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.info(f"KB pre-indexed for batch: {len(full_kb_context)} chars")

    def get_kb_brief_batched(self, ticket_id, ticket_subject, ticket_summary, code_context_summary=""):
        """Get KB brief using pre-loaded batch KB (avoids reloading KB for each ticket)."""
        if not self._batch_kb_cache.get("kb"):
            return ""
        return self.get_kb_brief(
            ticket_id, ticket_subject, ticket_summary,
            self._batch_kb_cache["kb"],
            self._batch_kb_cache.get("terminology", ""),
            code_context_summary
        )

    # ── Monitoring ────────────────────────────────────────────────────────────

    def get_agent_logs(self, ticket_id=None, limit=50):
        """Get recent agent execution logs."""
        if self.db:
            try:
                if ticket_id:
                    return self.db.execute("""
                        SELECT * FROM agent_logs WHERE ticket_id = ? ORDER BY created_at DESC LIMIT ?
                    """, (ticket_id, limit)).fetchall()
                else:
                    return self.db.execute("""
                        SELECT * FROM agent_logs ORDER BY created_at DESC LIMIT ?
                    """, (limit,)).fetchall()
            except Exception:
                pass
        return self._agent_log[-limit:]

    def get_cost_summary(self, days=7):
        """Get cost summary for the last N days."""
        if not self.db:
            return {}
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            rows = self.db.execute("""
                SELECT agent_name,
                       COUNT(*) as calls,
                       SUM(input_tokens) as total_input_tokens,
                       SUM(output_tokens) as total_output_tokens,
                       SUM(estimated_cost) as total_cost,
                       AVG(duration_ms) as avg_duration_ms,
                       SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes
                FROM agent_logs WHERE created_at > ?
                GROUP BY agent_name ORDER BY total_cost DESC
            """, (cutoff,)).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_lessons(self, active_only=True, limit=50):
        """Get stored lessons for dashboard display."""
        if not self.db:
            return []
        try:
            if active_only:
                return self.db.execute("""
                    SELECT * FROM agent_lessons WHERE active = 1
                    ORDER BY created_at DESC LIMIT ?
                """, (limit,)).fetchall()
            else:
                return self.db.execute("""
                    SELECT * FROM agent_lessons
                    ORDER BY created_at DESC LIMIT ?
                """, (limit,)).fetchall()
        except Exception as e:
            logger.warning(f"Failed to get lessons: {e}")
            return []


# ═══════════════════════════════════════════════════════════════════════════════
#  6. DB SCHEMA — Tables for agent system
# ═══════════════════════════════════════════════════════════════════════════════

AGENT_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS agent_lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_ticket_id INTEGER,
    template_name TEXT DEFAULT '',
    workflow_name TEXT DEFAULT '',
    category TEXT DEFAULT 'general',
    lesson TEXT NOT NULL,
    importance TEXT DEFAULT 'medium',
    applies_to TEXT DEFAULT 'all',
    output_type TEXT DEFAULT 'draft_response',
    active INTEGER DEFAULT 1,
    rating INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_lessons_template ON agent_lessons(template_name);
CREATE INDEX IF NOT EXISTS idx_lessons_category ON agent_lessons(category);
CREATE INDEX IF NOT EXISTS idx_lessons_active ON agent_lessons(active);

CREATE TABLE IF NOT EXISTS agent_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name TEXT NOT NULL,
    ticket_id INTEGER,
    input_chars INTEGER DEFAULT 0,
    output_chars INTEGER DEFAULT 0,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    estimated_cost REAL DEFAULT 0,
    duration_ms INTEGER DEFAULT 0,
    success INTEGER DEFAULT 1,
    error TEXT,
    provider TEXT DEFAULT '',
    model TEXT DEFAULT '',
    error_message TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agent_logs_ticket ON agent_logs(ticket_id);
CREATE INDEX IF NOT EXISTS idx_agent_logs_agent ON agent_logs(agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_logs_created ON agent_logs(created_at);

CREATE TABLE IF NOT EXISTS agent_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name TEXT NOT NULL,
    ticket_id INTEGER NOT NULL,
    cache_key TEXT NOT NULL,
    result TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_cache_key ON agent_cache(agent_name, ticket_id, cache_key);
CREATE INDEX IF NOT EXISTS idx_cache_expires ON agent_cache(expires_at);
"""


def init_agent_tables(db):
    """Create agent-specific database tables and migrate schema if needed."""
    try:
        db.executescript(AGENT_TABLES_SQL)
        db.commit()

        # ── Schema migration: add columns that may be missing from older DBs ──
        # CREATE TABLE IF NOT EXISTS won't update existing tables, so we need ALTER TABLE.
        _migrations = [
            ("agent_logs", "input_tokens", "ALTER TABLE agent_logs ADD COLUMN input_tokens INTEGER DEFAULT 0"),
            ("agent_logs", "output_tokens", "ALTER TABLE agent_logs ADD COLUMN output_tokens INTEGER DEFAULT 0"),
            ("agent_logs", "estimated_cost", "ALTER TABLE agent_logs ADD COLUMN estimated_cost REAL DEFAULT 0"),
            ("agent_lessons", "rating", "ALTER TABLE agent_lessons ADD COLUMN rating INTEGER DEFAULT 0"),
            ("agent_lessons", "hit_count", "ALTER TABLE agent_lessons ADD COLUMN hit_count INTEGER DEFAULT 1"),
            ("agent_lessons", "last_reinforced_at", "ALTER TABLE agent_lessons ADD COLUMN last_reinforced_at TEXT DEFAULT ''"),
            ("agent_lessons", "source", "ALTER TABLE agent_lessons ADD COLUMN source TEXT DEFAULT 'po_edit'"),
            ("agent_lessons", "pinned", "ALTER TABLE agent_lessons ADD COLUMN pinned INTEGER DEFAULT 0"),
            ("tickets", "last_learned_conv_id", "ALTER TABLE tickets ADD COLUMN last_learned_conv_id INTEGER DEFAULT 0"),
            ("agent_logs", "provider", "ALTER TABLE agent_logs ADD COLUMN provider TEXT DEFAULT ''"),
            ("agent_logs", "model", "ALTER TABLE agent_logs ADD COLUMN model TEXT DEFAULT ''"),
            ("agent_logs", "error_message", "ALTER TABLE agent_logs ADD COLUMN error_message TEXT DEFAULT ''"),
        ]
        for table, col, sql in _migrations:
            try:
                existing = [r[1] for r in db.execute(f"PRAGMA table_info({table})").fetchall()]
                if col not in existing:
                    db.execute(sql)
                    db.commit()
                    logger.info(f"Migration: added {col} to {table}")
            except Exception as me:
                logger.warning(f"Migration {table}.{col} skipped: {me}")

        logger.info("Agent tables initialized successfully.")
    except Exception as e:
        logger.warning(f"Agent table init warning: {e}")
