"""VOC Taxonomy Agent: classify reviews by aspect."""
from __future__ import annotations

import json

from src.agents.base import BaseAgent
from src.config import settings
from src.data.models import Aspect, Review

ASPECTS = [a.value for a in Aspect]

SYSTEM_PROMPT = f"""You are a VOC (Voice of Customer) taxonomy expert for consumer electronics.
Your task is to classify TV product reviews by the aspects they mention.

Available aspects:
- picture_quality: Display, resolution, HDR, color, brightness, contrast, image clarity, 4K
- sound: Audio quality, speakers, bass, volume, Dolby Atmos, soundbar mentions
- smart_tv: Tizen OS, apps, streaming, interface, UI/UX, menus, voice assistant, speed
- price: Value for money, cost, price comparison, deals, worth it
- installation: Setup, mounting, wall mount, assembly, initial configuration
- reliability: Durability, defects, dead pixels, hardware failures, freezing, crashing, warranty
- design: Physical appearance, bezel, stand, slim profile, aesthetics, remote control
- gaming: Gaming mode, input lag, FPS, VRR, FreeSync, HDMI 2.1, Game Bar
- connectivity: HDMI ports, USB, WiFi, Bluetooth, Ethernet, network
- remote: Remote control design, buttons, Eco Remote, Solar Remote
- other: Anything not fitting above categories

For each review, return a JSON object with:
{{
  "aspects": ["aspect1", "aspect2"],
  "aspect_sentiments": {{"aspect1": "positive|neutral|negative", "aspect2": "positive|neutral|negative"}},
  "overall_sentiment": "positive|neutral|negative"
}}
"""


class VOCTaxonomyAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="VOCTaxonomyAgent",
            model=settings.model_haiku,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.1,
        )

    def classify_reviews(self, reviews: list[Review], batch_size: int = 10) -> list[Review]:
        self.log(f"Classifying aspects for {len(reviews)} reviews...")
        substantive = [r for r in reviews if not r.is_duplicate and not r.is_short]

        for i in range(0, len(substantive), batch_size):
            batch = substantive[i : i + batch_size]
            self._classify_batch(batch)
            if (i + batch_size) % 50 == 0:
                self.log(f"Classified {min(i + batch_size, len(substantive))}/{len(substantive)}")

        self.log("Taxonomy classification complete")
        return reviews

    def _classify_batch(self, reviews: list[Review]) -> None:
        items = []
        for r in reviews:
            text = r.cleaned_text or r.text
            title = f"Title: {r.title}\n" if r.title else ""
            items.append(f"{title}Rating: {r.rating}/5\nReview: {text}")

        prompt = (
            f"Classify each of the following {len(reviews)} TV reviews.\n"
            f"Return a JSON array of {len(reviews)} objects, one per review.\n\n"
            + "\n\n---\n\n".join(f"Review {i+1}:\n{text}" for i, text in enumerate(items))
        )

        try:
            results = self.call_json(prompt, max_tokens=4096)
            if not isinstance(results, list):
                results = [results]
            for review, result in zip(reviews, results):
                aspects_raw = result.get("aspects", [])
                review.aspects = [a for a in aspects_raw if a in ASPECTS]
                review.aspect_sentiments = result.get("aspect_sentiments", {})
                review.overall_sentiment = result.get("overall_sentiment", "neutral")
        except Exception as e:
            self.log(f"[yellow]Batch classification failed: {e}, using rating-based fallback")
            for review in reviews:
                review.overall_sentiment = (
                    "positive" if review.rating >= 4
                    else "negative" if review.rating <= 2
                    else "neutral"
                )
                review.aspects = ["other"]
