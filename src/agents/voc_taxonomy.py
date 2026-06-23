"""VOC Taxonomy Agent: classify reviews by aspect."""
from __future__ import annotations

from typing import Optional

from src.agents.base import BaseAgent
from src.config import settings
from src.data.models import Review

# Universal aspects that apply to almost any consumer product category.
_UNIVERSAL_ASPECTS = """- price: Value for money, cost, price comparison, deals, worth it
- installation: Setup, assembly, initial configuration, delivery/unboxing
- reliability: Durability, defects, hardware failures, breakdowns, warranty
- design: Physical appearance, build quality, aesthetics
- other: Anything not fitting the categories above"""

# TV-specific aspects, kept as-is for the category this platform was originally built for.
_TV_ASPECTS = """- picture_quality: Display, resolution, HDR, color, brightness, contrast, image clarity, 4K
- sound: Audio quality, speakers, bass, volume, Dolby Atmos, soundbar mentions
- smart_tv: Tizen OS, apps, streaming, interface, UI/UX, menus, voice assistant, speed
- gaming: Gaming mode, input lag, FPS, VRR, FreeSync, HDMI 2.1, Game Bar
- connectivity: HDMI ports, USB, WiFi, Bluetooth, Ethernet, network
- remote: Remote control design, buttons, Eco Remote, Solar Remote"""

SYSTEM_PROMPT = """You are a VOC (Voice of Customer) taxonomy expert for consumer products.
Your task is to classify product reviews by the aspects they mention, using the aspect list
given to you in each request (it varies by the product category being analyzed). Apply only
the aspects that are genuinely relevant to what's actually said in the review.

For each review, return a JSON object with:
{
  "aspects": ["aspect1", "aspect2"],
  "aspect_sentiments": {"aspect1": "positive|neutral|negative", "aspect2": "positive|neutral|negative"},
  "overall_sentiment": "positive|neutral|negative"
}
"""


def _aspect_list_for_category(category: Optional[str]) -> str:
    """TVs get the original detailed TV aspect list; everything else gets the universal
    aspects plus an instruction to name additional category-specific aspects freely."""
    if category and category.upper() == "TV":
        return _UNIVERSAL_ASPECTS + "\n" + _TV_ASPECTS
    return (
        _UNIVERSAL_ASPECTS
        + "\n- (also use any other short, lowercase_with_underscores aspect tag genuinely relevant "
        + f"to this product category{f' ({category})' if category else ''}, e.g. 'cooling' or "
        + "'ice_maker' for a refrigerator, 'spin_cycle' for a washer — invent tags as needed)"
    )


class VOCTaxonomyAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="VOCTaxonomyAgent",
            model=settings.model_haiku,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.1,
        )

    def classify_reviews(
        self,
        reviews: list[Review],
        batch_size: int = settings.batch_size,
        category: Optional[str] = None,
    ) -> list[Review]:
        self.log(f"Classifying aspects for {len(reviews)} reviews...")
        substantive = [r for r in reviews if not r.is_duplicate and not r.is_short]

        for i in range(0, len(substantive), batch_size):
            batch = substantive[i : i + batch_size]
            self._classify_batch(batch, category)
            if (i + batch_size) % 50 == 0:
                self.log(f"Classified {min(i + batch_size, len(substantive))}/{len(substantive)}")

        self.log("Taxonomy classification complete")
        return reviews

    def _classify_batch(self, reviews: list[Review], category: Optional[str]) -> None:
        items = []
        for r in reviews:
            text = r.cleaned_text or r.text
            title = f"Title: {r.title}\n" if r.title else ""
            items.append(f"{title}Rating: {r.rating}/5\nReview: {text}")

        prompt = (
            f"Classify each of the following {len(reviews)} reviews of a "
            f"{category or 'consumer product'}.\n\n"
            f"Available aspects:\n{_aspect_list_for_category(category)}\n\n"
            f"Return a JSON array of {len(reviews)} objects, one per review.\n\n"
            + "\n\n---\n\n".join(f"Review {i+1}:\n{text}" for i, text in enumerate(items))
        )

        try:
            results = self.call_json(prompt, max_tokens=4096)
            if not isinstance(results, list):
                results = [results]
            for review, result in zip(reviews, results):
                aspects_raw = result.get("aspects", [])
                review.aspects = [a for a in aspects_raw if isinstance(a, str) and a]
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
