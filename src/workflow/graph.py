"""LangGraph orchestration graph for the VOC Intelligence Platform."""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

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

    # Fetch reviews synchronously (run async in sync context)
    async def _fetch():
        async with SamsungReviewScraper() as scraper:
            reviews = await scraper.collect_all_reviews(model_code, max_reviews)
            scraper.save_raw(reviews, model_code)
            return reviews

    reviews = asyncio.run(_fetch())
    spec = get_samsung_spec(model_code)
    competitor_specs = get_competitor_specs()

    console.print(f"[green]Collected {len(reviews)} reviews, spec loaded")
    update["agent_statuses"]["DataCollectionAgent"] = "done"
    push_progress(agent_statuses=update["agent_statuses"], current_step="Reviews collected", progress_pct=15)
    return {
        **update,
        "reviews": reviews,
        "product_spec": spec,
        "competitor_specs": competitor_specs,
        "progress_pct": 15,
    }


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
    taxonomy_agent = VOCTaxonomyAgent()
    classified = taxonomy_agent.classify_reviews(state["cleaned_reviews"])

    # Build RAG index
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
    """Run all 8 analysis tasks sequentially (LangGraph handles parallelism via fan-out)."""
    console.rule("[bold cyan]Step 4: Parallel Analysis")

    reviews = state["cleaned_reviews"]
    reviews_by_id = state["reviews_by_id"]

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
        avg_rating=round(avg_rating, 2),
    )

    agent_statuses = dict(state.get("agent_statuses", {}))

    def _tick(agent: str, step: str, pct: int) -> None:
        agent_statuses[agent] = "done"
        push_progress(agent_statuses=dict(agent_statuses), current_step=step, progress_pct=pct)

    # Task 1: Sentiment
    agent_statuses["SentimentAnalysisAgent"] = "running"
    push_progress(agent_statuses=dict(agent_statuses), current_step="Sentiment analysis", progress_pct=48)
    sentiment_agent = SentimentAnalysisAgent()
    result = sentiment_agent.analyze_sentiment_distribution(reviews, result)
    result = sentiment_agent.deep_analyze(reviews, retriever, result)
    _tick("SentimentAnalysisAgent", "Sentiment analysis complete", 52)

    # Task 2: Complaints
    agent_statuses["ComplaintAnalysisAgent"] = "running"
    push_progress(agent_statuses=dict(agent_statuses), current_step="Complaint analysis", progress_pct=53)
    complaint_agent = ComplaintAnalysisAgent()
    result = complaint_agent.analyze(reviews, retriever, result)
    _tick("ComplaintAnalysisAgent", "Complaint analysis complete", 57)

    # Task 3: Satisfaction
    agent_statuses["SatisfactionAnalysisAgent"] = "running"
    push_progress(agent_statuses=dict(agent_statuses), current_step="Satisfaction analysis", progress_pct=58)
    satisfaction_agent = SatisfactionAnalysisAgent()
    result = satisfaction_agent.analyze(reviews, retriever, result)
    _tick("SatisfactionAnalysisAgent", "Satisfaction analysis complete", 62)

    # Task 4: Improvements
    agent_statuses["ImprovementAnalysisAgent"] = "running"
    push_progress(agent_statuses=dict(agent_statuses), current_step="Improvement analysis", progress_pct=63)
    improvement_agent = ImprovementAnalysisAgent()
    result = improvement_agent.analyze(reviews, retriever, result)
    _tick("ImprovementAnalysisAgent", "Improvement analysis complete", 67)

    # Task 5: Marketing
    agent_statuses["MarketingAnalysisAgent"] = "running"
    push_progress(agent_statuses=dict(agent_statuses), current_step="Marketing analysis", progress_pct=68)
    marketing_agent = MarketingAnalysisAgent()
    result = marketing_agent.analyze(reviews, retriever, result)
    _tick("MarketingAnalysisAgent", "Marketing analysis complete", 72)

    # Task 6: Competitive
    agent_statuses["CompetitivePositioningAgent"] = "running"
    push_progress(agent_statuses=dict(agent_statuses), current_step="Competitive positioning", progress_pct=73)
    comp_agent = CompetitivePositioningAgent()
    result = comp_agent.analyze(reviews, retriever, result)
    _tick("CompetitivePositioningAgent", "Competitive positioning complete", 76)

    # Task 7: Contradictions
    agent_statuses["ContradictionAgent"] = "running"
    push_progress(agent_statuses=dict(agent_statuses), current_step="Contradiction detection", progress_pct=77)
    contra_agent = ContradictionAnalysisAgent()
    result = contra_agent.analyze(reviews, retriever, result)
    _tick("ContradictionAgent", "Contradiction detection complete", 80)

    # Task 8: Importance
    agent_statuses["ImportanceAnalysisAgent"] = "running"
    push_progress(agent_statuses=dict(agent_statuses), current_step="Importance matrix", progress_pct=81)
    importance_agent = ImportanceAnalysisAgent()
    result = importance_agent.analyze(reviews, retriever, result)
    _tick("ImportanceAnalysisAgent", "Importance matrix complete", 83)

    # Task 9 (핵심): Expectation Gap
    agent_statuses["ExpectationGapAgent"] = "running"
    push_progress(agent_statuses=dict(agent_statuses), current_step="Expectation gap analysis", progress_pct=84)
    gap_agent = ExpectationGapAgent()
    result = gap_agent.analyze(reviews, retriever, result)
    _tick("ExpectationGapAgent", "Expectation gap analysis complete", 85)

    return {
        "result": result,
        "agent_statuses": agent_statuses,
        "current_step": "Analysis complete",
        "progress_pct": 85,
    }


def generate_report(state: VOCWorkflowState) -> dict:
    console.rule("[bold cyan]Step 5: Executive Report Generation")
    update = _set_status(state, "ReportGenerationAgent", "running", "Generating executive report", 90)
    push_progress(agent_statuses=update["agent_statuses"], current_step="Generating executive report", progress_pct=90)

    report_agent = ReportGenerationAgent()
    result = report_agent.generate_executive_summary(state["result"])

    # Save result to disk
    import json
    out_path = settings.output_path / f"{state['model_code']}_voc_result.json"
    with open(out_path, "w") as f:
        json.dump(result.model_dump(), f, indent=2, default=str)
    console.print(f"[green]Results saved to {out_path}")

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
    graph.add_node("clean_reviews", clean_reviews)
    graph.add_node("build_taxonomy", build_taxonomy)
    graph.add_node("run_analysis", run_parallel_analysis)
    graph.add_node("generate_report", generate_report)

    graph.set_entry_point("collect_data")
    graph.add_edge("collect_data", "clean_reviews")
    graph.add_edge("clean_reviews", "build_taxonomy")
    graph.add_edge("build_taxonomy", "run_analysis")
    graph.add_edge("run_analysis", "generate_report")
    graph.add_edge("generate_report", END)

    return graph.compile()


def run_voc_pipeline(model_code: str, max_reviews: int = 200) -> VOCWorkflowState:
    """Run the full VOC pipeline and return final state."""
    graph = build_voc_graph()
    initial_state: VOCWorkflowState = {
        "model_code": model_code,
        "max_reviews": max_reviews,
        "reviews": [],
        "product_spec": None,
        "competitor_specs": {},
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
            "ImportanceAnalysisAgent": "pending",
            "ExpectationGapAgent": "pending",
            "ReportGenerationAgent": "pending",
        },
        "errors": [],
        "progress_pct": 0,
    }
    return graph.invoke(initial_state)
