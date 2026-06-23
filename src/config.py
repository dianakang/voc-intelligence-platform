from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API Keys
    anthropic_api_key: str = Field(default="")
    openai_api_key: str = Field(default="")
    openrouter_api_key: str = Field(default="")  # OpenRouter alternative

    # Vector DB — Qdrant (preferred) or Pinecone
    qdrant_url: str = Field(default="http://localhost:6333")
    qdrant_api_key: str = Field(default="")
    qdrant_collection: str = Field(default="samsung_reviews")
    pinecone_api_key: str = Field(default="")
    pinecone_index_name: str = Field(default="voc-samsung-tv")
    pinecone_environment: str = Field(default="us-east-1")

    # Samsung product
    samsung_product_url: str = Field(
        default="https://www.samsung.com/us/tvs/uhd-4k-tv/50-inch-class-crystal-uhd-u7900f-4k-smart-tv-sku-un50u7900ffxza/"
    )
    samsung_model_code: str = Field(default="UN50U7900FFXZA")
    samsung_product_id: str = Field(default="UN50U7900FFXZA")

    # Models (support both direct Anthropic and OpenRouter)
    model_haiku: str = Field(default="claude-haiku-4-5-20251001")
    model_sonnet: str = Field(default="claude-sonnet-4-6")
    model_opus: str = Field(default="claude-opus-4-8")
    embedding_model: str = Field(default="text-embedding-3-large")

    # OpenAI equivalents, used as an automatic cross-provider fallback when the
    # primary provider's call fails (credit exhaustion, outage, rate limit) —
    # and vice versa, for any agent configured with provider="openai" as primary.
    openai_model_haiku: str = Field(default="gpt-4o-mini")
    openai_model_sonnet: str = Field(default="gpt-4o")
    openai_model_opus: str = Field(default="gpt-4.1")

    # Pipeline
    max_reviews: int = Field(default=500)
    # Reviews per LLM call in ReviewCleaningAgent/VOCTaxonomyAgent batching. 25 is sized
    # against taxonomy's heavier output payload (~150 tokens/item) within max_tokens=4096 —
    # re-check that budget before raising this further.
    batch_size: int = Field(default=25)
    enable_rag: bool = Field(default=True)
    output_dir: str = Field(default="data/reports")

    @property
    def output_path(self) -> Path:
        p = ROOT_DIR / self.output_dir
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def raw_data_path(self) -> Path:
        p = ROOT_DIR / "data" / "raw"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def raw_product_dir(self, model_code: str) -> Path:
        """Per-product raw-asset directory: page.html, page_meta.json, spec.json, reviews.json."""
        p = self.raw_data_path / model_code
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def samsung_spec_pdf_path(self) -> Path:
        """Assignment-provided spec PDF, authoritative for static spec fields (see get_samsung_spec)."""
        return self.raw_product_dir(self.samsung_model_code) / "spec.pdf"

    @property
    def processed_data_path(self) -> Path:
        p = ROOT_DIR / "data" / "processed"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def use_openrouter(self) -> bool:
        return bool(self.openrouter_api_key) and not self.anthropic_api_key

    @property
    def effective_anthropic_key(self) -> str:
        return self.anthropic_api_key or self.openrouter_api_key

    @property
    def anthropic_base_url(self) -> str | None:
        if self.use_openrouter:
            return "https://openrouter.ai/api/v1"
        return None


settings = Settings()
