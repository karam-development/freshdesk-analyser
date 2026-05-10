# Agent Wiring Matrix

**Date:** 2026-05-10
**Branch:** wire-all-registered-agents
**Goal:** Every registered agent must run in a real workflow with real input, real output, and stored results.

---

## Wiring Status Key

| Status | Meaning |
|---|---|
| `wired_active` | Agent was already wired and running in production before this PR |
| `wired_now` | Agent was not wired before; has a call site, runs LLM, output stored and displayed |
| `partially_wired` | Agent runs but output is not yet stored or not used downstream |
| `blocked` | Cannot be wired without a specific external dependency |

---

## Full Wiring Matrix

### 1. `classification_agent`

| Field | Value |
|---|---|
| **Purpose** | Pre-analysis fast ticket classifier. Runs before main_analysis_agent to produce initial classification + confidence + reason. Reduces main agent token usage. |
| **Trigger** | Automatically at start of ticket analysis flow (`/ticket/<id>/prepare-analysis` and `/run`). |
| **Input** | Ticket subject, ticket description (first 2000 chars of compiled thread). |
| **Output** | JSON: `{classification, confidence, reason, ticket_type}` |
| **Output stored** | `agent_runs` table: `flow=analysis`, `output_json=<classification JSON>` |
| **Output displayed** | Ticket detail → Agent Run Status table; Agent Briefs section (classification + confidence) |
| **Downstream consumer** | `main_analysis_agent` (classification hint injected into enhanced_kb context) |
| **Runtime status** | `wired_now` |
| **Call site** | `AgentOrchestrator.run_classification()` → called in `prepare_analysis` route and `run` background job |

---

### 2. `summary_agent`

| Field | Value |
|---|---|
| **Purpose** | Produces a clean, structured ticket summary from the full conversation thread. Better than the raw `analysis` field as input to downstream agents. |
| **Trigger** | Automatically at start of ticket analysis flow, alongside classification_agent. |
| **Input** | Full compiled ticket thread (Freshdesk conversations), ticket subject. |
| **Output** | Structured text: `{summary, user_request, affected_template, affected_workflow, client_context}` |
| **Output stored** | `agent_runs` table: `flow=analysis`, `output_summary=<first 500 chars>`, `output_json=<full output>` |
| **Output displayed** | Ticket detail → Agent Briefs section |
| **Downstream consumer** | Passed as `summary_brief` to `feasibility_agent`; injected into `enhanced_kb` for `main_analysis_agent` and `draft_response_agent` |
| **Runtime status** | `wired_now` |
| **Call site** | `AgentOrchestrator.run_summary()` → called in `prepare_analysis` and `generate_drafts` routes |

---

### 3. `kb_agent`

| Field | Value |
|---|---|
| **Purpose** | Reads the full Knowledge Base and extracts only the relevant entries for the ticket. Prevents main agent from being overwhelmed by full KB. |
| **Trigger** | Automatically in parallel prep phase of analysis and draft generation. |
| **Input** | Ticket subject, ticket summary, full KB context (from `knowledge_base` table), terminology context, code context summary. |
| **Output** | Structured KB brief: relevant accounts, reconciliation rules, Liquid constraints, accounting validation, precedents. |
| **Output stored** | `agent_cache` table (4-hour TTL), `agent_logs` table (duration/cost). |
| **Output displayed** | Ticket detail → Relevant KB Evidence card (raw); Evidence & Diagnostics → KB Evidence Quality card. |
| **Downstream consumer** | `main_analysis_agent`, `draft_response_agent`, `feasibility_agent`, `qa_agent` |
| **Runtime status** | `wired_now` |
| **Call site** | `AgentOrchestrator.get_kb_brief()` → `run_preparation_agents_parallel()` |

---

### 4. `code_agent`

| Field | Value |
|---|---|
| **Purpose** | Analyses Silverfin Liquid template code, produces plain-language functional brief (no raw code in output). Identifies current behaviour, reference patterns, and existing solutions. |
| **Trigger** | Automatically in parallel prep phase, after KB brief is available. |
| **Input** | Ticket subject, ticket summary, full template code (from file system), KB brief. |
| **Output** | Plain-language code brief: template overview, current behaviour, reference patterns, existing solution check, feasibility hints. |
| **Output stored** | `agent_cache` table (4-hour TTL), `agent_logs` table. If no code context: `status=skipped`, reason stored in `agent_runs`. |
| **Output displayed** | Ticket detail → Agent Briefs section (code analysis summary) |
| **Downstream consumer** | `feasibility_agent`, `main_analysis_agent`, `draft_response_agent` |
| **Runtime status** | `wired_now` (skipped with reason if no template code found) |
| **Call site** | `AgentOrchestrator.get_code_brief()` → `run_preparation_agents_parallel()` |

