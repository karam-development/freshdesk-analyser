# Live Demo Smoke Test Checklist

Run through these checks in order before every team demo or production deployment.
Each step is manual unless noted as automated.

> **Automated option:** `python3 scripts/smoke_check.py` runs the route-level checks
> (steps 1–5) automatically. See [scripts/smoke_check.py](../scripts/smoke_check.py).

---

## Pre-flight: App is running

- [ ] App is started: `python3 app.py` (local) or Render service is live
- [ ] No startup errors in the terminal / logs
- [ ] Opening `http://localhost:5000` (or the deployed URL) loads the inbox page

---

## 1. Settings readiness

**What to check:** Settings page shows the System Readiness card with status **Ready**, and the Security Readiness card shows no critical failures.

Steps:
1. Go to **Settings** (`/settings`)
2. Confirm the System Readiness card is visible at the top of the page
3. Confirm status badge shows **Ready** (green)
4. Confirm score is ≥ 85/100
5. Confirm no **fail** checks are listed (warnings are acceptable)
6. Confirm the **Security Readiness** card shows no critical failures (status should not be **Unsafe for production**)

If not ready:
- Set LLM provider and API key in AI Provider Configuration
- Set Freshdesk domain and API key in Freshdesk Configuration
- Add at least one Knowledge Base entry
- Set `SECRET_KEY` environment variable to a strong non-default value
- Disable debug mode (`FLASK_DEBUG=0`) if enabled

Automated equivalent:
```
GET /api/system-readiness   →  {"ok": true, "report": {"status": "ready", "score": ≥85, ...}}
GET /api/security-readiness →  {"ok": true, "report": {"status": "secure_enough_for_demo", ...}}
```

---

## 2. Freshdesk connection

**What to check:** The app can reach the Freshdesk API with the configured credentials.

Steps:
1. Go to **Settings** → Freshdesk Configuration
2. Click **Test Connection**
3. Confirm the result shows: "Connection successful" or a ticket count
4. If it fails: verify the Freshdesk domain (e.g. `silverfin.freshdesk.com`) and API key

> The app only makes read-only `GET` requests to Freshdesk. No tickets are modified.

---

## 3. LLM provider connection

**What to check:** The configured LLM provider (OpenAI or Anthropic) is reachable.

Steps:
1. Go to **Settings** → AI Provider Configuration
2. Click **Test LLM Connection**
3. Confirm the result shows a successful response from the provider
4. If it fails: check the LLM provider name and API key
5. Optionally go to **Agents** (`/agents`) → confirm agent model configs are seeded (at least 3 rows)

> The LLMRouter reads provider/model from `agent_model_config`. If the table is empty,
> restart the app once to auto-seed default configurations.

---

## 4. Ticket inbox

**What to check:** Tickets load and display correctly in the inbox.

Steps:
1. Go to the **Inbox** (`/`)
2. Confirm at least one ticket is visible
3. Confirm classification badges (bug / feature / how-to / other) are present
4. Confirm risk-level badges (low / medium / high) are present
5. If the inbox is empty:
   - Click **Refresh Inbox** to trigger a fresh Freshdesk fetch
   - Verify the Freshdesk group ID is correct in Settings

> Tickets are fetched on demand. The inbox only shows tickets in the configured
> Freshdesk group and status filters.

---

## 5. Ticket detail

**What to check:** Opening a ticket shows all AI analysis panels.

Steps:
1. Click any ticket in the inbox to open the ticket detail page
2. Confirm the following panels are visible (may show "unavailable" if not yet analysed):
   - [ ] **PMDecision** — classification, confidence, rationale
   - [ ] **PM Guard Review** — named guardrails with pass/warn/fail
   - [ ] **Existing Solution Review** — whether the feature already exists
   - [ ] **KB Evidence** — retrieved knowledge base entries
   - [ ] **KB Evidence Quality** — completeness / recency / consistency
   - [ ] **KB Snapshot Diff** — changes since last analysis
   - [ ] **Safe-to-Send Review** — score and status card
3. Confirm no unhandled Python errors appear on the page (500 errors)
4. Confirm the page loads within a reasonable time (< 5 seconds for cached analysis)

---

## 6. Draft generation

**What to check:** Generating a draft reply works and produces output.

Steps:
1. On the ticket detail page, click **Generate Drafts**
2. Confirm the spinner/loading state appears
3. Confirm a draft reply appears in the draft area after generation
4. Confirm the draft is not empty
5. Confirm the AI generation did not produce a raw error message (e.g. `[ROUTER ERROR]`)

