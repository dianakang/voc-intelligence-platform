"""Extract product specifications by live-scraping the Samsung product page.

The product page itself fetches its full spec table from a JSON API
(`bridge-data`) after the initial page load; we call that same API directly
instead of rendering the page in a browser. Priority order for grounding
data: live scrape (__NEXT_DATA__ + spec API) -> cached snapshot -> hardcoded
fallback dict below (used only if both the network and the cache fail).
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Optional

import httpx
from rich.console import Console

from src.config import settings
from src.data.models import ProductSpec, SpecGroup

console = Console()

BRIDGE_DATA_URL = "https://www.samsung.com/us/gapi/v1/bridge/cacheable/bridge-data"

# Real Samsung spec-table group names -> ProductSpec category dict field.
# Anything not listed here folds into "other".
GROUP_TO_FIELD = {
    "Display": "display",
    "Video": "hdr",
    "Audio": "audio",
    "Smart Service": "smart_tv",
    "Smart Feature": "smart_tv",
    "Game Feature": "gaming",
    "Connectivity": "connectivity",
    "Design": "design",
    "Power & Eco Solution": "energy",
}

# Hardcoded fallback for Samsung UN50U7900FFXZA (Crystal UHD U7900F), used
# only when both the live scrape and the cached snapshot are unavailable.
SAMSUNG_U7900F_SPEC: dict = {
    "product_name": "50-inch Class Crystal UHD U7900F 4K Smart TV",
    "model": "UN50U7900FFXZA",
    "category": "TV > UHD 4K TV",
    "screen_size": "50 inch",
    "series": "U7900F Crystal UHD",
    "display": {
        "type": "Crystal UHD (VA panel)",
        "size": "50 inch",
        "backlight": "DLED",
        "brightness": "HDR10+ compatible",
        "refresh_rate": "60Hz (Motion Xcelerator 120)",
        "dimming": "Auto",
        "wide_color_gamut": "No",
        "local_dimming": "No",
    },
    "resolution": {
        "native": "3840 x 2160 (4K UHD)",
        "upscaling": "Crystal Processor 4K",
        "hdr_support": ["HDR10+", "HLG"],
    },
    "hdr": {
        "hdr10_plus": True,
        "dolby_vision": False,
        "hlg": True,
        "hdr10": True,
    },
    "smart_tv": {
        "os": "Tizen OS",
        "voice_assistant": ["Bixby", "Alexa built-in", "Google Assistant"],
        "gaming_hub": True,
        "samsung_health": True,
        "samsung_knox": True,
        "ambient_mode": True,
        "apps": "Samsung Smart TV Hub",
        "account_requirement": "Samsung Account required to use streaming apps, SmartThings, and other network-based smart features",
        "free_content": "Endless free content via Samsung TV Plus (ad-supported live channels)",
    },
    "gaming": {
        "input_lag_4k_60hz": "~13ms",
        "vrr": "FreeSync Premium",
        "auto_low_latency_mode": True,
        "game_mode": True,
        "game_bar": True,
        "cloud_gaming": True,
    },
    "audio": {
        "output_power": "20W",
        "speakers": "2.0 channel",
        "dolby_atmos": False,
        "q_symphony": False,
        "adaptive_sound": True,
        "bass_boost": True,
        "ots_lite": True,
    },
    "connectivity": {
        "hdmi": "3x HDMI (HDMI 2.1 x1, HDMI 2.0 x2)",
        "usb": "2x USB 2.0",
        "wifi": "WiFi 5 (802.11ac)",
        "bluetooth": "5.2",
        "ethernet": "1x RJ-45",
        "optical": "1x Digital Audio Out (Optical)",
        "ci_slot": False,
    },
    "design": {
        "stand_type": "Slim Y-Type",
        "vesa": "200 x 200mm",
        "thickness_without_stand": "25.7mm",
        "bezel": "Boundless 3-sided design",
        "color": "Titan Black",
    },
    "energy": {
        "energy_star": True,
        "power_consumption": "85W",
        "standby": "0.5W",
        "annual_energy": "122 kWh",
    },
    "other": {
        "price_usd": 397.99,
        "release_year": 2024,
        "warranty": "1 year",
        "easyinstallation": True,
        "one_connect_box": False,
        "solar_remote": False,
        "eco_remote": True,
        "delivery_availability": "Standard shipping; in-store pickup availability varies by location and may show as limited/unavailable",
        "marketing_highlights": [
            "Crystal Processor 4K",
            "MetalStream Design",
            "Samsung Knox Security",
            "Endless Free Content (Samsung TV Plus)",
        ],
    },
}

COMPETITOR_SPECS: dict[str, dict] = {
    "TCL Q6": {
        "model": "55Q650G",
        "price_usd": 349.99,
        "display_type": "QLED",
        "panel": "VA",
        "refresh_rate": "60Hz (Motion Rate 120)",
        "local_dimming": "Full Array Local Dimming",
        "hdr": ["Dolby Vision", "HDR10+", "HLG"],
        "audio_power": "30W",
        "dolby_atmos": True,
        "os": "Google TV",
        "hdmi": "4x HDMI (HDMI 2.1 x2)",
        "vrr": "FreeSync Premium",
        "gaming_input_lag": "~12ms",
        "wifi": "WiFi 6 (802.11ax)",
        "strengths": [
            "QLED panel - better color volume than Crystal UHD",
            "Full Array Local Dimming for better contrast",
            "Dolby Vision + Dolby Atmos support",
            "Google TV - broader app ecosystem",
            "Lower price point",
            "Better audio output (30W vs 20W)",
        ],
        "weaknesses": [
            "Google TV can be slower than Tizen",
            "TCL brand perceived as less premium",
            "Less robust Samsung ecosystem integration",
            "Build quality feels cheaper",
        ],
    },
    "Hisense A7": {
        "model": "50A7H",
        "price_usd": 279.99,
        "display_type": "4K UHD ULED",
        "panel": "VA",
        "refresh_rate": "60Hz",
        "local_dimming": "Yes",
        "hdr": ["Dolby Vision", "HDR10+", "HLG"],
        "audio_power": "24W",
        "dolby_atmos": True,
        "os": "VIDAA U6",
        "hdmi": "3x HDMI",
        "vrr": "No",
        "gaming_input_lag": "~15ms",
        "wifi": "WiFi 5",
        "strengths": [
            "Dolby Vision and Dolby Atmos at this price",
            "ULED technology - better colors than standard UHD",
            "Significantly cheaper price",
            "Good out-of-box picture calibration",
        ],
        "weaknesses": [
            "VIDAA OS - limited app selection",
            "No VRR/FreeSync for gaming",
            "Higher input lag than Samsung",
            "Less reliable smart features",
            "Hisense brand perceived as budget",
        ],
    },
    "LG UT70": {
        "model": "50UT7050PSA",
        "price_usd": 399.99,
        "display_type": "4K UHD",
        "panel": "IPS",
        "refresh_rate": "60Hz",
        "local_dimming": "No",
        "hdr": ["HDR10", "HLG"],
        "audio_power": "20W",
        "dolby_atmos": False,
        "os": "webOS 23",
        "hdmi": "3x HDMI (HDMI 2.1 x1)",
        "vrr": "FreeSync",
        "gaming_input_lag": "~9ms",
        "wifi": "WiFi 5",
        "strengths": [
            "IPS panel - better viewing angles than VA",
            "Excellent low input lag for gaming (~9ms)",
            "webOS - very smooth and user-friendly",
            "Better motion handling on IPS",
            "LG brand trust and reliability",
        ],
        "weaknesses": [
            "IPS has worse black levels than VA (Samsung)",
            "No local dimming",
            "No HDR10+ (only HDR10)",
            "No Dolby Vision or Dolby Atmos",
            "Slightly higher price",
        ],
    },
}


def _extract_next_data(html: str) -> dict:
    """Parse the Next.js __NEXT_DATA__ blob embedded in the page (price, stock, marketing copy)."""
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}


def _extract_json_ld(html: str) -> list[dict]:
    """Parse schema.org JSON-LD blocks (fallback source for name/price/description)."""
    blocks = re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.DOTALL
    )
    parsed = []
    for block in blocks:
        try:
            parsed.append(json.loads(block))
        except json.JSONDecodeError:
            continue
    return parsed


def _find_product_entry(next_data: dict, model_code: str) -> Optional[dict]:
    try:
        products = next_data["props"]["pageProps"]["productData"]["products"]
    except (KeyError, TypeError):
        return None
    for p in products:
        if str(p.get("modelCode", "")).upper() == model_code.upper():
            return p
    return products[0] if products else None


async def _fetch_full_spec_groups(group_id: str, model_code: str) -> tuple[list[dict], list[str]]:
    """Call the same JSON spec API the product page calls after load — no browser needed."""
    params = [
        ("data_type", "Specs"),
        ("data_type", "Support"),
        ("data_type", "RelatedModels"),
        ("store_type", "B2C"),
        ("group_id", group_id),
        ("version", "v2"),
    ]
    async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
        resp = await client.get(BRIDGE_DATA_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    entries = data.get("Specs", [])
    entry = next(
        (s for s in entries if str(s.get("modelCode", "")).upper() == model_code.upper()), None
    )
    if not entry:
        return [], []
    groups = entry.get("fullSpecs", [])
    highlights = [h["value"] for h in entry.get("specHighlights", []) if h.get("value")]
    return groups, highlights


def _map_to_product_spec_dict(
    model_code: str,
    product_entry: dict,
    spec_groups: list[dict],
    spec_highlights: list[str],
) -> dict:
    """Map the live spec-table groups + page product data onto the ProductSpec schema."""
    categories: dict[str, dict] = {
        "display": {}, "resolution": {}, "hdr": {}, "smart_tv": {}, "gaming": {},
        "audio": {}, "connectivity": {}, "design": {}, "energy": {}, "other": {},
    }
    raw_groups: list[dict] = []

    for group in spec_groups:
        name = group.get("groupName", "")
        items = {
            s["name"]: s["value"]
            for s in group.get("specList", [])
            if s.get("name") and s.get("value")
        }
        raw_groups.append(SpecGroup(group_name=name, items=items).model_dump())
        field = GROUP_TO_FIELD.get(name, "other")
        categories[field].update(items)

    if "Resolution" in categories["display"]:
        categories["resolution"]["Resolution"] = categories["display"]["Resolution"]
    if "Picture Upscale" in categories["hdr"]:
        categories["resolution"]["Upscaling"] = categories["hdr"]["Picture Upscale"]

    price = product_entry.get("currentPrice") or product_entry.get("msrpPrice")
    stock_flag = product_entry.get("stockFlag")
    fulfillment = product_entry.get("fulfillmentInfo") or {}

    categories["other"].update({
        "price_usd": price,
        "msrp_usd": product_entry.get("msrpPrice"),
        "stock_status": "in_stock" if stock_flag == "Y" else "limited_or_unavailable",
        "delivery_availability": (
            fulfillment.get("esd_custom_stock_message")
            or fulfillment.get("edd_custom_stock_message")
            or ("Standard delivery available" if stock_flag == "Y" else "Delivery/pickup availability limited")
        ),
        "marketing_highlights": [
            kf["desc"] for kf in (product_entry.get("keySummary") or []) if kf.get("desc")
        ],
    })
    categories["smart_tv"].setdefault(
        "account_requirement",
        "Samsung Account required to use streaming apps, SmartThings, and other network-based smart features",
    )

    return {
        "product_name": product_entry.get("productTitle") or product_entry.get("modelName") or model_code,
        "model": model_code,
        "category": "TV",
        "screen_size": categories["display"].get("Screen Size", ""),
        "series": product_entry.get("familyMktName", ""),
        **categories,
        "raw_spec_groups": raw_groups,
        "spec_highlights": spec_highlights,
    }


async def fetch_spec_from_web(model_code: str, url: Optional[str] = None) -> ProductSpec:
    """Live-scrape the product page + its spec API and build a ProductSpec from it.

    Saves the raw page snapshot (page.html, page_meta.json) under
    data/raw/{model_code}/ so the spec-parsing logic above can be changed and
    re-run later without re-fetching the page.
    """
    from src.data.scraper import SamsungReviewScraper  # local import avoids a module cycle

    target_url = url or settings.samsung_product_url
    async with SamsungReviewScraper() as scraper:
        html, status_code = await scraper.fetch_page_html(target_url)
        scraper.save_page_snapshot(html, model_code, target_url, status_code)

    next_data = _extract_next_data(html)
    product_entry = _find_product_entry(next_data, model_code)
    if not product_entry:
        # Fall back to JSON-LD for at least name/price if __NEXT_DATA__ is missing/changed
        ld_blocks = [b for b in _extract_json_ld(html) if b.get("@type") == "Product"]
        if not ld_blocks:
            raise ValueError(f"Could not locate product data for {model_code} on {target_url}")
        ld = ld_blocks[0]
        product_entry = {
            "modelCode": model_code,
            "productTitle": ld.get("name"),
            "currentPrice": (ld.get("offers") or {}).get("price"),
        }

    group_id = product_entry.get("familyId") or product_entry.get("buySpaId")
    spec_groups, spec_highlights = [], []
    if group_id:
        spec_groups, spec_highlights = await _fetch_full_spec_groups(str(group_id), model_code)

    spec_dict = _map_to_product_spec_dict(model_code, product_entry, spec_groups, spec_highlights)
    spec_dict["spec_source"] = "live_scrape"
    return ProductSpec(**spec_dict)


def load_spec_from_pdf(pdf_path: Path) -> dict:
    """Extract spec data from a product PDF."""
    try:
        import fitz  # pymupdf

        doc = fitz.open(str(pdf_path))
        text = ""
        for page in doc:
            text += page.get_text()
        return {"raw_text": text}
    except Exception as e:
        console.print(f"[yellow]PDF extraction failed: {e}")
        return {}


def get_samsung_spec(model_code: str) -> ProductSpec:
    """Live-scrape the current product page for spec data; fall back to the
    last cached snapshot, then to the hardcoded dict, only if scraping fails."""
    spec_path = settings.raw_product_dir(model_code) / "spec.json"

    try:
        spec = asyncio.run(fetch_spec_from_web(model_code))
        spec_path.write_text(json.dumps(spec.model_dump(), indent=2, default=str), encoding="utf-8")
        console.print(f"[green]Live-scraped spec for {model_code} (source: live_scrape)")
        return spec
    except Exception as e:
        console.print(f"[yellow]Live spec scrape failed ({e}); falling back to cache/hardcoded data")

    if spec_path.exists():
        with open(spec_path) as f:
            data = json.load(f)
        data["spec_source"] = "cache"
        console.print(f"[yellow]Using cached spec for {model_code} (source: cache)")
        return ProductSpec(**data)

    console.print(f"[red]No live or cached spec available for {model_code}; using hardcoded fallback")
    spec_data = {**SAMSUNG_U7900F_SPEC, "spec_source": "hardcoded_fallback"}
    return ProductSpec(**spec_data)


def get_competitor_specs() -> dict[str, dict]:
    return COMPETITOR_SPECS
