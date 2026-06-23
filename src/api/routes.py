"""FastAPI routes for VOC Intelligence Platform."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from src.config import settings
from src.api.state import _jobs, set_current_job_id
from src.data.models import VOCAnalysisResult
from src.reports.generator import generate_markdown_report, generate_json_report

router = APIRouter()


class RunAnalysisRequest(BaseModel):
    model_code: str = "UN50U7900FFXZA"
    max_reviews: int = 200
    skip_if_cached: bool = False
    url: Optional[str] = None  # if set, overrides model_code (derived from the URL's slug) and the page scraped


class JobStatus(BaseModel):
    job_id: str
    status: str  # pending | running | done | error
    progress_pct: int
    current_step: str
    agent_statuses: dict[str, str]
    error: Optional[str] = None


def _run_pipeline(
    job_id: str, model_code: str, max_reviews: int, skip_if_cached: bool = False, url: Optional[str] = None
):
    """Background task: run the full pipeline and store result."""
    try:
        from src.workflow.graph import run_voc_pipeline

        _jobs[job_id]["status"] = "running"
        set_current_job_id(job_id)

        final_state = run_voc_pipeline(
            model_code=model_code, max_reviews=max_reviews, skip_if_cached=skip_if_cached, url=url
        )

        _jobs[job_id]["status"] = "done"
        _jobs[job_id]["progress_pct"] = 100
        _jobs[job_id]["current_step"] = "Complete"
        _jobs[job_id]["agent_statuses"] = final_state.get("agent_statuses", {})
        _jobs[job_id]["result"] = final_state.get("result")

        # Generate reports
        if final_state.get("result"):
            generate_markdown_report(final_state["result"])
            generate_json_report(final_state["result"])

    except Exception as e:
        _jobs[job_id]["status"] = "error"
        # Unwrap tenacity RetryError to get the root cause
        cause = getattr(e, "last_attempt", None)
        if cause is not None:
            try:
                inner = cause.result()
            except Exception as inner_exc:
                e = inner_exc
        msg = str(e)
        if "AuthenticationError" in type(e).__name__ or "AuthenticationError" in msg:
            msg = "Anthropic API key is invalid or missing. Check ANTHROPIC_API_KEY in your .env file."
        elif "RateLimitError" in type(e).__name__:
            msg = "Anthropic rate limit hit. Wait a moment and try again."
        _jobs[job_id]["error"] = msg


@router.post("/analysis/run", response_model=dict)
async def start_analysis(req: RunAnalysisRequest, background_tasks: BackgroundTasks):
    import uuid

    model_code = req.model_code
    if req.url:
        from src.data.product_discovery import extract_model_code

        derived = extract_model_code(req.url)
        if not derived:
            raise HTTPException(
                status_code=400,
                detail="Could not find a '-sku-{model}/' segment in that URL — paste a samsung.com product page URL.",
            )
        model_code = derived

    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "progress_pct": 0,
        "current_step": "Initializing",
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
            "SegmentDivergenceAnalysisAgent": "pending",
            "CXActionAgent": "pending",
            "ReportGenerationAgent": "pending",
        },
        "error": None,
        "result": None,
        "model_code": model_code,
    }

    background_tasks.add_task(
        _run_pipeline, job_id, model_code, req.max_reviews, req.skip_if_cached, req.url
    )
    return {"job_id": job_id, "status": "pending"}


@router.get("/analysis/status/{job_id}", response_model=JobStatus)
async def get_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return JobStatus(
        job_id=job_id,
        status=job["status"],
        progress_pct=job.get("progress_pct", 0),
        current_step=job.get("current_step", ""),
        agent_statuses=job.get("agent_statuses", {}),
        error=job.get("error"),
    )


@router.get("/analysis/result/{job_id}")
async def get_result(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    if job["status"] != "done":
        raise HTTPException(status_code=400, detail=f"Job not complete (status: {job['status']})")

    result: VOCAnalysisResult = job.get("result")
    if not result:
        raise HTTPException(status_code=500, detail="No result available")
    return result.model_dump()


@router.get("/analysis/result/{job_id}/report")
async def download_report(job_id: str):
    job = _jobs.get(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(status_code=400, detail="Job not complete")

    model_code = job.get("model_code", "UN50U7900FFXZA")
    reports = list(settings.output_path.glob(f"{model_code}_voc_report_*.md"))
    if not reports:
        raise HTTPException(status_code=404, detail="Report not found")

    latest = sorted(reports)[-1]
    return FileResponse(latest, media_type="text/markdown", filename=latest.name)


@router.get("/product/spec/{model_code}")
async def get_product_spec(model_code: str):
    from src.data.spec_extractor import get_samsung_spec
    spec = get_samsung_spec(model_code)
    return spec.model_dump()


@router.get("/product/competitors/{model_code}")
async def get_competitors(model_code: str):
    from src.data.spec_extractor import get_competitor_specs
    return get_competitor_specs(model_code)


@router.get("/reviews/sample/{model_code}")
async def get_sample_reviews(model_code: str, limit: int = 20):
    from src.data.scraper import _generate_sample_reviews
    reviews = _generate_sample_reviews(model_code, count=limit)
    return [r.model_dump() for r in reviews]


def _cached_product_meta(model_code: str) -> dict:
    """Reads category/product_name from the spec cache written during analysis,
    without triggering get_samsung_spec()'s live-scrape fallback on a cache miss."""
    spec_path = settings.raw_product_dir(model_code) / "spec.json"
    try:
        with open(spec_path) as fp:
            spec = json.load(fp)
        return {"category": spec.get("category", ""), "product_name": spec.get("product_name", "")}
    except Exception:
        return {"category": "", "product_name": ""}


@router.get("/reports/list")
async def list_reports():
    reports = []
    for f in settings.output_path.glob("*.json"):
        if f.name.endswith(".manifest.json"):
            continue
        try:
            with open(f) as fp:
                data = json.load(fp)
            model = data.get("model", "")
            reports.append({
                "filename": f.name,
                "model": model,
                "analysis_date": data.get("analysis_date", ""),
                "total_reviews": data.get("total_reviews", 0),
                "avg_rating": data.get("avg_rating", 0),
                **_cached_product_meta(model),
            })
        except Exception:
            pass
    return sorted(reports, key=lambda x: x.get("analysis_date", ""), reverse=True)


@router.get("/reports/{filename}")
async def get_report(filename: str):
    path = settings.output_path / filename
    if not path.exists() or path.suffix != ".json":
        raise HTTPException(status_code=404, detail="Report not found")
    with open(path) as f:
        return json.load(f)


@router.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
