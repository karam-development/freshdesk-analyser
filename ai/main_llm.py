"""Main LLM helper — provider-agnostic generation for core app paths.

This module wraps LLMRouter for the main generation paths in app.py:
draft response, translation, PRD analysis, and ticket analysis.

Public API
----------
get_main_llm_router(db) -> LLMRouter
    Return a configured LLMRouter instance.

complete_main_llm(
    db,
    agent_name,
    system,
    messages,
    purpose="",
    max_tokens=None,
    fallback_legacy_client=None,
) -> dict
    Call the LLMRouter for a single completion.  Returns a stable dict:

    {
      "text": str,
      "provider": str,
      "model": str,
      "input_tokens": int,
      "output_tokens": int,
      "ok": bool,
      "error": str,     # empty on success; clear message on failure
    }

Rules
-----
- Uses only ``llm_api_key`` (via LLMRouter) — never ``anthropic_api_key``.
- Missing ``llm_api_key`` → ok=False with a clear error message.
- Router exception → ok=False with error text (no API keys in error).
- Never raises to the caller.
"""
from __future__ import annotations

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

# ── Lazy import guard ─────────────────────────────────────────────────────────

try:
    from ai.llm.router import LLMRouter as _LLMRouter
    _ROUTER_AVAILABLE = True
except ImportError:
    _LLMRouter = None  # type: ignore
    _ROUTER_AVAILABLE = False


# ── Public helpers ────────────────────────────────────────────────────────────

def get_main_llm_router(db) -> Optional["_LLMRouter"]:
    """Return a configured LLMRouter for the given DB connection.

    Returns None if LLMRouter is not importable (legacy deploy).
    Never raises.
    """
    if not _ROUTER_AVAILABLE or _LLMRouter is None:
        return None
    try:
        return _LLMRouter(db=db)
    except Exception as exc:
        logger.warning(f"get_main_llm_router: failed to create LLMRouter: {exc}")
        return None


def complete_main_llm(
    db,
    agent_name: str,
    system: str,
    messages: List[dict],
    purpose: str = "",
    max_tokens: Optional[int] = None,
    fallback_legacy_client=None,  # reserved for future use; currently unused
) -> dict:
    """Call LLMRouter for a single completion.

    Parameters
    ----------
    db:
        Active DB connection (used by LLMRouter to read provider settings and
        agent_model_config).
    agent_name:
        Must match an existing agent_model_config row
        (e.g. ``"draft_response_agent"``, ``"prd_agent"``,
        ``"main_analysis_agent"``).
    system:
        System prompt string.
    messages:
        List of ``{"role": str, "content": str}`` dicts.  Vision/multimodal
        content blocks are NOT supported — callers must pass text-only messages.
    purpose:
        Optional free-text description for logging.
    max_tokens:
        Override the agent's configured max_tokens when provided.
    fallback_legacy_client:
        Reserved for future use.  Currently ignored — callers that need a
        legacy fallback must handle it themselves.

    Returns
    -------
    dict
        ``{"text", "provider", "model", "input_tokens", "output_tokens",
           "ok", "error"}``
        ``ok`` is False when no llm_api_key is configured or any exception
        is raised.  Error text never contains API keys.
    """
    _empty = {
        "text": "",
        "provider": "",
        "model": "",
        "input_tokens": 0,
        "output_tokens": 0,
        "ok": False,
        "error": "",
    }

    if not _ROUTER_AVAILABLE or _LLMRouter is None:
        return {**_empty, "error": "LLMRouter not available (import failed)."}

    if db is None:
        return {**_empty, "error": "No DB connection provided to complete_main_llm."}

    try:
        router = _LLMRouter(db=db)
    except Exception as exc:
        return {**_empty, "error": f"LLMRouter init failed: {type(exc).__name__}"}

    try:
        resp = router.complete(
            agent_name=agent_name,
            system=system,
            messages=messages,
            purpose=purpose,
            max_tokens=max_tokens,
        )
        text = resp.text or ""
        provider = resp.provider or ""
        model = resp.model or ""
        input_tokens = getattr(resp.usage, "input_tokens", 0) if resp.usage else 0
        output_tokens = getattr(resp.usage, "output_tokens", 0) if resp.usage else 0

        if purpose:
            logger.info(
                f"complete_main_llm [{agent_name}] {purpose}: "
                f"provider={provider} model={model} "
                f"in={input_tokens} out={output_tokens} chars={len(text)}"
            )

        return {
            "text": text,
            "provider": provider,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "ok": True,
            "error": "",
        }

    except RuntimeError as exc:
        # LLMRouter raises RuntimeError for missing api_key and provider failures.
        # Sanitise: never include the raw error if it might contain key substrings.
        err_str = str(exc)
        # Redact anything that looks like a key (long alphanumeric token)
        import re as _re
        err_safe = _re.sub(r'[A-Za-z0-9_\-]{30,}', '[REDACTED]', err_str)
        logger.warning(
            f"complete_main_llm [{agent_name}] RuntimeError: {err_safe}"
        )
        return {**_empty, "error": err_safe}

    except Exception as exc:
        err_safe = f"LLMRouter call failed for '{agent_name}': {type(exc).__name__}"
        logger.warning(f"complete_main_llm [{agent_name}] exception: {exc}")
        return {**_empty, "error": err_safe}