---

### 5. `research_agent`

| Field | Value |
|---|---|
| **Purpose** | Searches past ticket history and agent_lessons for similar resolved issues and reusable patterns. |
| **Trigger** | Automatically in parallel prep phase (runs concurrently with KB agent). |
| **Input** | Ticket subject, ticket summary, template name, workflow name, Jira context, pre-fetched similar tickets and lessons from DB. |
| **Output** | Research brief: similar ticket summaries, key lessons, precedents relevant to this ticket. |
| **Output stored** | `agent_logs` table (no cache — needs fresh DB data). |
| **Output displayed** | Used directly in `enhanced_kb` for main agent. |
| **Downstream consumer** | `main_analysis_agent`, `draft_response_agent` |
| **Runtime status** | `wired_now` |
| **Call site** | `AgentOrchestrator.get_research_brief()` → `run_preparation_agents_parallel()` |

---

### 6. `feasibility_agent`

| Field | Value |
|---|---|
| **Purpose** | Dedicated technical feasibility assessment. Combines code_brief + kb_brief to produce a structured feasibility verdict: feasible/infeasible/workaround_exists/setting_exists. |
| **Trigger** | Automatically after `run_preparation_agents_parallel()` completes (has code_brief + kb_brief available). |
| **Input** | Ticket subject, summary_brief (from summary_agent), code_brief (from code_agent), kb_brief (from kb_agent). |
| **Output** | JSON: `{verdict, reason, conditions, existing_solution, dev_effort_estimate}` |
| **Output stored** | `agent_runs` table: `flow=analysis`, `output_json=<feasibility JSON>` |
| **Output displayed** | Ticket detail → Agent Briefs section (feasibility verdict + reason) |
| **Downstream consumer** | `main_analysis_agent` (feasibility verdict injected into enhanced_kb, influences PMDecision) |
| **Runtime status** | `wired_now` |
| **Call site** | `AgentOrchestrator.run_feasibility()` → called in `prepare_analysis` and `generate_drafts` routes |

---

### 7. `main_analysis_agent`

| Field | Value |
|---|---|
| **Purpose** | Core analysis agent. Produces ticket classification, RICE scores, risk level, PM decision context. Consumes all upstream briefs. |
| **Trigger** | After all prep agents complete (classification, summary, kb, code, research, feasibility). |
| **Input** | Full compiled thread + enhanced_kb (containing all agent briefs) + project instructions + terminology context. |
| **Output** | Structured analysis JSON: classification, summary, risk_level, rice_score, pm_decision context. |
| **Output stored** | `tickets.analysis` column (raw JSON), `tickets.pm_decision` column. |
| **Output displayed** | Ticket detail → AI Analysis card, PM Decision card, PM/PO Summary card. |
| **Downstream consumer** | `draft_response_agent`, `qa_agent`, `prd_agent`, PM/PO review flow |
| **Runtime status** | `wired_now` |
| **Call site** | `analyze_and_draft_ai()` in app.py → called in `/run` background job and `prepare_analysis` route |

---

### 8. `draft_response_agent`

| Field | Value |
|---|---|
| **Purpose** | Generates FR and EN client-facing draft responses using PMDecision, all agent briefs, support explanation guidance, and structured PM lessons. |
| **Trigger** | Manual: "Generate Draft" button on approved or declined tickets. Also triggered by PM-constrained regeneration. |
| **Input** | Full compiled thread + enhanced_kb (all briefs) + PMDecision + support explanation + structured lessons + KB evidence. |
| **Output** | Draft response: `--- CLIENT RESPONSE ---`, `--- INTERNAL NOTE ---`, `--- BACKLOG TICKET ---` sections in FR and EN. |
| **Output stored** | `tickets.draft_response` (FR), `tickets.draft_response_en` (EN). |
| **Output displayed** | Ticket detail → Draft Response section (rich editors). |
| **Downstream consumer** | `qa_agent`, `learning_agent` (after PO edits), `safe_to_send_review` |
| **Runtime status** | `wired_now` |
| **Call site** | `generate_draft_response()` in app.py → called in `generate_drafts` route |

---

### 9. `qa_agent`

| Field | Value |
|---|---|
| **Purpose** | Reviews generated drafts for quality, tone, completeness, PM-constraint compliance, accounting accuracy. Flags issues. May trigger one regeneration cycle. |
| **Trigger** | Automatically after draft_response_agent completes. Also manually via PM Guard review. |
| **Input** | Agent output text (analysis or draft), output_type, ticket subject, KB brief. |
| **Output** | JSON: `{passed, score, critical_issues, warnings, suggestions, blind_agreement, accounting_validated, summary}` |
| **Output stored** | `tickets.safe_to_send_review` (QA result influences STS), `agent_logs` table. |
| **Output displayed** | Ticket detail → Safe to Send Review card, PM Guard Review card. |
| **Downstream consumer** | `draft_response_agent` (retry if critical issues), `safe_to_send_review` |
| **Runtime status** | `wired_now` |
| **Call site** | `AgentOrchestrator.run_qa()` / `run_qa_with_retry()` → called in `generate_drafts` and `regenerate_draft_pm` routes |

