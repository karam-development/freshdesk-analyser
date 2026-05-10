# Production Checklist — Freshdesk AI Analyser

A pre-deployment and operational checklist for running the app in a production-like environment.

---

## Required Settings

- [ ] `llm_provider` — set to `openai` or `anthropic`
- [ ] `llm_api_key` — API key for the configured LLM provider
- [ ] `freshdesk_domain` — e.g. `yourcompany.freshdesk.com`
- [ ] `freshdesk_api_key` — Freshdesk API key with read access to the target group
- [ ] `freshdesk_group_id` — the Freshdesk group to monitor
- [ ] `writing_style` — set to match your team's tone (`customer_support` or `professional`)
- [ ] `SECRET_KEY` environment variable — set a strong random value in production (not the default)

### Optional but recommended
- [ ] `freshdesk_country` — country filter to narrow ticket scope
- [ ] `freshdesk_statuses` — which ticket statuses to process (default: Open, In Progress, Resolved, Assign to 3L)
- [ ] `llm_main_model` / `llm_fast_model` — override default model names if needed
- [ ] At least one Knowledge Base entry — for KB evidence retrieval to be useful

---

## Secrets Handling

- **Never commit API keys** to the repository. Use environment variables or the app's settings DB.
- The app stores settings in SQLite. The DB file (`freshdesk.db` or configured path) must not be publicly accessible.
- The `SECRET_KEY` Flask secret must be set via `SECRET_KEY` environment variable in production — the default includes a random suffix but is not suitable for multi-worker deploys.
- API keys are never exposed in logs, API responses, or the UI. The system readiness report only shows present/missing.
- Do not include API keys in screenshots, Notion exports, or Jira descriptions.

---

## Database Backup

- [ ] Back up the SQLite DB file before any schema migration or deployment
- [ ] The DB stores tickets, settings, knowledge base, agent configs, and PM decisions
- [ ] For Render deployments: use a persistent disk or export the DB regularly — ephemeral instances lose the DB on redeploy
- [ ] Verify backups are restorable before production launch

---

## Freshdesk API Safety

- The app only **reads** tickets and conversations from Freshdesk (GET requests)
- Reply and note posting require explicit user action (POST to `/ticket/<id>/reply-ticket` or `/ticket/<id>/post-note`)
- No bulk-reply or auto-send behaviour exists
- Freshdesk rate limits: the app uses `requests` with basic auth; respect Freshdesk's 1000 req/hour limit for standard plans
- The "Test Connection" button in Settings performs a single safe `GET /api/v2/tickets?per_page=1` call

---

## LLM Provider Safety

- All main generation paths go through LLMRouter — no raw API calls outside the router for text-only paths
- Vision/screenshot paths use the legacy Anthropic client (multimodal requirement)
- If the API key is missing or invalid, the app returns a clear error — no silent fallback to another provider
- Token limits are controlled per agent via `agent_model_config` (default: 4 000 for main agents, 10 000 for PRD)
- No streaming — all responses are synchronous with retry logic

---

## Human Review Controls

- [ ] Confirm the "Copy clean draft" button requires human action (it is never auto-triggered)
- [ ] Confirm the "Do not send yet" and "Needs review" banners show copy-confirmation dialogs
- [ ] Confirm no route auto-sends a Freshdesk reply without a human POST request
- [ ] Confirm the `/ticket/<id>/reply-ticket` route is only reachable via a user form submission
- [ ] Jira issue creation requires an explicit POST from the user

---

## Logs and Audit

- The app logs at INFO level to stdout by default
- Key events logged: ticket fetch, analysis start/end, draft generation, router provider/model used, token counts
- API key values are never logged (redacted with `[REDACTED]` in router error paths)
- For production: forward logs to a centralised logging system (e.g. Papertrail, Datadog, CloudWatch)
- [ ] Verify logs are not publicly accessible
- [ ] Verify no PII is logged beyond what is in the Freshdesk ticket itself

---

## Manual Smoke Tests

After deployment, run these checks manually:

- [ ] Open the Settings page → System Readiness card shows **Ready**
- [ ] `GET /api/system-readiness` returns `{"ok": true, "report": {...}}` with no API key values
- [ ] Click "Test Connection" for both Freshdesk and LLM — both pass
- [ ] Open the inbox → at least one ticket loads
- [ ] Open a ticket → PMDecision, KB Evidence, and Safe-to-Send panels all render (or show graceful "unavailable" states)
- [ ] Click "Generate Drafts" → a draft appears; Safe-to-Send banner shows
- [ ] Attempt to copy a flagged draft → browser confirmation dialog appears
- [ ] Agents page loads → agent model configs are visible
- [ ] Settings page saves a non-secret field (e.g. writing style) → flash message appears

---

## Rollback Plan

1. **Code rollback:** `git revert` the offending commit and redeploy; or roll back the Render service to the previous deploy
2. **DB rollback:** restore the SQLite DB backup taken before deployment
3. **Settings rollback:** API keys and settings are stored in the DB; restoring the DB restores all settings
4. **Freshdesk data:** the app only reads Freshdesk data; no Freshdesk data is mutated by the app except via explicit user reply actions

---

## Known Deferred Items

The following items are intentionally not in scope for this release:

| Item | Rationale |
|------|-----------|
| Vision/screenshot LLM routing | Multimodal paths always use legacy Anthropic client (LLMRouter limitation) |
| Semantic RAG / embeddings | Not started; KB retrieval uses keyword/heuristic matching |
| Multi-provider fallback | Silent fallback removed; explicit failure on provider error |
| Real-time Freshdesk webhooks | Polling only; webhooks deferred |
| Role-based access control | Single-user app in current scope |
| Encrypted secrets storage | SQLite settings DB; use environment variables for keys |
| Automated smoke test suite | Manual smoke tests defined above |

---

*Last updated: production-hardening-and-team-demo-polish release.*
*See also: `docs/TEAM_DEMO_GUIDE.md`*
