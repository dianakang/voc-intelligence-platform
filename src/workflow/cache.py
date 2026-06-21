"""Dev replay cache: detect "unchanged input since last run" to skip re-running all LLM agents.

Opt-in only (via --skip-if-cached / skip_if_cached) — never used unless explicitly requested.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

from src.config import settings
from src.data.models import ProductSpec, Review


def compute_input_hash(
    reviews: list[Review],
    model_code: str,
    max_reviews: int,
    spec: ProductSpec,
) -> str:
    """Hash the raw (pre-cleaning) review set + model_code + max_reviews + live spec content."""
    review_payload = sorted(
        ({"id": r.review_id, "text": r.text, "rating": r.rating} for r in reviews),
        key=lambda r: r["id"],
    )
    payload = {
        "model_code": model_code,
        "max_reviews": max_reviews,
        "review_count": len(reviews),
        "reviews": review_payload,
        "spec": spec.model_dump(mode="json"),
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _manifest_path(model_code: str) -> Path:
    return settings.output_path / f"{model_code}_voc_result.manifest.json"


def load_manifest(model_code: str) -> Optional[dict]:
    path = _manifest_path(model_code)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_manifest(model_code: str, input_hash: str) -> None:
    path = _manifest_path(model_code)
    with open(path, "w") as f:
        json.dump({"input_hash": input_hash, "model_code": model_code}, f, indent=2)


def is_cache_hit(model_code: str, input_hash: str) -> bool:
    manifest = load_manifest(model_code)
    if not manifest:
        return False
    result_path = settings.output_path / f"{model_code}_voc_result.json"
    return manifest.get("input_hash") == input_hash and result_path.exists()
