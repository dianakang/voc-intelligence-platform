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
    bv_passkey: str = Field(default="")

    # Models (support both direct Anthropic and OpenRouter)
    model_haiku: str = Field(default="claude-haiku-4-5-20251001")
    model_sonnet: str = Field(default="claude-sonnet-4-6")
    model_opus: str = Field(default="claude-opus-4-8")
    embedding_model: str = Field(default="text-embedding-3-large")

    # Pipeline
    max_reviews: int = Field(default=500)
    batch_size: int = Field(default=20)
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
