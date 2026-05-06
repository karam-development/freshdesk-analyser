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
            row = self.db.execute("SELECT * FROM agent_model_config WHERE agent_name = ?", (agent_name,)).fetchone()
            if row:
                return dict(row) if hasattr(row, "keys") else row
        return {
            "agent_name": agent_name,
            "provider": self._get_setting("llm_provider", "anthropic") or "anthropic",
            "model": self._get_setting("llm_fast_model", MODEL_REGISTRY["anthropic"]["fast"]) or MODEL_REGISTRY["anthropic"]["fast"],
            "temperature": 0.0,
            "max_tokens": 2000,
            "fallback_provider": "",
            "fallback_model": "",
        }

    def get_provider_settings(self, provider):
        provider = (provider or "anthropic").strip().lower()
        llm_provider = (self._get_setting("llm_provider", "") or "").strip().lower()
        llm_key = self._get_setting("llm_api_key", "")
        api_key = llm_key if llm_provider == provider and llm_key else ""
        if not api_key and provider == "anthropic":
            api_key = self._get_setting("anthropic_api_key", "") or llm_key
        return {"provider": provider, "api_key": api_key, "base_url": self._get_setting("llm_base_url", "")}

    def complete(self, agent_name, system, messages, purpose="", response_format=None, max_tokens=None):
        cfg = self.get_agent_config(agent_name)
        provider = cfg.get("provider", "anthropic")
        model = cfg.get("model")
        temperature = cfg.get("temperature", 0.0)
        max_tok = int(max_tokens if max_tokens is not None else cfg.get("max_tokens", 2000))
        settings = self.get_provider_settings(provider)
        req = LLMRequest(model=model, messages=[LLMMessage(role=m["role"], content=m["content"]) for m in messages],
                         system=system, temperature=float(temperature), max_tokens=max_tok)
        try:
            gw = LLMGateway(provider_name=provider, api_key=settings["api_key"], base_url=settings["base_url"] or None)
            return gw.complete(req)
        except Exception as primary_exc:
            fb_provider = (cfg.get("fallback_provider") or "").strip().lower()
            fb_model = (cfg.get("fallback_model") or "").strip()
            if fb_provider and fb_model:
                fb_settings = self.get_provider_settings(fb_provider)
                fb_req = LLMRequest(model=fb_model, messages=req.messages, system=system,
                                    temperature=float(temperature), max_tokens=max_tok)
                gw = LLMGateway(provider_name=fb_provider, api_key=fb_settings["api_key"], base_url=fb_settings["base_url"] or None)
                return gw.complete(fb_req)
            raise RuntimeError(f"LLMRouter failure for {agent_name}: {primary_exc}")
