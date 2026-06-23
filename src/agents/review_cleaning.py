"""Review Cleaning Agent: deduplication, normalization, quality filtering."""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict

from src.agents.base import BaseAgent
from src.config import settings
from src.data.models import Review

SYSTEM_PROMPT = """You are a data quality expert specializing in e-commerce review normalization.
Your job is to clean and normalize review text while preserving the original meaning.

For each review, you will:
1. Fix obvious typos and grammar issues
2. Expand common abbreviations (e.g., "pic quality" -> "picture quality")
3. Remove excessive punctuation (e.g., "!!!!" -> "!")
4. Normalize whitespace
5. Preserve all substantive content - do not remove complaints or praise
6. Return the cleaned text only, no explanations."""


class ReviewCleaningAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="ReviewCleaningAgent",
            model=settings.model_haiku,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.1,
        )

    def clean_reviews(self, reviews: list[Review]) -> list[Review]:
        self.log(f"Cleaning {len(reviews)} reviews...")

        # Step 1: Rule-based pre-cleaning
        for review in reviews:
            review.cleaned_text = self._rule_based_clean(review.text)
            review.is_short = len(review.cleaned_text.split()) < 5

        # Step 2: Deduplication
        reviews = self._deduplicate(reviews)

        # Step 3: LLM-based cleaning for substantive reviews
        substantive = [r for r in reviews if not r.is_duplicate and not r.is_short]
        self.log(f"LLM cleaning {len(substantive)} substantive reviews in batches...")

        batch_size = settings.batch_size
        for i in range(0, len(substantive), batch_size):
            batch = substantive[i : i + batch_size]
            cleaned = self._llm_clean_batch(batch)
            for review, clean_text in zip(batch, cleaned):
                review.cleaned_text = clean_text

        total_kept = sum(1 for r in reviews if not r.is_duplicate and not r.is_short)
        self.log(
            f"Cleaning complete: {total_kept} usable reviews "
            f"({sum(1 for r in reviews if r.is_duplicate)} duplicates, "
            f"{sum(1 for r in reviews if r.is_short)} too-short reviews tagged)"
        )
        return reviews

    def _rule_based_clean(self, text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"[!]{3,}", "!", text)
        text = re.sub(r"[.]{4,}", "...", text)
        text = re.sub(r"\b(tv|TV|Tv)\b", "TV", text)
        text = re.sub(r"\bpic\b", "picture", text, flags=re.IGNORECASE)
        text = re.sub(r"\bpics\b", "pictures", text, flags=re.IGNORECASE)
        text = re.sub(r"\bquality(?=\s)", "quality", text)
        return text

    def _deduplicate(self, reviews: list[Review]) -> list[Review]:
        seen_hashes: set[str] = set()
        seen_texts: dict[str, str] = {}

        for review in reviews:
            text_normalized = re.sub(r"\s+", "", review.cleaned_text or review.text).lower()
            text_hash = hashlib.md5(text_normalized.encode()).hexdigest()

            if text_hash in seen_hashes:
                review.is_duplicate = True
            elif len(text_normalized) > 20:
                # Fuzzy: check if 90%+ overlap with existing review
                for existing_hash, existing_text in seen_texts.items():
                    if self._similarity(text_normalized, existing_text) > 0.92:
                        review.is_duplicate = True
                        break

            if not review.is_duplicate:
                seen_hashes.add(text_hash)
                seen_texts[text_hash] = text_normalized

        return reviews

    def _similarity(self, a: str, b: str) -> float:
        """Simple character n-gram similarity."""
        if not a or not b:
            return 0.0
        n = 3
        a_grams = set(a[i : i + n] for i in range(len(a) - n + 1))
        b_grams = set(b[i : i + n] for i in range(len(b) - n + 1))
        if not a_grams or not b_grams:
            return 0.0
        intersection = a_grams & b_grams
        return len(intersection) / max(len(a_grams), len(b_grams))

    def _llm_clean_batch(self, reviews: list[Review]) -> list[str]:
        numbered = "\n\n".join(
            f"[{i+1}] {r.cleaned_text or r.text}" for i, r in enumerate(reviews)
        )
        prompt = f"""Clean and normalize each of the following {len(reviews)} TV reviews.
Return a JSON array with {len(reviews)} strings, one cleaned version per review.
Preserve all substantive content. Fix typos and normalize abbreviations.

Reviews:
{numbered}"""
        try:
            result = self.call_json(prompt, max_tokens=4096)
            if isinstance(result, list) and len(result) == len(reviews):
                return [str(r) for r in result]
        except Exception as e:
            self.log(f"[yellow]LLM batch cleaning failed: {e}, using rule-based results")
        return [r.cleaned_text or r.text for r in reviews]
