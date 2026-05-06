from ai.llm.gateway import LLMGateway
from ai.llm.registry import MODEL_REGISTRY
from ai.llm.types import LLMRequest, LLMMessage


class LLMRouter:
    def __init__(self, db=None):
        self.db = db

    def _get_setting(self, key, default=""):
        if not self.db:
            return default
        row = self.db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if not row:
            return default
        return row[0] if not hasattr(row, "keys") else row["value"]

    def get_agent_config(self, agent_name):
        if self.db:
            row = self.db.execute(
                "SELECT * FROM agent_model_config WHERE agent_name = ?", (agent_name,)
            ).fetchone()
            if row:
                return dict(row) if hasattr(row, "keys") else row
        return {
            "agent_name": agent_name,
            "provider": self._get_setting("llm_provider", "anthropic") or "anthropic",
            "model": (
                self._get_setting("llm_fast_model", MODEL_REGISTRY["anthropic"]["fast"])
                or MODEL_REGISTRY["anthropic"]["fast"]
            ),
            "temperature": 0.0,
            "max_tokens": 2000,
            "fallback_provider": "",
            "fallback_model": "",
        }

    def get_provider_settings(self, provider):
        """Return provider settings from the dedicated LLM settings keys only.

        Does NOT fall back to the legacy anthropic_api_key setting — that key is
        reserved for the old direct Anthropic path.  If llm_api_key is empty the
        caller (complete()) will surface a clear error rather than silently using
        a different credential.
        """
        provider = (provider or "anthropic").strip().lower()
        api_key = (self._get_setting("llm_api_key", "") or "").strip()
        base_url = (self._get_setting("llm_base_url", "") or "").strip()
        return {"provider": provider, "api_key": api_key, "base_url": base_url}

    def complete(self, agent_name, system, messages, purpose="", response_format=None,
                 max_tokens=None):
        cfg = self.get_agent_config(agent_name)
        provider = cfg.get("provider", "anthropic")
        model = cfg.get("model")
        temperature = cfg.get("temperature", 0.0)
        max_tok = int(max_tokens if max_tokens is not None else cfg.get("max_tokens", 2000))

        settings = self.get_provider_settings(provider)
        api_key = settings.get("api_key", "")

        if not api_key:
            raise RuntimeError(
                f"No API key configured for LLM provider '{provider}'. "
                "Please configure it in AI Provider settings."
            )

        req = LLMRequest(
            model=model,
            messages=[LLMMessage(role=m["role"], content=m["content"]) for m in messages],
            system=system,
            temperature=float(temperature),
            max_tokens=max_tok,
        )

        try:
            gw = LLMGateway(
                provider_name=provider,
                api_key=api_key,
                base_url=settings["base_url"] or None,
            )
            return gw.complete(req)
        except Exception as primary_exc:
            fb_provider = (cfg.get("fallback_provider") or "").strip().lower()
            fb_model = (cfg.get("fallback_model") or "").strip()
            if fb_provider and fb_model:
                fb_settings = self.get_provider_settings(fb_provider)
                fb_api_key = fb_settings.get("api_key", "")
                if fb_api_key:
                    fb_req = LLMRequest(
                        model=fb_model,
                        messages=req.messages,
                        system=system,
                        temperature=float(temperature),
                        max_tokens=max_tok,
                    )
                    gw = LLMGateway(
                        provider_name=fb_provider,
                        api_key=fb_api_key,
                        base_url=fb_settings["base_url"] or None,
                    )
                    return gw.complete(fb_req)
            raise RuntimeError(f"LLMRouter failure for {agent_name}: {primary_exc}")
