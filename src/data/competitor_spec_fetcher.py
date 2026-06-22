"""Live, search-grounded competitor TV spec fetching via OpenRouter.

Deliberately standalone (not a BaseAgent subclass): BaseAgent's retry/fallback
machinery branches only on provider == "anthropic" | "openai" and is shared by
all 11 production analysis agents, so bolting a third "openrouter search model"
provider onto it would risk those agents for the sake of one low-frequency,
manually-triggered, out-of-band command (`voc refresh-competitors`).

Competitor hardware specs don't change once a model ships, so this is never
called from `voc run` or the LangGraph pipeline. Run `voc refresh-competitors`
by hand, review the printed summary (including citations, if the model
returned any) before trusting it, then re-run the pipeline to pick it up.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import openai
from pydantic import ValidationError
from rich.console import Console

from src.agents.base import parse_json_response
from src.config import settings
from src.data.models import CompetitorSpec
from src.data.spec_extractor import COMPETITOR_SPECS

console = Console()

_FIELD_LIST = (
    "model, price_usd (number), display_type, panel, refresh_rate, local_dimming, "
    "hdr (list of strings, e.g. [\"HDR10\", \"HLG\"]), audio_power, dolby_atmos (boolean), "
    "os, hdmi, vrr, gaming_input_lag, wifi, strengths (list of strings), "
    "weaknesses (list of strings), sources (list of URLs you grounded this on, if any)"
)


def _safe_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _cache_path(name: str) -> Path:
    return settings.raw_data_path / "competitors" / _safe_name(name) / "spec.json"


def fetch_one(name: str, model: str) -> CompetitorSpec:
    """Fetch one competitor's spec via a search-grounded OpenRouter call.

    Raises on missing API key, a malformed response, or a response missing
    required fields — callers should catch and fall back to the existing
    hardcoded COMPETITOR_SPECS entry for that competitor."""
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set; refresh-competitors requires it")

    client = openai.OpenAI(api_key=settings.openrouter_api_key, base_url="https://openrouter.ai/api/v1")
    prompt = (
        f"Look up the real, current specifications for the {name} TV, model {model}. "
        f"Respond with ONLY a single JSON object (no markdown, no explanation) with exactly "
        f"these fields: {_FIELD_LIST}. price_usd must be a real number (your best estimate of "
        f"current street price if MSRP is unclear) and dolby_atmos must be true or false. For "
        f"any other field you cannot verify, use the string 'N/A' rather than guessing or "
        f"fabricating a technical detail."
    )
    response = client.chat.completions.create(
        model=settings.competitor_search_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1500,
    )
    raw = response.choices[0].message.content or ""
    parsed = parse_json_response(raw)
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected a JSON object, got {type(parsed).__name__}")
    parsed["fetched_at"] = datetime.now(timezone.utc).isoformat()
    return CompetitorSpec(**parsed)


def refresh_all_competitors() -> dict[str, dict]:
    """Fetch all known competitors, caching each success to disk. Returns a
    per-competitor summary dict for the CLI to render: {"ok": bool, "error": str|None,
    "spec": CompetitorSpec|None}. One failure doesn't block the others."""
    results: dict[str, dict] = {}
    for name, entry in COMPETITOR_SPECS.items():
        model = entry.get("model", "")
        try:
            spec = fetch_one(name, model)
            path = _cache_path(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(spec.model_dump(), indent=2), encoding="utf-8")
            results[name] = {"ok": True, "error": None, "spec": spec}
        except (RuntimeError, ValueError, ValidationError, json.JSONDecodeError, openai.OpenAIError) as e:
            results[name] = {"ok": False, "error": str(e), "spec": None}
    return results
