"""One-off: regenerate just `marketing_recommendations` for an already-analyzed model,
without re-running the full ~11-agent pipeline. Loads cached raw reviews + spec, replays
cleaning/taxonomy/RAG-indexing (no network calls — spec is read from the on-disk cache
rather than via get_samsung_spec(), which would otherwise attempt a live scrape), then
calls MarketingAnalysisAgent and patches the saved report JSON in place.

Usage: python scripts/regenerate_marketing_section.py <MODEL_CODE>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.marketing_analysis import MarketingAnalysisAgent
from src.agents.review_cleaning import ReviewCleaningAgent
from src.agents.voc_taxonomy import VOCTaxonomyAgent
from src.config import settings
from src.data.models import ProductSpec, Review, VOCAnalysisResult
from src.data.scraper import sample_reviews_stratified
from src.rag.chunker import chunk_reviews
from src.rag.retriever import ReviewRetriever
from src.rag.vector_store import VectorStore


def main(model_code: str) -> None:
    out_path = settings.output_path / f"{model_code}_voc_result.json"
    with open(out_path) as f:
        data = json.load(f)
    # The saved JSON may still have the pre-target_audience marketing_recommendations
    # shape; drop it for loading purposes — we only need satisfaction_drivers/complaints
    # from this snapshot, and we overwrite marketing_recommendations entirely below.
    result = VOCAnalysisResult(**{**data, "marketing_recommendations": None})

    raw_path = settings.raw_product_dir(model_code) / "reviews.json"
    with open(raw_path) as f:
        all_reviews = [Review(**r) for r in json.load(f)]

    spec_path = settings.raw_product_dir(model_code) / "spec.json"
    with open(spec_path) as f:
        spec = ProductSpec(**json.load(f))

    sampled = sample_reviews_stratified(all_reviews, result.total_reviews)
    cleaned = ReviewCleaningAgent().clean_reviews(sampled)
    classified = VOCTaxonomyAgent().classify_reviews(cleaned, category=spec.category)

    VectorStore.clear_process_memory()
    vector_store = VectorStore()
    chunks = chunk_reviews(classified)
    if chunks:
        vector_store.upsert_chunks(chunks)
    retriever = ReviewRetriever(vector_store, {r.review_id: r for r in classified})

    result = MarketingAnalysisAgent().analyze(classified, retriever, result, product_spec=spec)
    if result.marketing_recommendations is None:
        print(f"Marketing analysis failed for {model_code}; output JSON left unchanged.")
        return

    data["marketing_recommendations"] = result.marketing_recommendations.model_dump()
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"Patched {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/regenerate_marketing_section.py <MODEL_CODE>")
        sys.exit(1)
    main(sys.argv[1])