---

### 10. `learning_agent`

| Field | Value |
|---|---|
| **Purpose** | Extracts reusable lessons from PO edits and Freshdesk replies. Stores them in `agent_lessons` and `pm_structured_lessons` for future drafts. |
| **Trigger** | After PO approves/edits: triggered by `po-decision` route and `reply-ticket` route. Also triggered by `reply_scanner_agent` when corrections are found. |
| **Input** | Original AI output, PO's final edited version, ticket metadata (subject, template, workflow), source tag (po_edit / freshdesk_reply). |
| **Output** | Array of structured lessons with category, instruction, importance, applies_to. |
| **Output stored** | `agent_lessons` table + `pm_structured_lessons` table. `agent_logs` table for cost. |
| **Output displayed** | Agents page → Lessons Learned section. Ticket detail → Structured PM Lessons Used (in Diagnostics). |
| **Downstream consumer** | `research_agent`, `draft_response_agent` (lessons injected into future prompts) |
| **Runtime status** | `wired_now` |
| **Call site** | `AgentOrchestrator.run_learning()` → called in `po-decision`, `update` (draft save), `reply-ticket` routes |

---

### 11. `prd_agent`

| Field | Value |
|---|---|
| **Purpose** | Generates structured Product Requirements Documents for feature requests and complex changes. |
| **Trigger** | Manual: "Prepare PRD Analysis" or "Generate Document" buttons on ticket detail page. |
| **Input** | Full compiled thread + all agent briefs + PMDecision + PO draft (if available) + project instructions. |
| **Output** | PRD JSON: template_name, workflow, problem_statement, current_behaviour, new_behaviour, test_scenarios, complexity assessment. |
| **Output stored** | `tickets.prd_analysis` column. |
| **Output displayed** | Ticket detail → PRD/Document section. Generated as PDF/PPTX document via export. |
| **Downstream consumer** | `qa_agent` (PRD QA pass), document export |
| **Runtime status** | `wired_now` |
| **Call site** | `generate_prd_analysis()` in app.py → called in `prepare_analysis` and `generate_doc` routes |

---

### 12. `reply_scanner_agent`

| Field | Value |
|---|---|
| **Purpose** | Scans incoming Freshdesk conversations for PO corrections, lesson signals, approval confirmations, and client clarifications to feed the learning loop. |
| **Trigger** | Manual: "Scan Replies" button on ticket detail page. Route: `POST /ticket/<id>/scan-replies`. |
| **Input** | Ticket subject, full conversation thread (fetched live from Freshdesk API). |
| **Output** | JSON: `{corrections, lesson_signals, approval_detected, action_required, scan_summary}` |
| **Output stored** | `agent_runs` table: `flow=learning`, `output_json=<scan results>`. If corrections found, triggers `learning_agent`. |
| **Output displayed** | Ticket detail → Agent Run Status table; scan results shown in flash message and Agent Briefs. |
| **Downstream consumer** | `learning_agent` (if corrections detected) |
| **Runtime status** | `wired_now` |
| **Call site** | `AgentOrchestrator.run_reply_scanner()` → `POST /ticket/<id>/scan-replies` route |

---

### 13. `jira_agent`

| Field | Value |
|---|---|
| **Purpose** | Searches Jira for related issues and produces an LLM-summarized context brief. Replaces raw Jira text dump with structured, actionable context for downstream agents. |
| **Trigger** | Automatically when Jira is configured and `search_jira_for_ticket()` returns results during analysis or draft generation. |
| **Input** | Ticket subject, raw Jira search results text (from existing `search_jira_for_ticket()` REST call), PM context (if available). |
| **Output** | Structured Jira brief: linked issues summary, development status, relevant bug/feature context. |
| **Output stored** | `agent_runs` table: `flow=analysis`, `output_json=<jira brief>`. |
| **Output displayed** | Ticket detail → Agent Briefs section (Jira context); Agent Run Status table. |
| **Downstream consumer** | `research_agent`, `main_analysis_agent`, `draft_response_agent` (replaces raw jira_context string) |
| **Runtime status** | `wired_now` (skipped with reason if Jira not configured) |
| **Call site** | `AgentOrchestrator.run_jira_summary()` → called in `prepare_analysis` and `generate_drafts` routes after `search_jira_for_ticket()` |

---

### 14. `notification_agent`

