"""Sentiment Analysis Agent: aspect-level sentiment with RAG evidence."""
from __future__ import annotations

from collections import defaultdict

from src.agents.base import BaseAgent
from src.config import settings
from src.data.models import Review, Sentiment, VOCAnalysisResult
from src.rag.retriever import ReviewRetriever

SYSTEM_PROMPT = """You are a sentiment analysis expert specializing in consumer product reviews.
Analyze the sentiment of product reviews at both the overall and aspect level.
Be precise: distinguish between genuine satisfaction and resigned acceptance.
Return structured JSON only."""


class SentimentAnalysisAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="SentimentAnalysisAgent",
            model=settings.model_sonnet,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.2,
        )

    def analyze_sentiment_distribution(
        self,
        reviews: list[Review],
        result: VOCAnalysisResult,
    ) -> VOCAnalysisResult:
        self.log("Computing sentiment distribution...")

        usable = [r for r in reviews if not r.is_duplicate and not r.is_short]

        # Overall sentiment distribution
        sentiment_counts: dict[str, int] = defaultdict(int)
        for r in usable:
            s = r.overall_sentiment or (
                "positive" if r.rating >= 4
                else "negative" if r.rating <= 2
                else "neutral"
            )
            sentiment_counts[s] += 1
        result.sentiment_distribution = dict(sentiment_counts)

        # Aspect-level sentiment summary
        aspect_data: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for r in usable:
            for aspect, sentiment in r.aspect_sentiments.items():
                aspect_data[aspect][sentiment] += 1

        aspect_summary = {}
        for aspect, sentiments in aspect_data.items():
            total = sum(sentiments.values())
            if total == 0:
                continue
            pos = sentiments.get("positive", 0)
            neg = sentiments.get("negative", 0)
            neu = sentiments.get("neutral", 0)
            aspect_summary[aspect] = {
                "total_mentions": total,
                "positive": pos,
                "negative": neg,
                "neutral": neu,
                "positive_rate": round(pos / total * 100, 1),
                "negative_rate": round(neg / total * 100, 1),
            }

        result.aspect_sentiment_summary = aspect_summary
        self.log(
            f"Sentiment: {dict(sentiment_counts)} | "
            f"Aspects analyzed: {len(aspect_summary)}"
        )
        return result

    def deep_analyze(
        self,
        reviews: list[Review],
        retriever: ReviewRetriever,
        result: VOCAnalysisResult,
    ) -> VOCAnalysisResult:
        """Use RAG to deeply analyze sentiment for the most-mentioned aspects."""
        self.log("Deep sentiment analysis with RAG evidence...")

        # Pick the top aspects by mention volume from whatever VOCTaxonomyAgent actually tagged
        # for this product's reviews (analyze_sentiment_distribution, run just before this, already
        # built aspect_sentiment_summary keyed by those real tags) — adapts to any product category
        # automatically instead of assuming a fixed, TV-specific aspect list.
        key_aspects = sorted(
            result.aspect_sentiment_summary,
            key=lambda a: result.aspect_sentiment_summary[a].get("total_mentions", 0),
            reverse=True,
        )[:4]

        for aspect in key_aspects:
            relevant = retriever.retrieve(
                query=f"customer experience with {aspect.replace('_', ' ')} of this product",
                top_k=15,
            )
            aspect_reviews = [
                r for r in relevant if aspect in (r.aspects or [])
            ][:10]

            if len(aspect_reviews) < 3:
                continue

            context = retriever.format_for_context(aspect_reviews)
            prompt = f"""Analyze customer sentiment for the aspect "{aspect}" based on these {len(aspect_reviews)} reviews:

{context}

Provide a JSON response:
{{
  "aspect": "{aspect}",
  "overall_sentiment": "positive|neutral|negative",
  "positive_themes": ["theme1", "theme2"],
  "negative_themes": ["theme1", "theme2"],
  "key_insight": "one sentence insight",
  "positive_rate": 0.0
}}"""
            try:
                analysis = self.call_json(prompt, max_tokens=1024)
                if aspect in result.aspect_sentiment_summary:
                    result.aspect_sentiment_summary[aspect]["insight"] = analysis.get("key_insight", "")
                    result.aspect_sentiment_summary[aspect]["positive_themes"] = analysis.get("positive_themes", [])
                    result.aspect_sentiment_summary[aspect]["negative_themes"] = analysis.get("negative_themes", [])
            except Exception as e:
                self.log(f"[yellow]Deep analysis for {aspect} failed: {e}")

        return result
