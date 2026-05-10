# Freshdesk Analyser

AI-powered Freshdesk ticket analysis tool built with Flask and SQLite. Fetches tickets,
analyses them with an LLM, generates draft replies, and tracks BSO metrics.

> **Human-review only.** AI drafts are never auto-sent. Every draft must be reviewed
> and approved by a PO/agent before it can be used. The tool assists — it does not act.

---

## Documentation

| Document | Description |
|----------|-------------|
| [Team Demo Guide](docs/TEAM_DEMO_GUIDE.md) | How to run and demo the app for the team |
| [Production Checklist](docs/PRODUCTION_CHECKLIST.md) | Pre-deployment and operational requirements |
| [Live Demo Smoke Test](docs/LIVE_DEMO_SMOKE_TEST.md) | Manual and automated pre-demo checks |
| [Playwright Smoke Tests](docs/PLAYWRIGHT_SMOKE_TESTS.md) | Optional browser-level UI smoke tests |

> **Safety rule:** AI drafts are suggestions only — no auto-send behaviour exists. Human review is required before any reply is sent.

> **Security:** A Security Readiness card is available on the Settings page and via `GET /api/security-readiness`. It checks for weak `SECRET_KEY`, enabled debug mode, and missing API keys — without exposing any secret values.

---

## Features

- Ticket inbox with AI-powered analysis and draft reply generation
- Provider-agnostic LLM routing (Anthropic Claude or OpenAI)
- Per-agent model configuration (provider, model, temperature, fallback)
- Jira integration (create/link tickets)
- Google Sheets / Slides / Docs export
- Notion export
- Knowledge base for contextual AI responses
- Agent lesson-learning system
- PDF and PPTX report export
- BSO (Before Ship Out) tracking

---

## Deploy to Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

1. Click the button above and connect your GitHub account
2. Render uses `render.yaml` to provision a web service with a 1 GB persistent disk
3. Once deployed, open the app → **Settings** to enter your API keys

---

## Run locally

```bash
git clone https://github.com/karam-development/freshdesk-analyser.git
cd freshdesk-analyser

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt

# (Optional) install Node deps for PPTX export
npm install

# Start the app
python app.py
# or: gunicorn app:app
```

Open [http://localhost:5000](http://localhost:5000).

---

## Configuration

All secrets are stored in the database via the **Settings** page. You can also pre-seed
values using environment variables (see `.env.example`).

### Freshdesk

| Setting | Where |
|---------|-------|
| API key | Settings → Freshdesk → API Key |
| Domain  | Settings → Freshdesk → Domain (e.g. `yourcompany.freshdesk.com`) |
| Group ID | Settings → Freshdesk → Group ID |

### AI Provider settings (new unified path)

The app now supports **Anthropic** and **OpenAI** through a single provider-agnostic
routing layer. Configure it in **Settings → AI Provider Configuration**.

| Setting | Key | Description |
|---------|-----|-------------|
| Provider | `llm_provider` | `anthropic` or `openai` |
| API Key  | `llm_api_key`  | Key for the selected provider |
| Base URL | `llm_base_url` | Optional; for OpenAI-compatible endpoints |
| Fast model | `llm_fast_model` | Override the fast/cheap model |
| Main model | `llm_main_model` | Override the main/capable model |

> **Important:** `llm_api_key` is the active key used by the router.
> The legacy `anthropic_api_key` setting is kept only for the old direct Anthropic
> code path and is **not** read by the router.

#### Per-agent overrides

Each of the 16 agents (KB, Code, Research, QA, Learning, …) can have its own
provider, model, temperature, max-tokens, and optional fallback provider/model.
Configure them in **Agents → Model Configuration**.

#### Safe failure behaviour

If the provider settings are missing or the API key is not configured, routed agents
fail safely:

- **KB agent** → returns a clear "KB Agent failed" message; no crash
- **Code agent** → returns a safe unavailable message; raw code is never leaked
- **Research agent** → `"Research agent unavailable — proceeding without historical context."`
- **QA agent** → `passed: false` / manual review required
- **Learning agent** → returns an empty lesson list; nothing is saved to the DB

#### Legacy Anthropic path

If an agent is called **without** an `llm_router` (direct call), it uses the old
`Anthropic` client directly. This path is unaffected by the provider routing layer.

### Jira (optional)

Settings → Jira: domain, email, API token, project key.

### Google Drive / Workspace (optional)

Settings → Google Drive: service account JSON, export folder, KB folder.

### Notion (optional)

Settings → Notion: integration token, database/page ID.

---

## Environment variables

Copy `.env.example` to `.env` and edit as needed. Settings not listed here can be
configured in the app's Settings page.

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | auto-generated | Flask session secret |
| `DATA_DIR` | app directory | Path for DB and uploaded files |
| `PORT` | 5000 | HTTP port |
| `FLASK_DEBUG` | false | Enable debug mode |
| `LLM_PROVIDER` | — | Pre-seed `llm_provider` setting |
| `LLM_API_KEY` | — | Pre-seed `llm_api_key` setting |
| `LLM_BASE_URL` | — | Pre-seed `llm_base_url` setting |
| `LLM_FAST_MODEL` | — | Pre-seed `llm_fast_model` setting |
| `LLM_MAIN_MODEL` | — | Pre-seed `llm_main_model` setting |
| `ANTHROPIC_API_KEY` | — | Legacy direct-Anthropic path only |

---

## CI

GitHub Actions runs automatically on every pull request and push to `main`:

1. **Compile check** — `python3 -m py_compile app.py agents.py …`
2. **pytest** — full test suite (`pytest -q`); browser smoke tests skip if Playwright is not installed
3. **Smoke check dry-run** — `python3 scripts/smoke_check.py --dry-run --json`

No secrets or API keys are required for CI. Freshdesk and LLM APIs are never called.
Browser smoke tests (Playwright) are optional — see [`docs/PLAYWRIGHT_SMOKE_TESTS.md`](docs/PLAYWRIGHT_SMOKE_TESTS.md).

---

## Running tests

```bash
# Compile check (must produce no output)
python3 -m py_compile app.py agents.py ai/security_readiness.py \
  ai/llm/router.py ai/main_llm.py scripts/smoke_check.py

# Unit tests
pytest -q

# Smoke check dry-run (no app required)
python3 scripts/smoke_check.py --dry-run --json
```

All tests must pass before pushing to a feature branch.

---

## Tech stack

- **Backend**: Python 3.9+, Flask, SQLite
- **AI**: Anthropic Claude or OpenAI (via provider-agnostic `ai/` package)
- **Export**: ReportLab (PDF), pptxgenjs (PPTX), openpyxl (Excel)
- **Integrations**: Freshdesk API, Jira REST API, Google Workspace API, Notion API