| Field | Value |
|---|---|
| **Purpose** | Generates internal notification text when a ticket becomes high-risk, has an unsafe draft, is blocked, or needs escalation. Preview only — no external sends. |
| **Trigger** | Automatically after analysis completes when `risk_level=high` or safe-to-send score < 60. Also callable via `GET /ticket/<id>/notification-preview`. |
| **Input** | Ticket subject, classification, risk_level, PM decision summary, STS score (if available). |
| **Output** | JSON: `{severity, headline, body, recommended_action, channels_suggested}` |
| **Output stored** | `agent_runs` table: `flow=notification`, `output_json=<notification JSON>`. |
| **Output displayed** | Ticket detail → Agent Run Status table; notification preview shown when risk_level is high. |
| **Downstream consumer** | Display only. No external sends in this release. |
| **Runtime status** | `wired_now` (preview-only — no Slack/email send) |
| **Call site** | `AgentOrchestrator.run_notification_preview()` → called in `prepare_analysis` route (high-risk path) and `GET /ticket/<id>/notification-preview` route |

---

### 15. `reporting_agent`

| Field | Value |
|---|---|
| **Purpose** | Generates LLM-powered insights and narrative from ticket metrics. Augments the existing DB-stats reporting page with trend analysis, pattern identification, and recommendations. |
| **Trigger** | Manual: "Generate AI Report Insights" button on `/reporting` page. Route: `POST /api/reports/generate-ai`. |
| **Input** | Ticket metrics JSON (classification distribution, status distribution, resolution times, PO decision breakdown, client breakdown) from DB. |
| **Output** | JSON: `{executive_summary, key_findings, trends, recommendations, risk_flags, period_summary}` |
| **Output stored** | `agent_runs` table: `flow=reporting`, `ticket_id=NULL`, `output_json=<report JSON>`. |
| **Output displayed** | `/reporting` page → "AI Report Insights" section below the charts. |
| **Downstream consumer** | Reporting page display; future Google Sheets/Slides export. |
| **Runtime status** | `wired_now` |
| **Call site** | `AgentOrchestrator.run_report()` → `POST /api/reports/generate-ai` route |

---

### 16. `batch_agent`

| Field | Value |
|---|---|
| **Purpose** | Generates a batch processing plan for multiple tickets (analysis, re-scoring, KB refresh). Outputs a prioritized plan with effort estimates. Execution is separate and manual. |
| **Trigger** | Manual: `POST /api/batch/plan` with ticket IDs or date range. |
| **Input** | JSON array of ticket summaries (subject, classification, risk_level, status, po_decision) for selected/date-ranged tickets. |
| **Output** | JSON: `{batch_plan, priority_order, groups, estimated_total_effort, recommended_actions}` |
| **Output stored** | `agent_runs` table: `flow=batch`, `ticket_id=NULL`, `output_json=<batch plan>`. |
| **Output displayed** | Response JSON on API endpoint (caller displays). |
| **Downstream consumer** | Batch execution controller (future). In this release: plan display only. |
| **Runtime status** | `wired_now` (plan generation only — execution planning, not auto-execution) |
| **Call site** | `AgentOrchestrator.run_batch_plan()` → `POST /api/batch/plan` route |

---

## What Changed From "not_wired" to "wired_now"

| Agent | What Was Missing | What Was Added |
|---|---|---|
| `classification_agent` | No call site | LLM function + runner method + wired into analysis flow |
| `summary_agent` | No call site | LLM function + runner method + wired into analysis + draft flows |
| `feasibility_agent` | No call site | LLM function + runner method + wired into analysis + draft flows |
| `jira_agent` | Direct REST only; no LLM | LLM summarization wrapper + runner method + replaces raw jira_ctx |
| `notification_agent` | No call site | LLM function + runner method + triggered on high-risk analysis |
| `reply_scanner_agent` | No call site | LLM function + runner method + new `POST /ticket/<id>/scan-replies` route |
| `batch_agent` | No call site | LLM function + runner method + new `POST /api/batch/plan` route |
| `reporting_agent` | No call site | LLM function + runner method + new `POST /api/reports/generate-ai` route |

---

## agent_runs Table (new)

Stores workflow-level agent execution records. Different from `agent_logs` (which tracks raw API calls):
- `agent_logs`: cost/performance monitoring per API call
- `agent_runs`: semantic workflow runs — what did this agent actually do on this ticket, what was its output

Fields: `id, ticket_id, agent_name, flow, status, input_summary, output_summary, output_json, error, started_at, finished_at, duration_ms, provider, model`

Status values: `pending`, `running`, `completed`, `failed`, `skipped`

Flows: `analysis`, `draft`, `learning`, `prd`, `notification`, `batch`, `reporting`, `reply_scan`
