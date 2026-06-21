# Samsung TV VOC Intelligence Platform

AI-powered Voice of Customer (VOC) analysis for Samsung TVs. The pipeline scrapes customer reviews, cleans and classifies them, runs a battery of LLM-driven analysis agents (sentiment, complaints, satisfaction, competitive positioning, expectation gaps, CX actions, etc.), and produces an executive-ready Markdown/JSON report — accessible via CLI, REST API, or a Next.js dashboard.

Primary users are **in-house marketers** (PDP copy, ad messaging, promotions) and the **CX/customer support team** (FAQ updates, response scripts), with outputs designed to extend to product/PM, e-commerce ops, and sales enablement. Every analysis is grounded jointly in the review text **and** the product spec/PDP (price, account requirements, delivery/pickup status) so the platform can separate a genuine **product issue** from a **purchase-experience issue** (delivery, account setup, installation) instead of treating all complaints as defects.

## Architecture

```
Reviews (scraper) → Cleaning → Taxonomy + RAG indexing (grounded in PDP/spec) → Parallel analysis agents → Executive report
```

- **`src/data/`** — review scraping (`scraper.py`) and live product-page scraping (`spec_extractor.py`): every run fetches the current Samsung product page, saves a raw snapshot under `data/raw/{model_code}/` (`page.html`, `page_meta.json`, `spec.json`, `reviews.json`), and parses price, the full spec table, account requirements, and delivery/pickup availability from that same page — so spec and reviews are always compared against one source of truth. Falls back to a cached snapshot, then a hardcoded dict, only if the live scrape fails. Real reviews are fetched from BazaarVoice's current gateway via a Playwright-driven browser context (the classic passkey-based API is dead, and the newer gateway blocks plain HTTP requests) — falls back to a legacy API attempt, then cached/sample data, only if that fails. Every run fetches and caches the *entire* real review population (e.g. all ~2,700 reviews), then draws an analysis sample (`--max-reviews`, default 200) stratified by rating so the analyzed subset's sentiment mix matches the true population — the report shows both the analyzed count and the real total (e.g. "200 (sampled from 2,720 available)").
- **`src/rag/`** — chunking, embedding, and retrieval (Qdrant preferred, Pinecone fallback)
- **`src/agents/`** — one agent per analysis task: review cleaning, taxonomy, sentiment, complaints (tagged `product_defect` vs `purchase_experience`), satisfaction/improvement, marketing, paradox/contradiction detection (rating vs. review-text mismatches — separates emotional rating from actual product experience), importance, competitive positioning, expectation gap, segment divergence, **CX action generation** (turns complaint clusters into FAQ entries, support scripts, and proactive notices), report generation
- **`src/workflow/graph.py`** — LangGraph state machine that orchestrates the agents end to end
- **`src/reports/generator.py`** — renders the final `VOCAnalysisResult` into Markdown/JSON
- **`src/api/`** — FastAPI app exposing the pipeline as an async job (`main.py` is the entrypoint)
- **`src/cli.py`** — Typer CLI for running the pipeline from the terminal
- **`frontend/`** — Next.js dashboard that triggers a run and visualizes progress/results, including a Paradox Reviews section and a CX Action Toolkit for support teams

## Prerequisites

- Python ≥ 3.11
- Node.js (for the frontend)
- An Anthropic API key (or OpenRouter key) and an OpenAI API key (for embeddings)
- Optional: a running Qdrant instance (falls back to Pinecone if configured)

## Setup

```bash
# Install Python dependencies
pip install -e .

# Copy and fill in environment variables
cp .env.example .env
```

Edit `.env` with at minimum:

```
ANTHROPIC_API_KEY=...      # or OPENROUTER_API_KEY
OPENAI_API_KEY=...         # required for embeddings
```

## Running the pipeline

### CLI

```bash
voc run UN50U7900FFXZA --max-reviews 200 --json
voc spec UN50U7900FFXZA      # show product spec
voc sample UN50U7900FFXZA -n 5  # preview sample reviews
```

Reports are written to `data/reports/`.

### API server

```bash
python main.py
# or: uvicorn main:app --reload
```

- `POST /api/v1/analysis/run` — start a pipeline job
- `GET /api/v1/analysis/status/{job_id}` — poll progress
- `GET /api/v1/analysis/result/{job_id}` — fetch the final result
- `GET /api/v1/analysis/result/{job_id}/report` — download the Markdown report
- Full docs at `http://localhost:8000/docs`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The dashboard expects the API server running on `http://localhost:8000` (CORS is pre-configured for `localhost:3000`).

## Configuration

See `.env.example` for all available settings, including model selection (`MODEL_HAIKU` / `MODEL_SONNET` / `MODEL_OPUS`), vector DB choice (Qdrant/Pinecone), and pipeline tuning (`MAX_REVIEWS`, `BATCH_SIZE`, `ENABLE_RAG`).
