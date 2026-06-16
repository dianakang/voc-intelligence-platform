"""OpenAI text-embedding-3-large embeddings."""
from __future__ import annotations

import time
from typing import Optional

from openai import OpenAI
from rich.console import Console
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings
from src.rag.chunker import ReviewChunk

console = Console()

EMBEDDING_DIM = 3072  # text-embedding-3-large dimension


class Embedder:
    def __init__(self):
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.embedding_model

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(
            model=self.model,
            input=texts,
        )
        return [item.embedding for item in response.data]

    def embed_chunks(
        self,
        chunks: list[ReviewChunk],
        batch_size: int = 100,
    ) -> list[tuple[ReviewChunk, list[float]]]:
        results: list[tuple[ReviewChunk, list[float]]] = []
        total = len(chunks)

        for i in range(0, total, batch_size):
            batch = chunks[i : i + batch_size]
            texts = [c.text for c in batch]

            try:
                embeddings = self.embed_texts(texts)
                for chunk, emb in zip(batch, embeddings):
                    results.append((chunk, emb))
                console.print(f"[cyan]Embedded {min(i + batch_size, total)}/{total} chunks")
            except Exception as e:
                console.print(f"[red]Embedding failed for batch {i}: {e}")
                # Use zero vectors as fallback
                for chunk in batch:
                    results.append((chunk, [0.0] * EMBEDDING_DIM))

            time.sleep(0.1)

        return results

    def embed_query(self, query: str) -> list[float]:
        return self.embed_texts([query])[0]
