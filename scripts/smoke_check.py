#!/usr/bin/env python3
"""Lightweight smoke-check script for the Freshdesk AI Analyser.

Checks that safe local HTTP routes respond correctly before a demo or deployment.

IMPORTANT: This script NEVER calls Freshdesk or LLM APIs directly.
It only makes GET requests to the local (or configured) app server.

Usage
-----
  python3 scripts/smoke_check.py                          # default: http://localhost:5000
  python3 scripts/smoke_check.py --base-url http://...   # custom base URL
  python3 scripts/smoke_check.py --timeout 10            # custom timeout (seconds)
  python3 scripts/smoke_check.py --dry-run               # list checks, do not execute
  python3 scripts/smoke_check.py --json                  # machine-readable output

Exit codes
----------
  0  all checks passed
  1  one or more checks failed
  2  all checks skipped (dry-run or no checks configured)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Optional

# ── Only stdlib imports — no app imports, no third-party dependencies ─────────
# requests is part of the app's requirements.txt; we import it lazily so that
# --dry-run and --help work even without it.

_RESET  = "\033[0m"
_GREEN  = "\033[32m"
_YELLOW = "\033[33m"
_RED    = "\033[31m"
_BOLD   = "\033[1m"
_CYAN   = "\033[36m"


def _c(colour: str, text: str, use_colour: bool) -> str:
    return f"{colour}{text}{_RESET}" if use_colour else text


# ── Check definitions ─────────────────────────────────────────────────────────
# Each check is a dict:
#   code          str    machine-readable identifier
#   method        str    HTTP method (only GET is used — no destructive calls)
#   path          str    URL path (relative to base_url)
#   description   str    human-readable description
#   expect_status int    expected HTTP status code (default 200)
#   expect_json   dict   optional: key → expected value in JSON body
#   note          str    optional: shown after result

CHECKS = [
    {
        "code": "system_readiness",
        "method": "GET",
        "path": "/api/system-readiness",
        "description": "System readiness API returns ok=true",
        "expect_status": 200,
        "expect_json": {"ok": True},
        "note": "If ok=false: check Settings → System Readiness card for details.",
    },
    {
        "code": "api_status",
        "method": "GET",
        "path": "/api/status",
        "description": "Job status API responds",
        "expect_status": 200,
        "note": None,
    },
    {
        "code": "inbox",
        "method": "GET",
        "path": "/",
        "description": "Ticket inbox page loads",
        "expect_status": 200,
        "note": "If 500: check startup logs for DB or import errors.",
    },
    {
        "code": "settings",
        "method": "GET",
        "path": "/settings",
        "description": "Settings page loads",
        "expect_status": 200,
        "note": "If 500: check DB availability and settings table.",
    },
    {
        "code": "agents",
        "method": "GET",
        "path": "/agents",
        "description": "Agents page loads",
        "expect_status": 200,
        "note": "If 500: check agent_model_config table is seeded.",
    },
]

# ── Result structure ──────────────────────────────────────────────────────────

def _run_check(check: dict, base_url: str, timeout: int, use_colour: bool) -> dict:
    """Execute a single check and return a result dict. Never raises."""
    import urllib.request
    import urllib.error

    url = base_url.rstrip("/") + check["path"]
    start = time.monotonic()
    try:
        # Use urllib (stdlib) so the script has zero external dependencies.
        req = urllib.request.Request(url, method=check["method"])
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = time.monotonic() - start
            status = resp.status
            body_bytes = resp.read()
    except urllib.error.HTTPError as exc:
        elapsed = time.monotonic() - start
        status = exc.code
        body_bytes = b""
    except Exception as exc:
        elapsed = time.monotonic() - start
        return {
            "code": check["code"],
            "status": "error",
            "description": check["description"],
            "error": str(exc),
            "elapsed": elapsed,
            "note": check.get("note"),
        }

    # JSON body validation
    expect_json = check.get("expect_json")
    json_ok = True
    json_msg = ""
    if expect_json and body_bytes:
        try:
            body = json.loads(body_bytes.decode("utf-8", errors="replace"))
            for key, expected_val in expect_json.items():
                actual = body.get(key)
                if actual != expected_val:
                    json_ok = False
                    json_msg = f"expected {key}={expected_val!r}, got {actual!r}"
        except json.JSONDecodeError as e:
            json_ok = False
            json_msg = f"invalid JSON: {e}"

    expect_status = check.get("expect_status", 200)
    passed = (status == expect_status) and json_ok

    return {
        "code": check["code"],
        "status": "pass" if passed else "fail",
        "description": check["description"],
        "http_status": status,
        "elapsed": elapsed,
        "json_msg": json_msg if not json_ok else "",
        "note": check.get("note"),
    }


# ── Output helpers ────────────────────────────────────────────────────────────

def _print_result(result: dict, use_colour: bool) -> None:
    s = result["status"]
    if s == "pass":
        icon = _c(_GREEN, "✓ PASS", use_colour)
    elif s == "fail":
        icon = _c(_RED, "✗ FAIL", use_colour)
    else:
        icon = _c(_YELLOW, "⚠ ERROR", use_colour)

    elapsed = result.get("elapsed", 0)
    desc = result["description"]
    code = result["code"]
    print(f"  {icon}  {desc}  [{code}]  ({elapsed*1000:.0f} ms)")

    if s == "fail":
        if result.get("http_status"):
            print(f"         HTTP {result['http_status']}", end="")
            if result.get("json_msg"):
                print(f" — {result['json_msg']}", end="")
            print()
        if result.get("note"):
            print(f"         Hint: {result['note']}")

    if s == "error":
        print(f"         Error: {result.get('error')}")
        if result.get("note"):
            print(f"         Hint: {result['note']}")


def _print_dry(check: dict, use_colour: bool) -> None:
    method = check["method"]
    path = check["path"]
    desc = check["description"]
    code = check["code"]
    print(f"  {_c(_CYAN, '○ SKIP', use_colour)}  {desc}  [{code}]")
    print(f"         {method} {path}")
    if check.get("note"):
        print(f"         Note: {check['note']}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Smoke-check safe local routes of the Freshdesk AI Analyser.\n"
            "Never calls Freshdesk or LLM APIs directly."
        )
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:5000",
        help="Base URL of the running app (default: http://localhost:5000)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=5,
        help="HTTP request timeout in seconds (default: 5)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List all checks without executing them",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Output results as JSON (machine-readable)",
    )
    parser.add_argument(
        "--no-colour",
        action="store_true",
        help="Disable ANSI colour output",
    )
    args = parser.parse_args()

    use_colour = not args.no_colour and sys.stdout.isatty()

    if not args.json_output:
        print()
        print(_c(_BOLD, "Freshdesk AI Analyser — Smoke Check", use_colour))
        if args.dry_run:
            print(f"  Mode: dry run (listing checks only)")
        else:
            print(f"  Target: {args.base_url}")
            print(f"  Timeout: {args.timeout}s")
        print(f"  Checks: {len(CHECKS)}")
        print()
        print(_c(_BOLD, "IMPORTANT: This script never calls Freshdesk or LLM APIs.", use_colour))
        print()

    if args.dry_run:
        if args.json_output:
            print(json.dumps({"mode": "dry_run", "checks": [
                {"code": c["code"], "method": c["method"], "path": c["path"],
                 "description": c["description"]}
                for c in CHECKS
            ]}, indent=2))
        else:
            for check in CHECKS:
                _print_dry(check, use_colour)
            print()
            print(f"  {len(CHECKS)} check(s) listed. Run without --dry-run to execute.")
        return 2  # all skipped

    # Execute checks
    results = []
    for check in CHECKS:
        result = _run_check(check, args.base_url, args.timeout, use_colour)
        results.append(result)
        if not args.json_output:
            _print_result(result, use_colour)

    # Summary
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    errors = sum(1 for r in results if r["status"] == "error")
    total = len(results)

    if args.json_output:
        print(json.dumps({
            "base_url": args.base_url,
            "total": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "results": results,
        }, indent=2))
    else:
        print()
        print("─" * 50)
        if failed == 0 and errors == 0:
            print(_c(_GREEN, f"  ✓ All {passed}/{total} checks passed.", use_colour))
        else:
            ok_parts = [f"{passed} passed"]
            if failed:
                ok_parts.append(_c(_RED, f"{failed} failed", use_colour))
            if errors:
                ok_parts.append(_c(_YELLOW, f"{errors} error(s)", use_colour))
            print("  " + ", ".join(ok_parts) + f" out of {total} checks.")
        print()

        if failed or errors:
            print("  Next steps:")
            print("  1. Check that the app is running at:", args.base_url)
            print("  2. Open /settings and review the System Readiness card.")
            print("  3. See docs/LIVE_DEMO_SMOKE_TEST.md for manual steps.")
            print()

    return 0 if (failed == 0 and errors == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
