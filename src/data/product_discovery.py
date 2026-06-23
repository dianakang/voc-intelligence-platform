"""Discover product URLs/model codes from samsung.com/us's sitemap.xml.

Avoids rendering JS-heavy category listing pages: the sitemap index
(https://www.samsung.com/us/sitemap.xml, referenced from robots.txt) points to
b2c-sitemap.xml, which in turn points to per-division sub-sitemaps. Product
page slugs in those sub-sitemaps consistently end in '-sku-{model_code}/',
which both confirms a URL is a product page and gives its model code.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree

import httpx
from rich.console import Console

from src.config import settings
from src.data.models import DiscoveredProduct, DiscoveryManifest

console = Console()

SITEMAP_INDEX_URL = "https://www.samsung.com/us/sitemap.xml"
B2C_SITEMAP_URL = "https://www.samsung.com/us/b2c-sitemap.xml"

_SKU_RE = re.compile(r"-sku-([a-z0-9-]+)/?$", re.IGNORECASE)
_CATEGORY_RE = re.compile(r"^[a-z0-9-]+$")


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def extract_model_code(url: str) -> Optional[str]:
    """Pull the model code out of a samsung.com product URL's '-sku-{model_code}/'
    slug suffix — the same pattern used to recognize product pages during discovery."""
    m = _SKU_RE.search(url)
    return m.group(1).upper() if m else None


async def _fetch_locs(client: httpx.AsyncClient, sitemap_url: str) -> list[str]:
    """Fetch a sitemap (index or urlset) and return every <loc> URL it lists."""
    resp = await client.get(sitemap_url)
    resp.raise_for_status()
    root = ElementTree.fromstring(resp.content)
    return [el.text.strip() for el in root.iter() if _strip_ns(el.tag) == "loc" and el.text]


async def discover_category(
    category: str, max_sub_sitemaps: Optional[int] = None
) -> list[DiscoveredProduct]:
    """Walk the b2c sitemap tree and return every product URL under `category`'s
    path prefix whose slug matches the '-sku-{model_code}/' pattern, deduped by
    model code. `max_sub_sitemaps` is a debugging knob to fetch fewer sub-sitemaps.

    `category` is any samsung.com/us top-level URL path segment (e.g. "tvs",
    "refrigerators", "audio-devices") — no fixed whitelist, since the category name
    and its URL path segment are the same string in Samsung's URL scheme."""
    if not _CATEGORY_RE.match(category):
        raise ValueError(f"Invalid category '{category}' — expected a URL path segment like 'tvs' or 'refrigerators'")
    path_prefix = f"/us/{category}/"

    async with httpx.AsyncClient(timeout=30.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
        sub_sitemap_urls = await _fetch_locs(client, B2C_SITEMAP_URL)
        if max_sub_sitemaps:
            sub_sitemap_urls = sub_sitemap_urls[:max_sub_sitemaps]

        products: dict[str, DiscoveredProduct] = {}
        for sub_url in sub_sitemap_urls:
            try:
                locs = await _fetch_locs(client, sub_url)
            except Exception as e:
                console.print(f"[yellow]Failed to fetch sub-sitemap {sub_url}: {e}")
                continue
            for loc in locs:
                if path_prefix not in loc:
                    continue
                m = _SKU_RE.search(loc)
                if not m:
                    continue
                model_code = m.group(1).upper()
                products.setdefault(
                    model_code, DiscoveredProduct(model_code=model_code, url=loc, category=category)
                )

    return list(products.values())


def _manifest_path(category: str) -> Path:
    return settings.raw_data_path / "_discovery" / f"{category}.json"


def load_cached_discovery(category: str) -> Optional[DiscoveryManifest]:
    path = _manifest_path(category)
    if not path.exists():
        return None
    return DiscoveryManifest(**json.loads(path.read_text(encoding="utf-8")))


def save_discovery(category: str, products: list[DiscoveredProduct]) -> DiscoveryManifest:
    manifest = DiscoveryManifest(
        category=category,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        products=products,
    )
    path = _manifest_path(category)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest.model_dump(), indent=2), encoding="utf-8")
    console.print(f"[green]Discovered {len(products)} products for category '{category}' -> {path}")
    return manifest
