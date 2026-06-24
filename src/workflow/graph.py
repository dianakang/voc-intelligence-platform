"""LangGraph orchestration graph for the VOC Intelligence Platform."""
from __future__ import annotations

import asyncio
import concurrent.futures
from datetime import datetime
from typing import Any, Optional

from langgraph.graph import StateGraph, END
from rich.console import Console

from src.api.state import push_progress
from src.config import settings
from src.data.models import VOCAnalysisResult
from src.data.scraper import SamsungReviewScraper
from src.data.spec_extractor import get_samsung_spec, get_competitor_specs
from src.rag.chunker import chunk_reviews
from src.rag.vector_store import VectorStore
from src.rag.retriever import ReviewRetriever
from src.workflow.cache import compute_input_hash, is_cache_hit, save_manifest
from src.workflow.state import VOCWorkflowState

# Agents
from src.agents.review_cleaning import ReviewCleaningAgent
from src.agents.voc_taxonomy import VOCTaxonomyAgent
from src.agents.sentiment_analysis import SentimentAnalysisAgent
from src.agents.complaint_analysis import ComplaintAnalysisAgent
from src.agents.satisfaction_analysis import SatisfactionAnalysisAgent, ImprovementAnalysisAgent
from src.agents.marketing_analysis import MarketingAnalysisAgent
from src.agents.contradiction_analysis import ContradictionAnalysisAgent
from src.agents.importance_analysis import ImportanceAnalysisAgent
from src.agents.competitive_positioning import CompetitivePositioningAgent
from src.agents.expectation_gap import ExpectationGapAgent
from src.agents.segment_divergence import SegmentDivergenceAnalysisAgent
from src.agents.cx_action_agent import CXActionAgent
from src.agents.report_generation import ReportGenerationAgent

console = Console()


def _set_status(state: VOCWorkflowState, agent: str, status: str, step: str, pct: int) -> dict:
    statuses = dict(state.get("agent_statuses", {}))
    statuses[agent] = status
    return {"agent_statuses": statuses, "current_step": step, "progress_pct": pct}


# ── Node functions ────────────────────────────────────────────────────────────

def collect_data(state: VOCWorkflowState) -> dict:
    console.rule("[bold cyan]Step 1: Data Collection")
    update = _set_status(state, "DataCollectionAgent", "running", "Collecting reviews", 5)
    push_progress(agent_statuses=update["agent_statuses"], current_step=update["current_step"], progress_pct=5)

    model_code = state["model_code"]
    max_reviews = state.get("max_reviews", settings.max_reviews)
    url = state.get("url")

    # Fetch reviews synchronously (run async in sync context)
    async def _fetch():
        async with SamsungReviewScraper() as scraper:
            sampled, all_reviews = await scraper.collect_all_reviews(model_code, max_reviews, url=url)
            scraper.save_raw(all_reviews, model_code)  # cache the full real population, not just the sample
            return sampled, all_reviews

    reviews, all_reviews = asyncio.run(_fetch())
    total_reviews_available = len(all_reviews)
    spec = get_samsung_spec(model_code, url=url)
    competitor_specs = get_competitor_specs(model_code)
    # Hash the full fetched population (not just the sample) so a source-data change
    # is never masked by sampling happening to draw an identical-looking subset.
    input_hash = compute_input_hash(all_reviews, model_code, max_reviews, spec)

    console.print(
        f"[green]Collected {len(reviews)} reviews for analysis "
        f"(out of {total_reviews_available} available), spec loaded (source: {spec.spec_source})"
    )
    update["agent_statuses"]["DataCollectionAgent"] = "done"
    push_progress(agent_statuses=update["agent_statuses"], current_step="Reviews collected", progress_pct=15)
    return {
        **update,
        "reviews": reviews,
        "all_reviews": all_reviews,
        "total_reviews_available": total_reviews_available,
        "product_spec": spec,
        "competitor_specs": competitor_specs,
        "input_hash": input_hash,
        "progress_pct": 15,
    }


def load_cached_result(state: VOCWorkflowState) -> dict:
    """Cache hit (--skip-if-cached): skip all LLM agents, reload the previously saved result."""
    console.rule("[bold cyan]Cache hit — skipping LLM agents, reloading saved result")
    model_code = state["model_code"]
    out_path = settings.output_path / f"{model_code}_voc_result.json"

    import json
    with open(out_path) as f:
        data = json.load(f)
    result = VOCAnalysisResult(**data)

    statuses = {k: "done" for k in state.get("agent_statuses", {})}
    push_progress(agent_statuses=statuses, current_step="Loaded cached result", progress_pct=100)
    return {
        "result": result,
        "agent_statuses": statuses,
        "current_step": "Loaded cached result (--skip-if-cached)",
        "progress_pct": 100,
    }


