# Freshdesk Analyser

AI-powered Freshdesk ticket analysis tool built with Flask and Claude AI. Fetches tickets from Freshdesk, analyses them with Claude, generates draft replies, tracks BSO metrics, and exports reports.

## Features

- Ticket inbox with AI-powered analysis and draft reply generation
- Jira integration (create/link tickets)
- Google Sheets/Slides/Docs export
- Notion export
- Knowledge base for contextual AI responses
- Agent system with lesson learning
- PDF and PPTX report export
- BSO (Before Ship Out) tracking

## Deploy to Render (one click)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

1. Click the button above and connect your GitHub account
2. Render will use `render.yaml` to configure a web service with a 1 GB persistent disk
3. Once deployed, open the app and go to **Settings** to enter your API keys

## Run locally

```bash
# Clone the repo
git clone https://github.com/karam-development/freshdesk-analyser.git
cd freshdesk-analyser

# Install Python dependencies
pip install -r requirements.txt

# Install Node dependencies (for PPTX export)
npm install

# Start the app
./run.sh        # macOS/Linux
run.bat         # Windows
```

Open [http://localhost:5000](http://localhost:5000) and go to **Settings** to configure:

- Freshdesk API key and domain
- Anthropic API key
- Jira credentials (optional)
- Google Service Account JSON (optional)
- Notion API key (optional)

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | auto-generated | Flask session secret |
| `DATA_DIR` | app directory | Path for database and uploaded files |
| `PORT` | 5000 | HTTP port |
| `FLASK_DEBUG` | false | Enable debug mode |

Copy `.env.example` to `.env` and edit as needed.

## Tech stack

- **Backend**: Python, Flask, SQLite
- **AI**: Anthropic Claude (via `anthropic` SDK)
- **Export**: ReportLab (PDF), pptxgenjs (PPTX), openpyxl (Excel)
- **Integrations**: Freshdesk API, Jira REST API, Google Workspace API, Notion API
