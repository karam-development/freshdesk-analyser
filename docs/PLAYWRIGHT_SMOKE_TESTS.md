# Playwright Browser Smoke Tests

Optional browser-level smoke tests that validate the real UI renders correctly before a team demo.

---

## Purpose

The existing test suite covers unit logic, source structure, and stdlib route-check scripts.
These Playwright tests add a browser layer that checks:

- Pages actually load in a real browser (not just return HTTP 200)
- Key UI panels render visible content
- No unhandled server errors (500 pages) appear
- System Readiness and Security Readiness cards are present on the Settings page

These tests are **optional** and do not replace the normal pytest suite.

---

## What Is Tested

| Check | Path |
|---|---|
| Inbox / homepage loads | `/` |
| Settings page loads and shows System Readiness card | `/settings` |
| Settings page shows Security Readiness card | `/settings` |
| Agents page loads | `/agents` |
| `/api/system-readiness` returns `{"ok": true}` | `/api/system-readiness` |
| `/api/security-readiness` returns `{"ok": true}` | `/api/security-readiness` |
| First ticket link (if present) opens a ticket detail page | `/ticket/<id>` |
| Ticket detail shows expected panel headings (if analysis exists) | `/ticket/<id>` |

---

## What Is NOT Tested

- Freshdesk API calls — the app must be pre-configured with credentials, but the test itself does not call Freshdesk
- LLM API calls — no drafts are generated; the test is read-only
- Reply or note posting — no POST to `/ticket/<id>/reply-ticket` or `/ticket/<id>/post-note`
- Authentication flows — the app has no login in the current scope
- Multi-browser cross-browser compatibility
- Performance benchmarks

---

## Safety Rules

These tests enforce the same safety rules as the rest of the app:

- **No Freshdesk API calls** — tests only navigate local app pages
- **No LLM API calls** — tests never trigger draft generation
- **No auto-send** — tests never POST to mutating endpoints
- **No destructive actions** — read-only navigation only
- **Human review still required** — these tests do not validate AI draft quality; they only check that panels render

---

## Prerequisites

Python 3.9+ and `pip` are required. The app does not need Playwright for its normal operation.

### Install Playwright

```bash
pip install playwright pytest-playwright
playwright install chromium
```

> Only Chromium is required. Firefox and WebKit are optional.

### Verify installation

```bash
python3 -c "from playwright.sync_api import sync_playwright; print('OK')"
```

---

## Running Tests Locally

### 1. Start the app

```bash
python3 app.py
```

The app runs on `http://localhost:5000` by default.

### 2. Run browser smoke tests

```bash
# Default (app at localhost:5000)
APP_BASE_URL=http://localhost:5000 python3 -m pytest tests/browser -q

# Headed mode (see the browser)
APP_BASE_URL=http://localhost:5000 python3 -m pytest tests/browser -q --headed

# Verbose output
APP_BASE_URL=http://localhost:5000 python3 -m pytest tests/browser -v
```

### 3. Using the helper script

```bash
bash scripts/run_browser_smoke.sh
```

---

## Running Against a Deployed Instance

```bash
APP_BASE_URL=https://your-app.onrender.com python3 -m pytest tests/browser -q
```

> The tests only make GET requests. They are safe to run against a staging or production instance.

---

## What Happens Without Playwright

If `playwright` is not installed, all browser tests skip cleanly:

```
tests/browser/test_demo_smoke.py::test_homepage_loads SKIPPED (playwright not installed)
...
```

The normal `pytest -q` suite (all `tests/test_*.py`) is **not affected** — it never imports or requires Playwright.

---

## Known Limitations

| Limitation | Notes |
|---|---|
| Requires app to be running | Tests skip if `APP_BASE_URL` is not reachable |
| Chromium must be installed | `playwright install chromium` |
| Ticket detail test is conditional | Skipped if no ticket links are visible on the inbox |
| AI panels only visible after analysis | Panel presence check is best-effort (warns, does not fail) |
| No cross-browser testing | Only Chromium in the default config |
| Not part of CI by default | Add `APP_BASE_URL` and Playwright install to CI if desired |

---

## Updating Tests

Browser tests live in `tests/browser/test_demo_smoke.py`.
They use `playwright.sync_api` and the `pytest-playwright` plugin.

Adding a new page check:
1. Add a new `test_` function
2. Use `page.goto(BASE_URL + "/your-route")`
3. Assert on visible text: `page.get_by_text("Expected heading").is_visible()`
4. Keep the test read-only — no clicks on submit/send buttons

---

*See also: [`docs/LIVE_DEMO_SMOKE_TEST.md`](LIVE_DEMO_SMOKE_TEST.md) · [`scripts/smoke_check.py`](../scripts/smoke_check.py) · [`scripts/run_browser_smoke.sh`](../scripts/run_browser_smoke.sh)*
