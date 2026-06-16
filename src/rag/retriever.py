"""RAG Retriever: fetch relevant reviews for a given analysis query."""
from __future__ import annotations

from src.data.models import Review
from src.rag.vector_store import VectorStore


class ReviewRetriever:
    def __init__(self, vector_store: VectorStore, reviews_by_id: dict[str, Review]):
        self.store = vector_store
        self.reviews_by_id = reviews_by_id

    def retrieve(self, query: str, top_k: int = 10, filter: dict | None = None) -> list[Review]:
        matches = self.store.query(query=query, top_k=top_k, filter=filter)
        reviews = []
        for m in matches:
            chunk_id = m["id"]
            rid = chunk_id.replace("review_", "")
            if rid in self.reviews_by_id:
                reviews.append(self.reviews_by_id[rid])
        return reviews

    def retrieve_by_rating(self, query: str, min_rating: float, max_rating: float, top_k: int = 10) -> list[Review]:
        all_reviews = self.retrieve(query, top_k=top_k * 2)
        return [r for r in all_reviews if min_rating <= r.rating <= max_rating][:top_k]

    def retrieve_negative(self, query: str, top_k: int = 10) -> list[Review]:
        return self.retrieve_by_rating(query, 1, 2, top_k)

    def retrieve_positive(self, query: str, top_k: int = 10) -> list[Review]:
        return self.retrieve_by_rating(query, 4, 5, top_k)

    def format_for_context(self, reviews: list[Review], max_chars: int = 6000) -> str:
        lines = []
        total = 0
        for r in reviews:
            text = r.cleaned_text or r.text
            entry = f"[Rating: {r.rating}/5, Date: {r.date or 'N/A'}]\n{text}"
            if total + len(entry) > max_chars:
                break
            lines.append(entry)
            total += len(entry)
        return "\n\n---\n\n".join(lines)
