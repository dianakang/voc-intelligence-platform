"""Base agent with automatic cross-provider fallback between Anthropic and OpenAI.

Every agent has a primary provider (Anthropic by default) and, when both API
keys are configured, an automatic fallback to the other provider if the
primary exhausts its own retries — e.g. credit exhaustion, an outage, or a
rate limit on one provider shouldn't take the whole pipeline down.
"""
from __future__ import annotations

import json
from typing import Any, Optional

import anthropic
import openai
from tenacity import retry, stop_after_attempt, wait_exponential
from rich.console import Console

from src.config import settings

console = Console()

_RETRY = dict(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)


class BaseAgent:
    def __init__(
        self,
        name: str,
        model: str,
        system_prompt: str,
        temperature: float = 0.3,
        provider: str = "anthropic",
    ):
        self.name = name
        self.model = model
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.provider = provider  # "anthropic" | "openai" — preferred provider for this agent

        self._anthropic_client: Optional[anthropic.Anthropic] = None
        self._openai_client: Optional[openai.OpenAI] = None

        if settings.effective_anthropic_key:
            client_kwargs: dict = {"api_key": settings.effective_anthropic_key}
            if settings.anthropic_base_url:
                client_kwargs["base_url"] = settings.anthropic_base_url
            self._anthropic_client = anthropic.Anthropic(**client_kwargs)

        if settings.openai_api_key:
            self._openai_client = openai.OpenAI(api_key=settings.openai_api_key)

    def _fallback_model(self, provider: str, model: str) -> tuple[str, str]:
        """Resolve the (provider, model) to use if `provider`/`model` fails.

        Checked in sonnet/haiku/opus order (not a dict) because some .env setups
        point multiple tiers at the same underlying model string (e.g.
        MODEL_OPUS == MODEL_SONNET) — a dict keyed on the model string would let
        the last-inserted tier silently win. Sonnet is checked first since it's
        the most commonly reused tier.
        """
        if provider == "anthropic":
            if model == settings.model_sonnet:
                return "openai", settings.openai_model_sonnet
            if model == settings.model_haiku:
                return "openai", settings.openai_model_haiku
            if model == settings.model_opus:
                return "openai", settings.openai_model_opus
            return "openai", settings.openai_model_sonnet
        if model == settings.openai_model_sonnet:
            return "anthropic", settings.model_sonnet
        if model == settings.openai_model_haiku:
            return "anthropic", settings.model_haiku
        if model == settings.openai_model_opus:
            return "anthropic", settings.model_opus
        return "anthropic", settings.model_sonnet

    def call(self, user_message: str, max_tokens: int = 4096, json_mode: bool = False) -> str:
        attempts = [(self.provider, self.model)]
        if self._anthropic_client and self._openai_client:
            attempts.append(self._fallback_model(self.provider, self.model))

        last_error: Exception = RuntimeError("No LLM provider configured (set ANTHROPIC_API_KEY or OPENAI_API_KEY)")
        for i, (prov, mdl) in enumerate(attempts):
            try:
                return self._call_provider(prov, mdl, user_message, max_tokens, json_mode)
            except Exception as e:
                last_error = e
                if i < len(attempts) - 1:
                    next_prov, next_mdl = attempts[i + 1]
                    self.log(f"[yellow]{prov} call failed ({e}); falling back to {next_prov} ({next_mdl})")
        raise last_error

    @retry(**_RETRY)
    def _call_provider(
        self, provider: str, model: str, user_message: str, max_tokens: int, json_mode: bool
    ) -> str:
        if provider == "anthropic":
            if not self._anthropic_client:
                raise RuntimeError("Anthropic API key not configured")
            system = self.system_prompt
            if json_mode:
                system += "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown, no explanation outside JSON."
            response = self._anthropic_client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user_message}],
                temperature=self.temperature,
            )
            return response.content[0].text

        if not self._openai_client:
            raise RuntimeError("OpenAI API key not configured")
        kwargs: dict = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = self._openai_client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=self.temperature,
            **kwargs,
        )
        return response.choices[0].message.content or ""

    def call_json(self, user_message: str, max_tokens: int = 4096) -> Any:
        raw = self.call(user_message, max_tokens=max_tokens, json_mode=True).strip()
        return parse_json_response(raw)

    def log(self, message: str) -> None:
        console.print(f"[bold blue][{self.name}][/bold blue] {message}")


def parse_json_response(raw: str) -> Any:
    """Repair and parse an LLM's JSON-mode response. Shared by BaseAgent.call_json
    and any standalone (non-agent) call to a JSON-mode model."""
    raw = raw.strip()
    # Strip markdown fences
    if raw.startswith("```"):
        raw = raw[raw.find("\n") + 1:]
        if "```" in raw:
            raw = raw[: raw.rfind("```")]
    parsed = json.loads(raw.strip())

    # OpenAI's JSON mode requires a top-level object, so a prompt asking for a
    # bare JSON array sometimes comes back wrapped as e.g. {"reviews": [...]}.
    # Unwrap that so callers expecting a bare array still get one.
    if isinstance(parsed, dict) and len(parsed) == 1:
        only_value = next(iter(parsed.values()))
        if isinstance(only_value, list):
            return only_value
    return parsed