def _route_after_collect(state: VOCWorkflowState) -> str:
    if not state.get("skip_if_cached"):
        return "clean_reviews"
    if is_cache_hit(state["model_code"], state["input_hash"]):
        return "load_cached_result"
    return "clean_reviews"


def clean_reviews(state: VOCWorkflowState) -> dict:
    console.rule("[bold cyan]Step 2: Review Cleaning")
    update = _set_status(state, "ReviewCleaningAgent", "running", "Cleaning reviews", 20)
    push_progress(agent_statuses=update["agent_statuses"], current_step="Cleaning reviews", progress_pct=20)

    agent = ReviewCleaningAgent()
    cleaned = agent.clean_reviews(state["reviews"])
    reviews_by_id = {r.review_id: r for r in cleaned}

    update["agent_statuses"]["ReviewCleaningAgent"] = "done"
    push_progress(agent_statuses=update["agent_statuses"], current_step="Reviews cleaned", progress_pct=30)
    return {**update, "cleaned_reviews": cleaned, "reviews_by_id": reviews_by_id, "progress_pct": 30}


def build_taxonomy(state: VOCWorkflowState) -> dict:
    console.rule("[bold cyan]Step 3: VOC Taxonomy + Embedding")
    update = _set_status(state, "VOCTaxonomyAgent", "running", "Building VOC taxonomy", 35)
    push_progress(agent_statuses=update["agent_statuses"], current_step="Building VOC taxonomy", progress_pct=35)

    # Taxonomy classification
    product_spec = state.get("product_spec")
    taxonomy_agent = VOCTaxonomyAgent()
    classified = taxonomy_agent.classify_reviews(
        state["cleaned_reviews"], category=product_spec.category if product_spec else None
    )

    # Build RAG index — clear stale data from any previous run first
    VectorStore.clear_process_memory()
    vector_store = VectorStore()
    chunks = chunk_reviews(classified)
    if chunks:
        vector_store.upsert_chunks(chunks)

    # Store vector_store ref in result for downstream nodes
    # (Pass via state using a workaround — store as serializable ref)
    update["agent_statuses"]["VOCTaxonomyAgent"] = "done"
    push_progress(agent_statuses=update["agent_statuses"], current_step="RAG index built", progress_pct=45)
    return {
        **update,
        "cleaned_reviews": classified,
        "reviews_by_id": {r.review_id: r for r in classified},
        "rag_built": True,
        "progress_pct": 45,
        "current_step": "RAG index built",
    }


