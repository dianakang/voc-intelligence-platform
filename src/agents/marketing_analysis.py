"""Task 4: Marketing Message Improvement Analysis."""
from __future__ import annotations

from typing import Optional

from src.agents.base import BaseAgent
from src.config import settings
from src.data.models import MarketingRecommendation, ProductSpec, Review, VOCAnalysisResult
from src.rag.retriever import ReviewRetriever

SYSTEM_PROMPT = """You are a marketing strategist with expertise in consumer electronics branding.
You analyze the gap between what brands promise and what customers actually experience,
then generate authentic marketing messages grounded in real customer voice.
Return structured JSON only."""

# Used only if no live-scraped product_spec is available.
FALLBACK_MESSAGING = "(no verified product marketing copy available — infer current positioning from the customer voice evidence below only)"


def _build_current_messaging(product_spec: Optional[ProductSpec]) -> str:
    """Build the 'current marketing messages' block from verified product data, not a hand-typed guess."""
    if not product_spec or not (product_spec.spec_highlights or product_spec.other.get("marketing_highlights")):
        return FALLBACK_MESSAGING

    lines = [f"{product_spec.product_name} current marketing messages (source: {product_spec.spec_source}):"]
    for h in product_spec.other.get("marketing_highlights", []) or product_spec.spec_highlights:
        lines.append(f'- "{h}"')
    price = product_spec.other.get("price_usd")
    if price:
        lines.append(f"- Priced at ${price} (MSRP ${product_spec.other.get('msrp_usd', price)})")
    return "\n".join(lines)


class MarketingAnalysisAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="MarketingAnalysisAgent",
            model=settings.model_sonnet,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.4,
        )

    def analyze(
        self,
        reviews: list[Review],
        retriever: ReviewRetriever,
        result: VOCAnalysisResult,
        product_spec: Optional[ProductSpec] = None,
    ) -> VOCAnalysisResult:
        self.log("Analyzing marketing message alignment (Task 4)...")

        # Get reviews that mention brand expectations
        brand_reviews = retriever.retrieve(
            "Samsung brand quality expected expected better premium reputation worth",
            top_k=15,
        )
        value_reviews = retriever.retrieve(
            "great value worth the price bang for buck recommend buy",
            top_k=10,
        )

        pool = list({r.review_id: r for r in brand_reviews + value_reviews}.values())[:20]
        context = retriever.format_for_context(pool, max_chars=6000)

        satisfaction_summary = "\n".join(
            f"- {s.factor} ({s.positive_rate:.0f}% positive)"
            for s in result.satisfaction_drivers[:5]
        )
        complaint_summary = "\n".join(
            f"- {c.category}: {c.root_cause}"
            for c in result.complaints[:5]
        )

        prompt = f"""Analyze the gap between Samsung's marketing messages and actual customer experience.

{_build_current_messaging(product_spec)}

WHAT CUSTOMERS ACTUALLY VALUE (from VOC):
{satisfaction_summary}

MAIN COMPLAINTS:
{complaint_summary}

CUSTOMER VOICE EVIDENCE:
{context}

Generate marketing message recommendations:
{{
  "current_perception": "how customers currently perceive this product and brand",
  "actual_value_drivers": [
    "specific value element customers genuinely appreciate"
  ],
  "new_message_proposals": [
    "new marketing message 1 grounded in actual customer experience",
    "new marketing message 2",
    "new marketing message 3",
    "new marketing message 4"
  ],
  "messages_to_avoid": [
    "message/claim that backfires due to customer experience gap"
  ],
  "evidence": [
    "actual customer quote supporting a new message"
  ]
}}"""

        try:
            data = self.call_json(prompt, max_tokens=2048)
            result.marketing_recommendations = MarketingRecommendation(
                current_perception=data.get("current_perception", ""),
                actual_value_drivers=data.get("actual_value_drivers", []),
                new_message_proposals=data.get("new_message_proposals", []),
                messages_to_avoid=data.get("messages_to_avoid", []),
                evidence=data.get("evidence", []),
            )
            self.log("Marketing analysis complete")
        except Exception as e:
            self.log(f"[red]Marketing analysis failed: {e}")

        return result
