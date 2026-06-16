"""Extract product specifications from PDF or web."""
from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
from rich.console import Console

from src.config import settings
from src.data.models import ProductSpec

console = Console()

# Known spec for Samsung UN50U7900FFXZA (Crystal UHD U7900F)
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


async def fetch_spec_from_web(model_code: str) -> dict:
    """Try to fetch spec from Samsung.com API."""
    url = f"https://www.samsung.com/us/televisions-home-theater/tvs/all-tvs/{model_code.lower()}-un{model_code.lower()}/specifications/"
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            # In production, parse the spec page HTML
            return {}
        except Exception:
            return {}


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
    """Return product spec, using hardcoded data as authoritative source."""
    spec_path = settings.raw_data_path / f"{model_code}_spec.json"
    if spec_path.exists():
        with open(spec_path) as f:
            data = json.load(f)
        return ProductSpec(**data)

    spec_data = SAMSUNG_U7900F_SPEC.copy()

    with open(spec_path, "w") as f:
        json.dump(spec_data, f, indent=2)

    return ProductSpec(**spec_data)


def get_competitor_specs() -> dict[str, dict]:
    return COMPETITOR_SPECS