def run_parallel_analysis(state: VOCWorkflowState) -> dict:
    """Run the 11 analysis agents in 3 dependency-respecting concurrent waves.

    BaseAgent.call() is a blocking HTTP call, so concurrency here comes from a
    thread pool (these calls are I/O-bound and release the GIL while waiting on
    the network), not asyncio. Each agent runs against its own result.model_copy()
    snapshot and returns the mutated copy; only the main thread ever writes back
    onto the shared `result`, by copying just the field(s) that agent owns — so
    no two threads ever touch the same VOCAnalysisResult instance concurrently.
    """
    console.rule("[bold cyan]Step 4: Parallel Analysis")

    reviews = state["cleaned_reviews"]
    reviews_by_id = state["reviews_by_id"]
    product_spec = state.get("product_spec")
    full_population = state.get("all_reviews") or reviews

    # Rebuild vector store connection (stateless between nodes)
    vector_store = VectorStore()
    retriever = ReviewRetriever(vector_store, reviews_by_id)

    usable = [r for r in reviews if not r.is_duplicate and not r.is_short]
    avg_rating = sum(r.rating for r in usable) / len(usable) if usable else 0.0

    result = VOCAnalysisResult(
        product_id=state["model_code"],
        model=state["model_code"],
        analysis_date=datetime.now().strftime("%Y-%m-%d %H:%M"),
        total_reviews=len(reviews),
        total_reviews_available=state.get("total_reviews_available", 0),
        avg_rating=round(avg_rating, 2),
    )

    agent_statuses = dict(state.get("agent_statuses", {}))
    TOTAL_AGENTS, PCT_START, PCT_END = 11, 48, 89
    completed = 0

    def _tick(agent: str, step: str) -> None:
        nonlocal completed
        completed += 1
        pct = PCT_START + round((PCT_END - PCT_START) * completed / TOTAL_AGENTS)
        agent_statuses[agent] = "done"
        push_progress(agent_statuses=dict(agent_statuses), current_step=step, progress_pct=pct)

    def _sentiment_task(snap: VOCAnalysisResult) -> VOCAnalysisResult:
        agent = SentimentAnalysisAgent()
        snap = agent.analyze_sentiment_distribution(reviews, snap)
        return agent.deep_analyze(reviews, retriever, snap)

    def _contradiction_task(snap: VOCAnalysisResult) -> VOCAnalysisResult:
        # Scans the FULL fetched population (not just the analyzed sample), since
        # genuine rating/text mismatches are rare and a stratified sample can miss
        # them entirely. The heuristic pre-filter is free; only flagged candidates
        # ever reach the LLM, so cost stays bounded regardless of population size.
        return ContradictionAnalysisAgent().analyze(full_population, retriever, snap)

    # (agent_status_name, step_label, result fields this agent owns, fn(snapshot) -> mutated snapshot)
    WAVE_1 = [
        ("SentimentAnalysisAgent", "Sentiment analysis",
         ["sentiment_distribution", "aspect_sentiment_summary"], _sentiment_task),
        ("ComplaintAnalysisAgent", "Complaint analysis", ["complaints"],
         lambda snap: ComplaintAnalysisAgent().analyze(reviews, retriever, snap, product_spec=product_spec)),
        ("SatisfactionAnalysisAgent", "Satisfaction analysis", ["satisfaction_drivers"],
         lambda snap: SatisfactionAnalysisAgent().analyze(reviews, retriever, snap, product_spec=product_spec)),
        ("ContradictionAgent", "Contradiction detection", ["contradictions"], _contradiction_task),
    ]
    # Each of these reads result.complaints / result.satisfaction_drivers, written by wave 1.
    WAVE_2 = [
        ("ImprovementAnalysisAgent", "Improvement analysis", ["improvement_points"],
         lambda snap: ImprovementAnalysisAgent().analyze(reviews, retriever, snap, product_spec=product_spec)),
        ("MarketingAnalysisAgent", "Marketing analysis", ["marketing_recommendations"],
         lambda snap: MarketingAnalysisAgent().analyze(reviews, retriever, snap, product_spec=product_spec)),
        ("CompetitivePositioningAgent", "Competitive positioning", ["positioning_analysis"],
         lambda snap: CompetitivePositioningAgent().analyze(reviews, retriever, snap, product_spec=product_spec)),
        ("ExpectationGapAgent", "Expectation gap analysis", ["expectation_gaps"],
         lambda snap: ExpectationGapAgent().analyze(reviews, retriever, snap, product_spec=product_spec)),
        ("CXActionAgent", "CX action generation", ["cx_actions"],
         lambda snap: CXActionAgent().analyze(reviews, retriever, snap)),
    ]
    # Both of these read result.expectation_gaps / result.cx_actions (to point to an existing
    # fix instead of restating it) and/or result.complaints, all written by wave 2 — so they
    # must run after wave 2, not alongside ExpectationGapAgent/CXActionAgent in it.
    WAVE_3 = [
        ("ImportanceAnalysisAgent", "Importance matrix", ["importance_matrix"],
         lambda snap: ImportanceAnalysisAgent().analyze(reviews, retriever, snap, product_spec=product_spec)),
        ("SegmentDivergenceAnalysisAgent", "Segment divergence analysis", ["segment_divergence_analysis"],
         lambda snap: SegmentDivergenceAnalysisAgent().analyze(reviews, retriever, snap, product_spec=product_spec)),
    ]

    def _run_wave(tasks: list[tuple[str, str, list[str], Any]]) -> None:
        for agent_name, _, _, _ in tasks:
            agent_statuses[agent_name] = "running"
        pct = PCT_START + round((PCT_END - PCT_START) * completed / TOTAL_AGENTS)
        push_progress(
            agent_statuses=dict(agent_statuses),
            current_step=f"Running {len(tasks)} analysis agent(s) in parallel",
            progress_pct=pct,
        )
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(tasks)) as pool:
            futures = {
                pool.submit(fn, result.model_copy()): (agent_name, step_label, field_names)
                for agent_name, step_label, field_names, fn in tasks
            }
            for future in concurrent.futures.as_completed(futures):
                agent_name, step_label, field_names = futures[future]
                mutated = future.result()
                for field in field_names:
                    setattr(result, field, getattr(mutated, field))
                _tick(agent_name, f"{step_label} complete")

    _run_wave(WAVE_1)
    _run_wave(WAVE_2)
    _run_wave(WAVE_3)

    return {
        "result": result,
        "agent_statuses": agent_statuses,
        "current_step": "Analysis complete",
        "progress_pct": PCT_END,
    }


