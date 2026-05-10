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
- [ ] `SECRET_KEY` environment variable — **must** be set to a strong random value; never use the default or a placeholder

### Optional but recommended
- [ ] `freshdesk_country` — country filter to narrow ticket scope
- [ ] `freshdesk_statuses` — which ticket statuses to process (default: Open, In Progress, Resolved, Assign to 3L)
- [ ] `llm_main_model` / `llm_fast_model` — override default model names if needed
- [ ] At least one Knowledge Base entry — for KB evidence retrieval to be useful

---

## Secrets Handling

- **Never commit API keys** to the repository. Use environment variables or the app's settings DB.
- The app stores settings in SQLite. The DB file (`freshdesk.db` or configured path) **must not be publicly accessible**.
- The `SECRET_KEY` Flask secret **must** be set via the `SECRET_KEY` environment variable in production. The default value is not suitable for multi-worker deploys or any team-accessible environment.
- If a `SECRET_KEY` default/placeholder is detected, the Security Readiness card on the Settings page will flag it as a failure.
- API keys are never exposed in logs, API responses, or the UI. Both the system readiness and security readiness reports only show present/missing.
- **Do not include API keys in screenshots, screen recordings, Notion exports, or Jira descriptions.**
- **Rotate any key that has been accidentally exposed** (committed to git, shared in a screenshot, etc.) immediately.
- Restrict app access to trusted users or a trusted network; the app has no login/authentication in its current scope.

---

## Debug Mode

- **Disable debug mode** (`FLASK_DEBUG=0`, `APP_DEBUG=0`) in any team-accessible or production deployment.
- Running with debug enabled exposes an interactive debugger and detailed stack traces to anyone who can reach the app.
- The Security Readiness card flags `FLASK_DEBUG=1` or `APP_DEBUG=1` as a failure in production-like environments.

---

## Database Backup

- [ ] Back up the SQLite DB file before any schema migration or deployment
- [ ] The DB stores tickets, settings, knowledge base, agent configs, and PM decisions
- [ ] For Render deployments: use a persistent disk or export the DB regularly — ephemeral instances lose the DB on redeploy
- [ ] Verify backups are restorable before production launch
- [ ] Keep DB backups access-controlled — they contain API keys and ticket content

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

## Security Readiness Check

Before any demo or team deployment:

- [ ] Open Settings → Security Readiness card shows **Secure enough for demo** or better
- [ ] `GET /api/security-readiness` returns `{"ok": true, "report": {...}}` with no secret values in output
- [ ] SECRET_KEY is set and non-default
- [ ] Debug mode is disabled
- [ ] DB file is stored in a private directory

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

## Semantic RAG (optional feature)

Semantic KB retrieval is **disabled by default**.  To enable it:

- [ ] Configure LLM provider and API key in Settings (OpenAI required for embeddings)
- [ ] Set `semantic_rag_enabled` = `true` in Settings (or via DB)
- [ ] Understand that embedding API calls will incur cost (per-token billing)
- [ ] Embeddings are cached in `kb_embedding_cache`; first-run will call the API for all KB entries
- [ ] Keyword retrieval remains the fallback; any embedding failure falls back silently
- [ ] Do NOT enable in production without testing on a non-critical environment first
- [ ] Do NOT expose the embedding API key in logs, URLs, or error messages

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
| Semantic RAG / embeddings | Available behind `semantic_rag_enabled=true` flag; off by default; requires OpenAI API key |
| Multi-provider fallback | Silent fallback removed; explicit failure on provider error |
| Real-time Freshdesk webhooks | Polling only; webhooks deferred |
| Role-based access control | Single-user app in current scope |
| Encrypted secrets storage | SQLite settings DB; use environment variables for keys; encryption deferred |
| Automated smoke test suite | Manual smoke tests defined above |
| Secrets rotation tooling | Manual rotation process; tooling deferred |

---

*Last updated: security-hardening-secrets-and-access-safety release.*
*See also: `docs/TEAM_DEMO_GUIDE.md`, `docs/LIVE_DEMO_SMOKE_TEST.md`*
