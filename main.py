"""FastAPI application entrypoint."""
import warnings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router
from src.config import settings

# Warn loudly if keys are still placeholders
_placeholder = "your_"
if _placeholder in settings.anthropic_api_key or not settings.anthropic_api_key:
    warnings.warn("⚠️  ANTHROPIC_API_KEY is not set in .env — analysis will fail with AuthenticationError", stacklevel=1)
if _placeholder in settings.openai_api_key or not settings.openai_api_key:
    warnings.warn("⚠️  OPENAI_API_KEY is not set in .env — embeddings will fail", stacklevel=1)

app = FastAPI(
    title="Samsung TV VOC Intelligence Platform",
    description="AI-powered customer review analysis system",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "name": "Samsung TV VOC Intelligence Platform",
        "version": "1.0.0",
        "docs": "/docs",
        "api": "/api/v1",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