def generate_report(state: VOCWorkflowState) -> dict:
    console.rule("[bold cyan]Step 5: Executive Report Generation")
    update = _set_status(state, "ReportGenerationAgent", "running", "Generating executive report", 90)
    push_progress(agent_statuses=update["agent_statuses"], current_step="Generating executive report", progress_pct=90)

    report_agent = ReportGenerationAgent()
    result = report_agent.generate_executive_summary(state["result"], product_spec=state.get("product_spec"))

    # Save result to disk
    import json
    out_path = settings.output_path / f"{state['model_code']}_voc_result.json"
    with open(out_path, "w") as f:
        json.dump(result.model_dump(), f, indent=2, default=str)
    console.print(f"[green]Results saved to {out_path}")
    save_manifest(state["model_code"], state["input_hash"])

    update["agent_statuses"]["ReportGenerationAgent"] = "done"
    push_progress(agent_statuses=update["agent_statuses"], current_step="Complete", progress_pct=100)
    return {
        **update,
        "result": result,
        "current_step": "Complete",
        "progress_pct": 100,
    }


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_voc_graph() -> StateGraph:
    graph = StateGraph(VOCWorkflowState)

    graph.add_node("collect_data", collect_data)
    graph.add_node("load_cached_result", load_cached_result)
    graph.add_node("clean_reviews", clean_reviews)
    graph.add_node("build_taxonomy", build_taxonomy)
    graph.add_node("run_analysis", run_parallel_analysis)
    graph.add_node("generate_report", generate_report)

    graph.set_entry_point("collect_data")
    graph.add_conditional_edges(
        "collect_data",
        _route_after_collect,
        {"clean_reviews": "clean_reviews", "load_cached_result": "load_cached_result"},
    )
    graph.add_edge("clean_reviews", "build_taxonomy")
    graph.add_edge("build_taxonomy", "run_analysis")
    graph.add_edge("run_analysis", "generate_report")
    graph.add_edge("generate_report", END)
    graph.add_edge("load_cached_result", END)

    return graph.compile()


def run_voc_pipeline(
    model_code: str,
    max_reviews: int = 200,
    skip_if_cached: bool = False,
    url: Optional[str] = None,
) -> VOCWorkflowState:
    """Run the full VOC pipeline and return final state.

    `url` is the product page to scrape; omit it for the original U7900F TV
    (falls back to settings.samsung_product_url) or pass it for any other model.
    """
    graph = build_voc_graph()
    initial_state: VOCWorkflowState = {
        "model_code": model_code,
        "max_reviews": max_reviews,
        "skip_if_cached": skip_if_cached,
        "url": url,
        "reviews": [],
        "all_reviews": [],
        "total_reviews_available": 0,
        "product_spec": None,
        "competitor_specs": {},
        "input_hash": "",
        "cleaned_reviews": [],
        "reviews_by_id": {},
        "rag_built": False,
        "result": None,
        "current_step": "Starting",
        "agent_statuses": {
            "DataCollectionAgent": "pending",
            "ReviewCleaningAgent": "pending",
            "VOCTaxonomyAgent": "pending",
            "SentimentAnalysisAgent": "pending",
            "ComplaintAnalysisAgent": "pending",
            "SatisfactionAnalysisAgent": "pending",
            "ImprovementAnalysisAgent": "pending",
            "MarketingAnalysisAgent": "pending",
            "CompetitivePositioningAgent": "pending",
            "ContradictionAgent": "pending",
            "ExpectationGapAgent": "pending",
            "SegmentDivergenceAnalysisAgent": "pending",
            "CXActionAgent": "pending",
            "ImportanceAnalysisAgent": "pending",
            "ReportGenerationAgent": "pending",
        },
        "errors": [],
        "progress_pct": 0,
    }
    return graph.invoke(initial_state)
