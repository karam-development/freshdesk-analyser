# Team Demo Guide — Freshdesk AI Analyser

A practical reference for running an internal team demo.

---

## What the App Does

The Freshdesk AI Analyser is a **human-in-the-loop** assistant for product support workflows. It:

- Fetches open tickets from Freshdesk and analyses them with an LLM
- Classifies tickets (bug, feature, how-to, etc.) and assigns confidence and risk scores
- Generates draft replies based on KB entries, project instructions, and writing style
- Runs a multi-layer PM decision review (guards, existing solutions, KB evidence)
- Produces a Safe-to-Send review before any draft is copied or sent
- Never auto-sends anything — every action requires human approval

---

## What Is Safe / Not Safe

| Safe | Not safe |
|------|----------|
| Reading and analysing tickets | Auto-sending replies |
| Generating AI drafts | Bypassing PM review |
| Copying drafts (with warning if flagged) | Ignoring "Do not send yet" banners |
| Reviewing KB evidence and quality | Treating AI drafts as authoritative |
| Running the system readiness check | Skipping Freshdesk domain/API key configuration |

> **Rule:** AI drafts are suggestions only. A human must review and approve before any reply is sent via Freshdesk.

---

## Demo Setup Checklist

Before the demo, verify:

- [ ] LLM provider is configured in Settings (OpenAI or Anthropic)
- [ ] LLM API key is set in Settings
- [ ] Freshdesk domain and API key are configured
- [ ] At least one KB entry exists (for KB evidence to appear)
- [ ] System Readiness card on the Settings page shows **Ready** or **Degraded** (not **Needs configuration**)
- [ ] At least one ticket is visible in the inbox
- [ ] Agent model configs are seeded (visible on the Agents page)

---

## Suggested Demo Flow

1. **Open the Settings page** → show the System Readiness card (score, checks, status badge)
2. **Go to the inbox** → show the ticket list with classification badges, risk levels, and confidence scores
3. **Open a ticket** → walk through each panel top-to-bottom:
   - PMDecision
   - PM Guard Review
   - Existing Solution Review
   - KB Evidence
   - KB Evidence Quality
   - KB Snapshot Diff
   - Safe-to-Send Review
   - Draft Banner + Draft area
4. **Demonstrate draft generation** → click "Generate Drafts", show the AI draft
5. **Show the Safe-to-Send banner** → explain what "Safe to send" vs "Needs review" vs "Do not send yet" means
6. **Attempt to copy a flagged draft** → show the browser confirmation dialog (human-review gate)
7. **Show the Agents page** → explain per-agent model configuration (provider, model, temperature)

---

## What to Show on the Ticket Detail Page

### PMDecision
The top-level product classification: `build`, `reject`, `defer`, or `needs_info`. Includes confidence score and rationale. This drives how the draft is framed.

### PM Guard Review
A set of named guardrails that check whether the draft meets product standards. Each guard returns pass/warn/fail with a reason.

### Existing Solution Review
Checks if the ticket is asking about a feature that already exists in the product. Prevents unnecessary "we'll build this" replies.

### KB Evidence
Retrieved knowledge base entries relevant to the ticket. Shows title, category, similarity, and supporting snippets. Drives the draft context.

### KB Evidence Quality
Rates the retrieved KB evidence: completeness, recency, consistency. Flags low-quality or contradictory evidence.

### KB Snapshot Diff
Compares the current KB evidence to a previous snapshot for the same ticket. Shows what changed between analyses.

### Safe-to-Send Review
The final pre-send gate. Scores 0–100 and returns one of three statuses:
- **Safe to send** — no blocking issues
- **Needs review** — warnings present; proceed with caution
- **Do not send yet** — blocking issues; resolve before copying

### Draft Banner
Displayed in the draft area. Shows the Safe-to-Send badge, score, top reasons, and a copy warning if the draft is flagged.

---

## How to Explain LLMRouter

LLMRouter is the provider-agnostic routing layer:
- Reads the configured provider (`openai`, `anthropic`, etc.) from the DB
- Selects the model and temperature from `agent_model_config` (per agent, per ticket type)
- All main text-generation paths go through the router — no hardcoded provider
- Vision/screenshot paths still use the legacy Anthropic client (multimodal limitation)
- If the API key is missing or the provider call fails, the app returns a clear error — it does **not** silently fall back

---

## Known Limitations

- Vision analysis (screenshots) requires an Anthropic key regardless of the configured LLM provider
- Vision/screenshot analysis requires an Anthropic key regardless of the configured LLM provider (multimodal requirement)
- No real-time Freshdesk webhook support; ticket fetch is triggered manually or by the scheduled run
- Safe-to-Send scores are heuristic-based (no LLM call in the review itself)
- KB snapshot diffs require at least two analysis runs on the same ticket

---

## What Is Intentionally Not Automated

| What | Why |
|------|-----|
| Auto-send replies | Human review is required; AI drafts can be wrong |
| Auto-approve PM decisions | Product judgement requires human context |
| Auto-delete tickets or KB entries | Destructive actions require explicit user intent |
| Auto-create Jira issues | Jira links require human review of scope |
| Auto-merge or auto-deploy | No CI/CD automation in scope |

---

## Troubleshooting

### Missing `llm_api_key`
- System Readiness shows "LLM API key missing"
- Ticket analysis returns `[ROUTER ERROR]` in the analysis field
- Fix: go to Settings → AI Provider Configuration → set the API key

### Freshdesk connection issue
- Inbox shows no tickets or shows a fetch error
- Go to Settings → Freshdesk Configuration → click "Test Connection"
- Check that the domain and API key are correct

### No KB evidence
- KB Evidence panel shows "No relevant entries found"
- Fix: add entries in Settings → Knowledge Base

### Router provider error
- Analysis or draft generation returns an error banner
- Check: Settings → Agents → verify the agent model config is seeded
- Check: the LLM provider and API key are correct
- Check: the model name matches a model the provider supports

---

*This guide covers the app as of the production-hardening release. See `docs/PRODUCTION_CHECKLIST.md` for deployment requirements.*
