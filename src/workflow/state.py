"""LangGraph workflow state definition."""
from __future__ import annotations

from typing import Any, Optional
from typing_extensions import TypedDict

from src.data.models import Review, ProductSpec, VOCAnalysisResult


class VOCWorkflowState(TypedDict):
    """Shared state passed between LangGraph nodes."""

    # Input
    model_code: str
    max_reviews: int
    skip_if_cached: bool  # opt-in dev replay cache — see src/workflow/cache.py

    # Data collection outputs
    reviews: list[Review]  # the analyzed sample (stratified by rating, size = max_reviews)
    all_reviews: list[Review]  # the full fetched population — only used for cheap heuristic scans
    # (e.g. contradiction candidate flagging) that need to see rare cases the sample might miss
    total_reviews_available: int  # real population size discovered during scraping
    product_spec: Optional[ProductSpec]
    competitor_specs: dict[str, dict]
    input_hash: str  # computed in collect_data, used to detect a cache hit

    # Processing outputs
    cleaned_reviews: list[Review]
    reviews_by_id: dict[str, Review]

    # RAG
    rag_built: bool

    # Analysis result (accumulates through pipeline)
    result: Optional[VOCAnalysisResult]

    # Status tracking for UI
    current_step: str
    agent_statuses: dict[str, str]  # agent_name -> "pending"|"running"|"done"|"error"
    errors: list[str]
    progress_pct: int
