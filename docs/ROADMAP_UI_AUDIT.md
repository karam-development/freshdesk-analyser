# Roadmap UI Visibility Audit

Audits all roadmap backend features against browser UI visibility and configurability.
Updated after PR `fix-settings-llm-provider-ui` (PR #35) and `roadmap-ui-visibility-audit`.

---

## How to read this table

| Column | Meaning |
|--------|---------|
| **Feature** | Backend setting or UI panel name |
| **Backend exists?** | Feature is implemented in Python/DB |
| **Visible in UI?** | User can see it in the browser |
| **Configurable in UI?** | User can change it from the browser |
| **Location** | Where in the UI it lives |
| **Status** | See legend below |
| **Gap** | What was missing before this audit |
| **Fix in this PR?** | Whether the gap is addressed in the current PR |
| **Deferred reason** | Why a gap is intentionally left |

**Status legend:** `OK` · `Fixed in this PR` · `Read-only by design` · `Missing` · `Deferred` · `Not applicable`

---

## A. LLM / Provider

| Feature | Backend exists? | Visible in UI? | Configurable in UI? | Location | Status | Gap | Fix in this PR? | Deferred reason |
|---------|----------------|----------------|---------------------|----------|--------|-----|-----------------|-----------------|
| `llm_provider` | ✅ | ✅ | ✅ | Settings → AI Provider Configuration | OK | Was missing before PR #35 | Fixed in PR #35 | — |
| `llm_api_key` | ✅ | ✅ (key-is-set indicator, no value) | ✅ | Settings → AI Provider Configuration | OK | Was missing before PR #35 | Fixed in PR #35 | — |
| `llm_base_url` | ✅ | ✅ | ✅ | Settings → AI Provider Configuration | OK | Was missing before PR #35 | Fixed in PR #35 | — |
| `llm_fast_model` | ✅ | ✅ | ✅ | Settings → AI Provider Configuration | OK | Already present | No | — |
| `llm_main_model` | ✅ | ✅ | ✅ | Settings → AI Provider Configuration | OK | Already present | No | — |
| `anthropic_api_key` (legacy) | ✅ | ✅ | ✅ | Settings → Legacy Anthropic Configuration | OK | Relabeled as legacy in PR #35 | Fixed in PR #35 | — |
| `agent_model_config` (per-agent) | ✅ | ✅ (read-only table) | Read-only in UI | Agents → Agent Model Configuration | Fixed in this PR | Table was never rendered despite data being passed | Yes | Edit via API `/api/agents/model-config/<name>` |
| LLMRouter provider/model in agent logs | ✅ | ✅ | Not applicable | Agents → Cost by Agent | OK | Agent logs show provider/model | No | — |

---

## B. Semantic RAG

| Feature | Backend exists? | Visible in UI? | Configurable in UI? | Location | Status | Gap | Fix in this PR? | Deferred reason |
|---------|----------------|----------------|---------------------|----------|--------|-----|-----------------|-----------------|
| `semantic_rag_enabled` | ✅ | ✅ | ✅ | Settings → Semantic RAG Configuration | Fixed in this PR | No UI field existed | Yes | — |
| `semantic_rag_provider` | ✅ | ✅ | ✅ | Settings → Semantic RAG Configuration | Fixed in this PR | No UI field existed | Yes | — |
| `semantic_embedding_model` | ✅ | ✅ | ✅ | Settings → Semantic RAG Configuration | Fixed in this PR | No UI field existed | Yes | — |
| `semantic_rag_top_k` | ✅ | ✅ | ✅ | Settings → Semantic RAG Configuration | Fixed in this PR | No UI field existed | Yes | — |
| `semantic_rag_min_score` | ✅ | ✅ | ✅ | Settings → Semantic RAG Configuration | Fixed in this PR | No UI field existed | Yes | — |
| `kb_embedding_cache` record count | ✅ | ✅ (read-only status block) | Not applicable (read-only) | Settings → Semantic RAG Cache | Fixed in this PR | No cache visibility | Yes | — |
| Keyword / semantic / hybrid source badges | ✅ | ✅ | Not applicable (display-only) | Ticket → Relevant KB Evidence | OK | Already present (PR #34) | No | — |
| Experimental / cost warning | ✅ | ✅ | Not applicable | Settings → Semantic RAG Configuration | Fixed in this PR | No user-facing warning | Yes | — |

---

## C. Readiness

| Feature | Backend exists? | Visible in UI? | Configurable in UI? | Location | Status | Gap | Fix in this PR? | Deferred reason |
|---------|----------------|----------------|---------------------|----------|--------|-----|-----------------|-----------------|
| System Readiness card | ✅ | ✅ | Not applicable (read-only) | Settings (top of page) | OK | — | No | — |
| System Readiness API | ✅ | ✅ | Not applicable | `GET /api/system-readiness` | OK | — | No | — |
| Security Readiness card | ✅ | ✅ | Not applicable (read-only) | Settings (top of page) | OK | — | No | — |
| Security Readiness API | ✅ | ✅ | Not applicable | `GET /api/security-readiness` | OK | — | No | — |
| No secret values in readiness output | ✅ | ✅ | Not applicable | Both readiness cards | OK | — | No | — |

---

## D. Ticket Review Panels

| Feature | Backend exists? | Visible in UI? | Configurable in UI? | Location | Status | Gap | Fix in this PR? | Deferred reason |
|---------|----------------|----------------|---------------------|----------|--------|-----|-----------------|-----------------|
| PM Decision | ✅ | ✅ | Read-only | Ticket detail → PM Decision | OK | Has empty state | No | — |
| PM Guard Review | ✅ | ✅ | Read-only | Ticket detail → PM Guard Review | OK | Has empty state | No | — |
| Existing Solution Review | ✅ | ✅ | Read-only | Ticket detail → Existing Solution Review | OK | Has empty state | No | — |
| Relevant KB Evidence | ✅ | ✅ | Read-only | Ticket detail → Relevant KB Evidence | OK | Has empty state | No | — |
| KB Evidence Quality | ✅ | ✅ | Read-only | Ticket detail → KB Evidence Quality | OK | Has empty state | No | — |
| KB Evidence Snapshots by Flow | ✅ | ✅ | Read-only | Ticket detail → KB Evidence Snapshots by Flow | OK | Has "No stored KB evidence snapshots yet" | No | — |
| KB Snapshot Diff Summary | ✅ | ✅ | Read-only | Ticket detail → KB Snapshot Diff Summary | OK | Has "No KB snapshot comparisons available yet" | No | — |
| Structured PM Lessons Used | ✅ | ✅ | Read-only | Ticket detail → Structured PM Lessons Used | Fixed in this PR | Panel was hidden with no else state when no lessons | Yes | — |
| Safe to Send Review | ✅ | ✅ | Read-only | Ticket detail → Safe to Send Review | OK | Has "No safe-to-send review available" empty state | No | — |
| Safe-to-send draft banner | ✅ | ✅ | Read-only | Ticket detail → draft area | OK | — | No | — |

---

## E. Learning / Agents

| Feature | Backend exists? | Visible in UI? | Configurable in UI? | Location | Status | Gap | Fix in this PR? | Deferred reason |
|---------|----------------|----------------|---------------------|----------|--------|-----|-----------------|-----------------|
| Structured PM Lessons (agents page) | ✅ | ✅ | Read-only | Agents → Structured PM Lessons | OK | — | No | — |
| Agent lessons (research) | ✅ | ✅ | Rate/toggle | Agents → Lessons Learned | OK | — | No | — |
| Agent cost/call logs | ✅ | ✅ | Read-only | Agents → Cost by Agent | OK | — | No | — |
| `agent_model_config` table | ✅ | ✅ (read-only) | Read-only in UI | Agents → Agent Model Configuration | Fixed in this PR | Data was passed to template but never rendered | Yes | Edit via API |
| Agent dashboard overview | ✅ | ✅ | Read-only | `/agents` | OK | — | No | — |

---

## F. Copy / Review Actions

| Feature | Backend exists? | Visible in UI? | Configurable in UI? | Location | Status | Gap | Fix in this PR? | Deferred reason |
|---------|----------------|----------------|---------------------|----------|--------|-----|-----------------|-----------------|
| Copy clean draft button | ✅ | ✅ | User action | Ticket detail → draft area | OK | — | No | — |
| Copy warning confirm (needs_review / do_not_send) | ✅ | ✅ | User action | Ticket detail → draft area | OK | — | No | — |
| Regenerate draft with PM constraints | ✅ | ✅ | User action | Ticket detail → draft area | OK | — | No | — |
| No auto-send | ✅ | ✅ (banners) | Not applicable | Ticket detail | OK | "Do not send yet" banner always shown | No | By design — human review required |

---

## Summary

| Category | Total features audited | OK (no gap) | Fixed in this PR | Deferred |
|----------|----------------------|-------------|------------------|----------|
| A. LLM / Provider | 8 | 6 | 2 (PR #35) | 0 |
| B. Semantic RAG | 8 | 1 | 7 | 0 |
| C. Readiness | 5 | 5 | 0 | 0 |
| D. Ticket panels | 10 | 9 | 1 | 0 |
| E. Learning / Agents | 5 | 4 | 1 | 0 |
| F. Copy / Review | 4 | 4 | 0 | 0 |
| **Total** | **40** | **29** | **11** | **0** |

---

## Deferred items

No gaps were deferred in this audit. All identified UI gaps are either fixed in this PR or in PR #35.

Items that are intentionally read-only by design (not a gap):
- `agent_model_config` editing — available via API; UI shows read-only table
- Readiness cards — diagnostic, never editable
- All ticket review panels — deterministic, never editable by user

---

*Last updated: `roadmap-ui-visibility-audit` branch.*
*See also: `docs/SEMANTIC_KB_RETRIEVAL_PLAN.md`, `docs/PRODUCTION_CHECKLIST.md`*
