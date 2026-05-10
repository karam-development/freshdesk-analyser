#!/usr/bin/env bash
# run_browser_smoke.sh — Run Playwright browser smoke tests against the running app.
#
# Usage:
#   bash scripts/run_browser_smoke.sh
#   APP_BASE_URL=https://your-app.onrender.com bash scripts/run_browser_smoke.sh
#
# The app must already be running before this script is executed.
# Tests are read-only: no Freshdesk/LLM calls, no mutating endpoints, no auto-send.

set -euo pipefail

APP_BASE_URL="${APP_BASE_URL:-http://localhost:5000}"

echo "──────────────────────────────────────────────"
echo "  Freshdesk AI Analyser — Browser Smoke Tests"
echo "──────────────────────────────────────────────"
echo "  Target: ${APP_BASE_URL}"
echo ""

# ── Check Playwright is installed ─────────────────────────────────────────────
if ! python3 -c "import playwright" 2>/dev/null; then
    echo "ERROR: Playwright is not installed."
    echo ""
    echo "Install with:"
    echo "  pip install playwright pytest-playwright"
    echo "  playwright install chromium"
    echo ""
    echo "Then re-run this script."
    exit 1
fi

# ── Check app is reachable ────────────────────────────────────────────────────
echo "Checking app is reachable at ${APP_BASE_URL}/api/status ..."
if ! python3 - <<'PYCHECK'
import urllib.request, sys, os
url = os.environ.get("APP_BASE_URL", "http://localhost:5000") + "/api/status"
try:
    with urllib.request.urlopen(url, timeout=4) as r:
        if r.status == 200:
            sys.exit(0)
        sys.exit(1)
except Exception as e:
    print(f"  Not reachable: {e}", file=sys.stderr)
    sys.exit(1)
PYCHECK
then
    echo ""
    echo "ERROR: App not reachable at ${APP_BASE_URL}"
    echo ""
    echo "Start the app first:"
    echo "  python3 app.py"
    echo ""
    echo "Or set APP_BASE_URL to a running instance:"
    echo "  APP_BASE_URL=https://your-app.onrender.com bash scripts/run_browser_smoke.sh"
    exit 1
fi

echo "  App is reachable."
echo ""

# ── Run browser smoke tests ───────────────────────────────────────────────────
echo "Running browser smoke tests..."
echo ""

APP_BASE_URL="${APP_BASE_URL}" python3 -m pytest tests/browser -q "$@"

STATUS=$?
echo ""
if [ $STATUS -eq 0 ]; then
    echo "All browser smoke tests passed."
else
    echo "Some browser smoke tests failed. See output above."
fi
echo ""
echo "Safety note: These tests are read-only."
echo "  - No Freshdesk API calls"
echo "  - No LLM API calls"
echo "  - No auto-send"
echo "  - Human review still required before any reply is sent"
echo ""
exit $STATUS
