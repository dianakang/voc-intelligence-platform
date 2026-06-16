"""Review chunking strategy: 1 review = 1 chunk with rich metadata."""
from __future__ import annotations

from src.data.models import Review


class ReviewChunk:
    def __init__(self, review: Review):
        self.review = review
        self.chunk_id = f"review_{review.review_id}"
        self.text = self._build_text()
        self.metadata = self._build_metadata()

    def _build_text(self) -> str:
        parts = []
        if self.review.title:
            parts.append(f"Title: {self.review.title}")
        parts.append(f"Rating: {self.review.rating}/5")
        parts.append(f"Review: {self.review.cleaned_text or self.review.text}")
        return "\n".join(parts)

    def _build_metadata(self) -> dict:
        return {
            "review_id": self.review.review_id,
            "product_id": self.review.product_id,
            "model": self.review.model,
            "rating": float(self.review.rating),
            "date": self.review.date or "",
            "helpful_votes": self.review.helpful_votes,
            "verified_purchase": self.review.verified_purchase,
            "aspects": ",".join(self.review.aspects) if self.review.aspects else "",
            "sentiment": self.review.overall_sentiment or "",
            "has_contradiction": self.review.has_contradiction,
        }


def chunk_reviews(reviews: list[Review]) -> list[ReviewChunk]:
    """Convert reviews to chunks. Exclude duplicates and too-short reviews."""
    return [
        ReviewChunk(r)
        for r in reviews
        if not r.is_duplicate and not r.is_short and (r.cleaned_text or r.text).strip()
    ]
