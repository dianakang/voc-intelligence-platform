"""Live, search-grounded competitor discovery + spec fetching via Claude's native
web_search tool.

Deliberately standalone (not a BaseAgent subclass): BaseAgent's retry/fallback
machinery branches only on provider == "anthropic" | "openai" for plain text
completions and isn't aware of server tools (web_search), so bolting that onto
it would risk all 11 production analysis agents for the sake of one
low-frequency, manually-triggered, out-of-band command (`voc refresh-competitors`).

Uses the same ANTHROPIC_API_KEY as every other agent — no separate provider or
account needed.

Competitor hardware specs don't change once a model ships, so this is never
called from `voc run` or the LangGraph pipeline — it would also add several
extra LLM calls to every single analysis run, which defeats the point of
keeping per-run cost predictable. Run `voc refresh-competitors <model_code>`
by hand, review the printed summary (including citations, if the model
returned any) before trusting it, then re-run the pipeline to pick it up.

Competitors are discovered and fetched per analyzed product (not a fixed global
list) since "what competes with this" depends on the product's category — a
TV's competitors are other TVs, a refrigerator's are other refrigerators.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from pydantic import ValidationError
from rich.console import Console
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.agents.base import parse_json_response
from src.config import settings
from src.data.models import CompetitorSpec

console = Console()

# max_uses kept low (each search round-trip feeds its results back as input tokens on the next
# turn, which is what counts against an org's input-tokens-per-minute limit — low-tier accounts
# can have a limit as low as 30k/min, easily exhausted by an unbounded number of searches).
_WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 2}

# wait_exponential's max=90 covers a full per-minute rate-limit window resetting, since on a
# low input-tokens-per-minute tier (as low as 30k/min) a single web_search call can exhaust the
# whole budget for that minute — retrying sooner than that would just hit the same 429 again.
_RATE_LIMIT_RETRY = dict(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=10, max=90),
    retry=retry_if_exception_type(anthropic.RateLimitError),
    reraise=True,
)


def _safe_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _cache_path(model_code: str) -> Path:
    return settings.raw_product_dir(model_code) / "competitors.json"


def _client() -> anthropic.Anthropic:
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set; refresh-competitors requires it")
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _extract_json(text: str) -> str:
    """Pull the JSON object/array out of a web-search response's text. Despite being told to
    respond with ONLY JSON, search-grounded answers reliably narrate first (e.g. "Based on the
    search results... {...}") — parse_json_response only strips markdown fences, not prose, so
    it fails on these unless we slice out the JSON span first."""
    text = text.strip()
    start = min((i for i in (text.find("{"), text.find("[")) if i != -1), default=-1)
    end = max(text.rfind("}"), text.rfind("]"))
    if start == -1 or end == -1 or end < start:
        return text
    return text[start : end + 1]


def _final_text(response: anthropic.types.Message) -> str:
    """Concatenate the text blocks of a web_search-tool response (search/tool-use
    blocks are interleaved with the model's text; we only want the prose/JSON)."""
    if response.stop_reason == "max_tokens":
        raise RuntimeError(
            "Response truncated by max_tokens before producing a final answer "
            "(likely mid web_search) — retry, or raise max_tokens"
        )
    text = "".join(block.text for block in response.content if block.type == "text")
    if not text.strip():
        raise RuntimeError(f"Model returned no text content (stop_reason={response.stop_reason})")
    return _extract_json(text)


@retry(**_RATE_LIMIT_RETRY)
def discover_competitors(product_name: str, category: str, model_code: str) -> list[dict]:
    """Identify 3 real, currently-sold competing products in the same category, via a
    web-search-grounded call. Returns [{"name": "Brand Display Name", "model": "model number"}]."""
    prompt = (
        f"Search the web to identify exactly 3 real, currently-sold competitor products to the "
        f"Samsung {category} \"{product_name}\" (model {model_code}). Competitors must be from "
        f"different brands than Samsung, genuinely compete in the same product category and "
        f"price tier, and currently be sold in the US. After searching, respond with ONLY a "
        f'single JSON object (no markdown, no explanation): {{"competitors": [{{"name": "Brand '
        f'Display Name", "model": "exact model number"}}, ...]}}'
    )
    response = _client().messages.create(
        model=settings.model_sonnet,
        max_tokens=2048,
        tools=[_WEB_SEARCH_TOOL],
        messages=[{"role": "user", "content": prompt}],
    )
    parsed = parse_json_response(_final_text(response))
    competitors = parsed.get("competitors", []) if isinstance(parsed, dict) else parsed
    return [c for c in competitors if isinstance(c, dict) and c.get("name") and c.get("model")]


@retry(**_RATE_LIMIT_RETRY)
def fetch_one(name: str, model: str, category: str) -> CompetitorSpec:
    """Fetch one competitor's spec via a web-search-grounded call.

    Raises on missing API key, a malformed response, or a response missing
    required fields — callers should catch and skip that competitor."""
    prompt = (
        f"Search the web for the real, current specifications for the {name} {category}, model "
        f"{model}. After searching, respond with ONLY a single JSON object (no markdown, no "
        f"explanation) with exactly these fields: model, price_usd (number — your best estimate "
        f"of current street price if MSRP is unclear), key_specs (an object of 5-8 of the most "
        f"purchase-relevant spec attributes for this product category, e.g. for a TV: "
        f'{{"Display": "...", "Panel": "...", "HDR": "..."}}; for a refrigerator: {{"Capacity": '
        f'"...", "Ice Maker": "...", "Energy Rating": "..."}} — adapt the keys to what actually '
        f"matters for this category), strengths (list of strings), weaknesses (list of strings), "
        f"sources (list of URLs you grounded this on). For any value you cannot verify, use 'N/A' "
        f"rather than guessing or fabricating a technical detail."
    )
    response = _client().messages.create(
        model=settings.model_sonnet,
        max_tokens=2048,
        tools=[_WEB_SEARCH_TOOL],
        messages=[{"role": "user", "content": prompt}],
    )
    parsed = parse_json_response(_final_text(response))
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected a JSON object, got {type(parsed).__name__}")
    parsed["fetched_at"] = datetime.now(timezone.utc).isoformat()
    return CompetitorSpec(**parsed)


def refresh_competitors_for_product(model_code: str, product_name: str, category: str) -> dict[str, dict]:
    """Discover this product's real competitors, fetch each one's spec, and cache the
    result under data/raw/{model_code}/competitors.json. Returns a per-competitor summary
    dict for the CLI to render: {"ok": bool, "error": str|None, "spec": CompetitorSpec|None}.
    One failure doesn't block the others."""
    results: dict[str, dict] = {}
    try:
        discovered = discover_competitors(product_name, category, model_code)
    except (RuntimeError, ValueError, json.JSONDecodeError, anthropic.APIError) as e:
        console.print(f"[red]Competitor discovery failed: {e}")
        return results

    if not discovered:
        console.print("[yellow]No competitors discovered.")
        return results

    cache: dict[str, dict] = {}
    for i, comp in enumerate(discovered):
        # Each fetch_one call burns several round-trips via web_search internally, consuming a
        # meaningful chunk of even a generous per-minute token budget — space sequential calls out
        # by roughly the rate-limit window's reset interval, not just a few seconds, so each call
        # starts with a fresh budget instead of immediately tripping the same 429 as the last one.
        if i > 0:
            console.print("[dim]Waiting 30s before the next competitor (rate-limit spacing)...")
            time.sleep(30)
        name, model = comp["name"], comp["model"]
        try:
            spec = fetch_one(name, model, category)
            cache[name] = spec.model_dump()
            results[name] = {"ok": True, "error": None, "spec": spec}
        except (RuntimeError, ValueError, ValidationError, json.JSONDecodeError, anthropic.APIError) as e:
            results[name] = {"ok": False, "error": str(e), "spec": None}

    if cache:
        path = _cache_path(model_code)
        path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
        console.print(f"[green]Cached {len(cache)} competitor(s) -> {path}")

    return results
