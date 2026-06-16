"""Base agent with Anthropic Claude (direct or via OpenRouter)."""
from __future__ import annotations

import json
from typing import Any

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential
from rich.console import Console

from src.config import settings

console = Console()


class BaseAgent:
    def __init__(self, name: str, model: str, system_prompt: str, temperature: float = 0.3):
        self.name = name
        self.model = model
        self.system_prompt = system_prompt
        self.temperature = temperature

        client_kwargs: dict = {"api_key": settings.effective_anthropic_key}
        if settings.anthropic_base_url:
            client_kwargs["base_url"] = settings.anthropic_base_url
        self.client = anthropic.Anthropic(**client_kwargs)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def call(self, user_message: str, max_tokens: int = 4096, json_mode: bool = False) -> str:
        system = self.system_prompt
        if json_mode:
            system += "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown, no explanation outside JSON."

        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_message}],
            temperature=self.temperature,
        )
        return response.content[0].text

    def call_json(self, user_message: str, max_tokens: int = 4096) -> Any:
        raw = self.call(user_message, max_tokens=max_tokens, json_mode=True).strip()
        # Strip markdown fences
        if raw.startswith("```"):
            raw = raw[raw.find("\n") + 1:]
            if "```" in raw:
                raw = raw[: raw.rfind("```")]
        return json.loads(raw.strip())

    def log(self, message: str) -> None:
        console.print(f"[bold blue][{self.name}][/bold blue] {message}")