If generation fails:
- Check the LLM provider connection (step 3)
- Check the agent model configs are seeded (Agents page)
- Check the system logs for `complete_main_llm` error messages

> Draft generation uses LLMRouter. The model and provider are read from
> `agent_model_config` — not hardcoded.

---

## 7. Safe-to-Send Review

**What to check:** The Safe-to-Send panel scores the draft and shows a clear status.

Steps:
1. After draft generation (step 6), look at the **Safe-to-Send Review** panel
2. Confirm the status badge shows one of:
   - 🟢 **Safe to send** — no blocking issues
   - 🟡 **Needs review** — warnings present; review before sending
   - 🔴 **Do not send yet** — blocking issues; resolve first
3. Confirm the score (0–100) is displayed
4. Confirm top reasons are listed (if any)
5. If the panel shows "unavailable": regenerate the draft

---

## 8. Copy confirmation (human-review gate)

**What to check:** Copying a flagged draft triggers a confirmation dialog.

Steps:
1. If the Safe-to-Send status is **Needs review** or **Do not send yet**:
   - Click **Copy clean draft**
   - Confirm a browser dialog appears with a warning message
   - Confirm the dialog mentions "review warnings" or "do not send yet"
   - Click **Cancel** — confirm nothing is sent
2. If the status is **Safe to send**:
   - Click **Copy clean draft**
   - Confirm the draft is copied to the clipboard
   - No confirmation dialog is required for safe drafts
3. Confirm the **Copy clean draft** button is never disabled (always clickable)

> The copy button is a gate — it warns but does not block. Sending still requires
> a human to paste the draft into Freshdesk and click Reply.

---

## 9. No auto-send

**What to check:** The app never sends a reply to Freshdesk automatically.

Steps:
1. Confirm there is no "Auto-send" or "Send now" button anywhere in the UI
2. Confirm clicking "Copy clean draft" only copies to clipboard — it does not POST to Freshdesk
3. Confirm the ticket detail page has no background jobs that send replies
4. Confirm the only way to post a reply to Freshdesk is via the **Post Reply** form
   (which requires the agent to manually paste and submit)

---

## 10. Human review required

**What to check:** Every action path requires explicit human approval.

Steps:
1. Confirm the draft area shows the Safe-to-Send banner — agents must read it before acting
2. Confirm the **Post Reply** / **Post Note** buttons require explicit form submission
3. Confirm the **PM Decision** panel is informational only — no auto-routing
4. Confirm the **Jira** integration (if enabled) only creates issues when the user explicitly clicks "Create Jira Issue"
5. Confirm the **Generate Drafts** button only generates — it does not send

---

## Final checklist summary

| # | Step | Status |
|---|------|--------|
| 1 | Settings readiness — System Readiness card shows Ready; Security Readiness shows no critical fail | ☐ |
| 2 | Freshdesk connection — Test Connection passes | ☐ |
| 3 | LLM provider connection — Test LLM Connection passes | ☐ |
| 4 | Ticket inbox — tickets visible with classification badges | ☐ |
| 5 | Ticket detail — all panels visible without 500 errors | ☐ |
| 6 | Draft generation — draft appears, no ROUTER ERROR | ☐ |
| 7 | Safe-to-Send Review — score and status visible | ☐ |
| 8 | Copy confirmation — dialog shown for flagged drafts | ☐ |
| 9 | No auto-send — no reply posted without human action | ☐ |
| 10 | Human review required — no action path bypasses review | ☐ |

**All 10 items must pass before the demo.**

---

## Automated route check

Run before the demo to verify safe HTTP routes respond correctly:

```bash
# Against local app (default)
python3 scripts/smoke_check.py

# Against a deployed instance
python3 scripts/smoke_check.py --base-url https://your-app.onrender.com

# Dry run — list checks without executing
python3 scripts/smoke_check.py --dry-run
```

The script checks:
- `GET /api/system-readiness` — expects `{"ok": true}`
- `GET /api/status` — expects HTTP 200
- `GET /` — inbox loads
- `GET /settings` — settings page loads
- `GET /agents` — agents page loads

The script **never** calls Freshdesk or LLM APIs directly.

---

*See also: [`docs/TEAM_DEMO_GUIDE.md`](TEAM_DEMO_GUIDE.md) · [`docs/PRODUCTION_CHECKLIST.md`](PRODUCTION_CHECKLIST.md)*
