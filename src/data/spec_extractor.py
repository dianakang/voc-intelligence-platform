"""Extract product specifications from the assignment-provided spec PDF,
merged with a live scrape of the Samsung product page.

The PDF (parsed by parse_u7900f_spec_pdf) is authoritative for static spec
fields (display/audio/design/gaming/etc) since it's the assignment's source
of truth and doesn't change. It has no price/stock/delivery/account data, so
a live scrape always also runs and contributes only those commerce-dynamic
fields on top of the PDF data. If the PDF file is missing, falls back to
live-scrape-only -> cached snapshot -> hardcoded dict below.
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


def _category_from_url(url: str) -> str:
    """Derive a human-readable product category from the URL's first /us/{category}/ path
    segment (e.g. '/us/tvs/...' -> 'TV', '/us/refrigerators/...' -> 'Refrigerator'). This
    platform was originally built TV-only, so several agents key behavior off this category
    (e.g. skipping TV-competitor positioning for non-TV products) — it must reflect the actual
    product, not be hardcoded."""
    match = re.search(r"/us/([a-z0-9-]+)/", url)
    if not match:
        return "Unknown"
    segment = match.group(1)
    if segment == "tvs":
        return "TV"
    label = segment.rstrip("s").replace("-", " ").strip()
    return label.title() if label else "Unknown"


def _map_to_product_spec_dict(
    model_code: str,
    product_entry: dict,
    spec_groups: list[dict],
    spec_highlights: list[str],
    category: str = "TV",
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
    if category == "TV":
        categories["smart_tv"].setdefault(
            "account_requirement",
            "Samsung Account required to use streaming apps, SmartThings, and other network-based smart features",
        )

    return {
        "product_name": product_entry.get("productTitle") or product_entry.get("modelName") or model_code,
        "model": model_code,
        "category": category,
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
        try:
            spec_groups, spec_highlights = await _fetch_full_spec_groups(str(group_id), model_code)
        except Exception as e:
            # The detailed spec-table API isn't available for every product/division (e.g. 404s
            # on some non-TV categories) — degrade to name/price-only rather than failing the whole
            # spec fetch and falling back to a hardcoded, wrong-category spec.
            console.print(f"[yellow]Spec-table fetch failed for {model_code} ({e}); continuing with name/price only")

    category = _category_from_url(target_url)
    spec_dict = _map_to_product_spec_dict(model_code, product_entry, spec_groups, spec_highlights, category=category)
    spec_dict["spec_source"] = "live_scrape"
    return ProductSpec(**spec_dict)


# U7900F spec-PDF label -> ProductSpec category dict. Tailored to this exact
# document; anything not listed here is dropped (not folded into "other") since
# an unrecognized label here is more likely a parsing artifact than real data.
PDF_LABEL_TO_FIELD: dict[str, str] = {
    # PICTURE (PROCESSING)
    "Processor": "display", "Upscaling": "resolution",
    "Variable Refresh Rate (VRR)": "display", "Motion Handling": "display",
    "Contrast Enhancer": "display", "Object Motion Enhancing": "display", "Color": "display",
    "HDR (High Dynamic Range)": "hdr", "HDR10+": "hdr", "Auto HDR Remastering": "hdr",
    "Adaptive Picture": "hdr", "Supersize Picture Enhancer": "hdr",
    # PICTURE (PANEL)
    "Display Type": "display", "Refresh Rate": "display", "Lighting Technology": "display",
    "Display Resolution": "resolution", "Anti Reflection": "display",
    "Viewing Angle": "display", "Dimming Technology": "display",
    # TV ART FEATURES
    "Art Mode": "other", "Art Store": "other",
    # SECURITY
    "Knox Vault": "other", "Knox Security": "other",
    # SMART TV FEATURES
    "Operating System": "smart_tv", "AI TV": "smart_tv", "Free Ad Supported TV": "smart_tv",
    "Smart Home Connectivity": "smart_tv", "Smart Assistants (Built-In)": "smart_tv",
    "Smart Assistants (Works with)": "smart_tv", "Far-Field Voice Interactions": "smart_tv",
    "Web Browser": "smart_tv", "SmartThings Hub": "smart_tv", "Samsung Health": "smart_tv",
    "Multi Device Experience": "smart_tv", "Multi-View": "smart_tv", "Ambient Mode": "smart_tv",
    "Buds Auto Switch": "smart_tv", "Works with Apple Airplay": "smart_tv",
    "Works with Google Cast": "smart_tv", "Daily+": "smart_tv", "Daily Board": "smart_tv",
    "Workout Tracker": "smart_tv", "Karaoke Mic": "smart_tv", "Multi-Control": "smart_tv",
    "ConnecTime": "smart_tv", "Screen Vitals": "smart_tv", "Storage Share": "smart_tv",
    # AUDIO
    "Speaker Type": "audio", "Output Power": "audio", "Dolby Atmos": "audio",
    "Object Tracking Sound (OTS)": "audio", "Q-Symphony": "audio",
    "Active Voice Amplifier (AVA)": "audio", "Adaptive Sound": "audio",
    "Bluetooth Audio": "audio", "360 Audio": "audio",
    # CONNECTIVITY
    "Wi-Fi": "connectivity", "Bluetooth": "connectivity", "One Connect Box": "connectivity",
    "HDMI Input": "connectivity", "HDMI Maximum Input Rate": "connectivity",
    "HDMI Audio Return Channel": "connectivity", "HDMI-CEC": "connectivity",
    "USB Ports": "connectivity", "Ethernet (LAN)": "connectivity",
    "Digital Audio Out (Optical)": "connectivity", "RF Connection": "connectivity",
    "RS-232C Input": "connectivity",
    # DESIGN
    "TV Design": "design", "Bezel Type": "design", "Front Color": "design",
    "Stand Type": "design", "Stand Color": "design", "Adjustable Stand": "design",
    # SAMSUNG VISION AI
    "Live Translate": "other", "Click to Search": "other", "Generative Wallpaper": "other",
    "Pet & Family Care": "other", "Home Insight": "other",
    "Universal Gestures/Quick Control": "other",
    # GAMING
    "Gaming Hub": "gaming", "Cloud Gaming": "gaming", "AI Auto Game Mode": "gaming",
    "ALLM (Auto Low Latency Mode)": "gaming", "Game Motion Plus": "gaming",
    "Super Ultra Wide Game View": "gaming", "Game Bar": "gaming", "Mini Map Zoom": "gaming",
    "VRR Standard": "gaming", "HGiG": "gaming", "Hue Sync": "gaming",
    # POWER
    "Power Supply (V)": "energy", "Standby Power Consumption (W)": "energy",
    "Typical Power Consumption (W)": "energy", "Max Power Consumption (W)": "energy",
    # INCLUDED ACCESSORIES
    "Remote Control": "other", "Power Cable": "other",
}

# All-caps lines that are section headers, not "Label: Value" data. The PDF's
# multi-column layout means PyMuPDF extracts these out of order relative to
# their items (sometimes trailing, sometimes leading, sometimes neither), so
# headers are only used to reset continuation-line tracking, not to group items.
PDF_SECTION_HEADERS = {
    "PICTURE (PANEL)", "PICTURE (PROCESSING)", "AUDIO", "DESIGN", "CONNECTIVITY",
    "SAMSUNG VISION AI", "TV ART FEATURES", "SMART TV FEATURES1", "SMART TV FEATURES",
    "GAMING", "SECURITY", "POWER", "INCLUDED ACCESSORIES", "CLASS HIERARCHY",
    "SIZE CLASS", "TOP  10 KEY FEATURES", "MODELS",
}

_FOOTNOTE_SUFFIX_RE = re.compile(r"(?<=[a-zA-Z\)%])\d+$")
_LABEL_VALUE_RE = re.compile(r"^([A-Za-z0-9][\w \(\)/.,+'’&-]*):\s*(.*)$")
_FEATURE_LINE_RE = re.compile(r"^\d+\.\s*(.+)$")
_SIZE_VALUE_RE = re.compile(r'^(\d+)[”"]?:\s*(.+)$')


def _strip_footnote(text: str) -> str:
    """Drop a trailing footnote-reference digit, e.g. 'Samsung TV Plus1' -> 'Samsung TV Plus'."""
    return _FOOTNOTE_SUFFIX_RE.sub("", text).strip()


def parse_u7900f_spec_pdf(pdf_path: Path) -> dict:
    """Parse the assignment-provided U7900F spec PDF into a ProductSpec-shaped dict.

    Tailored to this exact document, not a generic PDF-spec parser (single
    product/PDF, per the assignment's stated scope). Labels are matched
    individually via PDF_LABEL_TO_FIELD rather than grouped by their section
    header, since the header-to-item association breaks under this PDF's
    multi-column layout once PyMuPDF flattens it to plain text.
    """
    import fitz  # pymupdf

    doc = fitz.open(str(pdf_path))
    page1_lines = [ln.strip() for ln in doc[0].get_text().split("\n") if ln.strip()]
    page2_text = doc[1].get_text() if doc.page_count > 1 else ""
    warranty_links = {
        m.group(1).upper(): link["uri"]
        for page in doc
        for link in page.get_links()
        if link.get("uri") and (m := re.search(r"modelCode=([A-Z0-9]+)", link["uri"], re.I))
    }
    doc.close()

    categories: dict[str, dict] = {
        "display": {}, "resolution": {}, "hdr": {}, "smart_tv": {}, "gaming": {},
        "audio": {}, "connectivity": {}, "design": {}, "energy": {}, "other": {},
    }
    spec_highlights: list[str] = []

    i = 0
    in_features = False
    last_label, last_field = None, None
    while i < len(page1_lines):
        line = page1_lines[i]

        if line == "TOP  10 KEY FEATURES":
            in_features = True
            i += 1
            continue
        if in_features:
            m = _FEATURE_LINE_RE.match(line)
            if m:
                spec_highlights.append(_strip_footnote(m.group(1)))
                i += 1
                continue
            in_features = False  # fall through and re-process this line normally

        if line in PDF_SECTION_HEADERS:
            last_label = None
            i += 1
            continue

        m = _LABEL_VALUE_RE.match(line)
        if m:
            label, value = _strip_footnote(m.group(1)), _strip_footnote(m.group(2))
            field = PDF_LABEL_TO_FIELD.get(label)
            if field is None:
                last_label = None
                i += 1
                continue
            if not value:
                # Multi-line per-size value, e.g. "Typical Power Consumption (W):"
                # followed by "55<quote>: 97W" / "50<quote>: 89W".
                parts, j = [], i + 1
                while j < len(page1_lines):
                    sm = _SIZE_VALUE_RE.match(page1_lines[j])
                    if not sm:
                        break
                    parts.append(f'{sm.group(1)}": {sm.group(2)}')
                    j += 1
                if parts:
                    categories[field][label] = ", ".join(parts)
                    i, last_label = j, None
                    continue
            categories[field][label] = value
            last_label, last_field = label, field
            i += 1
            continue

        # Continuation of the previous label's value (line-wrapped, no own colon)
        if last_label and last_field:
            categories[last_field][last_label] = f"{categories[last_field][last_label]} {line}".strip()
        i += 1

    # MODELS page: 50" is this pipeline's target model; the 55" block only
    # contributes a cheap "also available in" note (see Section 9(d) of the plan).
    sizes: dict[str, dict] = {}
    for block in re.split(r"(?=MODEL: UN\d+U7900F\b)", page2_text):
        order_m = re.search(r"ORDER CODE:\s*(\S+)", block)
        if not order_m:
            continue
        order_code = order_m.group(1).strip()
        size_m = re.search(r"SCREEN SIZE CLASS:\s*(\d+)", block)
        upc_m = re.search(r"UPC CODE:\s*(\S+)", block)
        weight_m = re.search(r"TV WITH STAND:\s*([\d.]+)", block)
        dims_m = re.search(r"TV WITHOUT STAND:\s*([\d.]+ X [\d.]+ X [\d.]+)", block)
        vesa_m = re.search(r"VESA SUPPORT:\s*(.+)", block)
        sizes[order_code] = {
            "screen_size": f'{size_m.group(1)}"' if size_m else "",
            "upc_code": upc_m.group(1) if upc_m else "",
            "weight_with_stand_lb": weight_m.group(1) if weight_m else "",
            "dimensions_without_stand_in": dims_m.group(1) if dims_m else "",
            "vesa_support": vesa_m.group(1).strip() if vesa_m else "",
            "warranty_url": warranty_links.get(order_code.upper(), ""),
        }

    target = sizes.get("UN50U7900FFXZA", {})
    other_model = next((code for code in sizes if code != "UN50U7900FFXZA"), None)

    if target.get("upc_code"):
        categories["other"]["UPC Code"] = target["upc_code"]
    if target.get("weight_with_stand_lb"):
        categories["other"]["Weight (TV with Stand, lb)"] = target["weight_with_stand_lb"]
    if target.get("dimensions_without_stand_in"):
        categories["other"]["Dimensions without Stand (W x H x D, in)"] = target["dimensions_without_stand_in"]
    if target.get("vesa_support"):
        categories["design"]["VESA Support"] = target["vesa_support"]
    if target.get("warranty_url"):
        categories["other"]["Warranty"] = target["warranty_url"]
    if other_model and sizes[other_model].get("screen_size"):
        categories["other"]["available_sizes"] = (
            f'Also available in {sizes[other_model]["screen_size"]} ({other_model}); '
            "identical spec except dimensions/weight/UPC"
        )

    raw_groups = [
        SpecGroup(group_name=field, items=items).model_dump()
        for field, items in categories.items() if items
    ]

    return {
        "product_name": '50" Class Crystal UHD U7900F 4K Smart TV',
        "model": "UN50U7900FFXZA",
        "category": "TV",
        "screen_size": '50"',
        "series": "U7900F Crystal UHD",
        **categories,
        "raw_spec_groups": raw_groups,
        "spec_highlights": spec_highlights,
        "spec_source": "pdf",
    }


# Commerce-dynamic fields the PDF never has (it's a static spec sheet); these
# only ever come from a live scrape or its cached snapshot, and get merged
# on top of the PDF-derived dict without touching its static spec fields.
_COMMERCE_OTHER_KEYS = ("price_usd", "msrp_usd", "stock_status", "delivery_availability")


def get_samsung_spec(model_code: str, url: Optional[str] = None) -> ProductSpec:
    """Build the product spec from the assignment-provided PDF (authoritative
    for static spec fields) merged with a live scrape or cached snapshot
    (the only source for commerce-dynamic fields: price, stock, delivery,
    account requirement). Falls back to live-scrape-only, then hardcoded,
    if the PDF file isn't present.

    `url` is the product page to live-scrape (defaults to
    settings.samsung_product_url if omitted). The PDF path is keyed off
    settings.samsung_model_code regardless, so it only ever applies to that
    one assignment TV — any other model_code naturally skips straight to
    live-scrape-only.
    """
    spec_path = settings.raw_product_dir(model_code) / "spec.json"
    pdf_path = settings.samsung_spec_pdf_path

    pdf_dict: Optional[dict] = None
    if model_code.upper() == settings.samsung_model_code.upper() and pdf_path.exists():
        try:
            pdf_dict = parse_u7900f_spec_pdf(pdf_path)
            console.print(f"[green]Parsed spec PDF for {model_code} ({pdf_path.name})")
        except Exception as e:
            console.print(f"[yellow]PDF spec parse failed ({e}); falling back to live-scrape-only behavior")

    commerce: Optional[dict] = None
    commerce_source = None
    try:
        live_spec = asyncio.run(fetch_spec_from_web(model_code, url=url))
        spec_path.write_text(json.dumps(live_spec.model_dump(), indent=2, default=str), encoding="utf-8")
        commerce = live_spec.model_dump()
        commerce_source = "live_scrape"
    except Exception as e:
        console.print(f"[yellow]Live spec scrape failed ({e}); falling back to cache for commerce fields")
        if spec_path.exists():
            with open(spec_path) as f:
                commerce = json.load(f)
            commerce_source = "cache"

    if pdf_dict is not None:
        if commerce is not None:
            for key in _COMMERCE_OTHER_KEYS:
                if commerce.get("other", {}).get(key) is not None:
                    pdf_dict["other"][key] = commerce["other"][key]
            account_req = commerce.get("smart_tv", {}).get("account_requirement")
            if account_req:
                pdf_dict["smart_tv"]["account_requirement"] = account_req
            pdf_dict["spec_source"] = f"pdf+{commerce_source}"
        else:
            pdf_dict["spec_source"] = "pdf_only"
        return ProductSpec(**pdf_dict)

    if commerce is not None:
        commerce["spec_source"] = commerce_source
        return ProductSpec(**commerce)

    console.print(f"[red]No PDF, live, or cached spec available for {model_code}; using hardcoded fallback")
    spec_data = {**SAMSUNG_U7900F_SPEC, "spec_source": "hardcoded_fallback"}
    return ProductSpec(**spec_data)


_COMPETITOR_STALENESS_DAYS = 90


def get_competitor_specs(model_code: str) -> dict[str, dict]:
    """Read this product's competitor specs from data/raw/{model_code}/competitors.json,
    written by `voc refresh-competitors {model_code}`. Returns {} if that command hasn't
    been run for this product yet — callers (CompetitivePositioningAgent) should skip
    competitive positioning gracefully in that case rather than fabricate a comparison."""
    from datetime import datetime, timezone

    cache_path = settings.raw_product_dir(model_code) / "competitors.json"
    if not cache_path.exists():
        return {}
    try:
        data: dict[str, dict] = json.loads(cache_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        console.print(f"[yellow]Failed to read cached competitors for {model_code} ({e})")
        return {}

    for name, spec in data.items():
        fetched_at = spec.get("fetched_at")
        if fetched_at:
            age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(fetched_at)).days
            if age_days > _COMPETITOR_STALENESS_DAYS:
                console.print(
                    f"[yellow]Cached competitor spec for {name} is {age_days} days old; "
                    f"consider re-running `voc refresh-competitors {model_code}`"
                )
    return data
