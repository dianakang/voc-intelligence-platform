# Samsung TV VOC Intelligence Platform

AI-powered Voice of Customer (VOC) analysis for Samsung TVs. The pipeline scrapes customer reviews, cleans and classifies them, runs a battery of LLM-driven analysis agents (sentiment, complaints, satisfaction, competitive positioning, expectation gaps, etc.), and produces an executive-ready Markdown/JSON report — accessible via CLI, REST API, or a Next.js dashboard.

## Architecture

```
Reviews (scraper) → Cleaning → Taxonomy + RAG indexing → Parallel analysis agents → Executive report
```

- **`src/data/`** — review scraping (`scraper.py`) and product spec extraction (`spec_extractor.py`)
- **`src/rag/`** — chunking, embedding, and retrieval (Qdrant preferred, Pinecone fallback)
- **`src/agents/`** — one agent per analysis task (review cleaning, taxonomy, sentiment, complaints, satisfaction/improvement, marketing, contradictions, importance, competitive positioning, expectation gap, segment divergence, report generation)
- **`src/workflow/graph.py`** — LangGraph state machine that orchestrates the agents end to end
- **`src/reports/generator.py`** — renders the final `VOCAnalysisResult` into Markdown/JSON
- **`src/api/`** — FastAPI app exposing the pipeline as an async job (`main.py` is the entrypoint)
- **`src/cli.py`** — Typer CLI for running the pipeline from the terminal
- **`frontend/`** — Next.js dashboard that triggers a run and visualizes progress/results

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
