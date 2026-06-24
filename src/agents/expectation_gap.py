"""Task 8: Customer Expectation Gap Analysis — the most important analysis."""
from __future__ import annotations

from typing import Optional

from src.agents.base import BaseAgent
from src.config import settings
from src.data.models import ExpectationGapItem, ProductSpec, Review, VOCAnalysisResult
from src.rag.retriever import ReviewRetriever

SYSTEM_PROMPT = """You are a customer experience strategist specializing in expectation management.
Your most important task is to identify the gap between what customers EXPECTED when purchasing
a Samsung product and what they ACTUALLY experienced after using it.

Pre-purchase expectations are revealed through:
- "I expected...", "I thought it would...", "Samsung is known for..."
- "Brand reputation", "Premium", "Samsung quality"
- "For the price I expected...", "At this price point..."
- Comparisons to previous products or brand promises

Actual experiences are revealed through:
- Specific observations after use
- Direct comparisons to expectations
- Complaints about unmet expectations
- Positive surprises (expected less, got more)

The gap analysis is critical for:
1. Product roadmap (where to invest to close gaps)
2. Marketing alignment (set realistic expectations)
3. Pricing strategy (justify premium or adjust)
4. Customer experience design

Return structured JSON only."""


class ExpectationGapAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="ExpectationGapAgent",
            model=settings.model_sonnet,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.3,
        )

    def analyze(
        self,
        reviews: list[Review],
        retriever: ReviewRetriever,
        result: VOCAnalysisResult,
        product_spec: Optional[ProductSpec] = None,
    ) -> VOCAnalysisResult:
        self.log("Running Expectation Gap Analysis (Task 8) with Claude Sonnet...")

        # Targeted retrieval for expectation signals
        expectation_reviews = retriever.retrieve(
            "expected thought Samsung brand quality premium reputation disappointing surprised better worse",
            top_k=20,
        )
        price_expectation = retriever.retrieve(
            "for the price worth money value expected at this price point",
            top_k=10,
        )
        brand_expectation = retriever.retrieve(
            "Samsung brand trust premium quality reliability known reputation",
            top_k=10,
        )

        pool = list({
            r.review_id: r
            for r in expectation_reviews + price_expectation + brand_expectation
        }.values())[:25]

        # Fallback: if RAG is empty (e.g. in-memory store not shared across nodes),
        # sample directly from reviews so the agent always has context.
        if not pool and reviews:
            import random
            pool = random.sample(reviews, min(25, len(reviews)))
            self.log("[yellow]RAG pool empty — using direct review sample as fallback")

        context = retriever.format_for_context(pool, max_chars=8000)

        complaints_str = "\n".join(f"- {c.category}: {c.root_cause}" for c in result.complaints[:6])
        satisfaction_str = "\n".join(f"- {s.factor}" for s in result.satisfaction_drivers[:5])
        product_label = product_spec.product_name if product_spec and product_spec.product_name else result.model

        prompt = f"""Perform a deep Customer Expectation Gap Analysis for {product_label}.

This is the most strategic analysis. Identify EXACTLY where customer expectations diverge from reality.

WHAT CUSTOMERS COMPLAIN ABOUT (actual experience gaps):
{complaints_str}

WHAT CUSTOMERS VALUE (actual positive experiences):
{satisfaction_str}

CUSTOMER REVIEWS WITH EXPECTATION SIGNALS:
{context}

Identify 7-8 key expectation dimensions — each one must trace back to a DISTINCT underlying complaint
or root cause. If two candidate dimensions would both be evidenced by the same underlying issue (e.g.
a "Brand Quality" gap and a "Reliability" gap that are both really just about the same screen/panel
failures, narrated from two different angles), merge them into ONE dimension rather than splitting the
same root cause into two entries with different framing. For each:
{{
  "expectation_gaps": [
    {{
      "dimension": "concise topic name ONLY, 1-3 words (e.g. 'Brand Quality', 'Picture Quality') —
        the Expected/Reality split is already shown below this title, so do NOT repeat words like
        'expectation', 'vs.', or 'reality' in the dimension name itself",
      "expectation": "what customers expected BEFORE purchase, one specific sentence",
      "actual_experience": "what customers ACTUALLY experienced, one specific sentence",
      "gap_severity": "high|medium|low",
      "gap_description": "the business implication ONLY — one sentence on the downstream consequence
        (lost sales, returns, brand trust, etc.) if this gap goes unaddressed. Do not restate or
        paraphrase the expectation/actual_experience sentences above — say something they don't already say",
      "recommended_action": "specific actionable recommendation for Samsung product/marketing team",
      "supporting_reviews": ["actual quote from reviews above", "another actual quote"]
    }}
  ],
  "overall_gap_insight": "strategic insight: what is the single biggest expectation gap?"
}}

Dimensions to consider — adapt these to what's actually relevant for this specific product
(name each field with just the short topic, not this full phrasing):
- Brand quality
- Core product performance (the attributes this product category is bought for, e.g. picture
  quality for a TV, cooling/temperature consistency for a refrigerator)
- Price-value
- Reliability
- Setup / ease-of-use
- Any other dimension the reviews surface as a recurring expectation theme"""

        try:
            data = self.call_json(prompt, max_tokens=5000)
            gaps_raw = data.get("expectation_gaps", []) if isinstance(data, dict) else []

            for item in gaps_raw:
                result.expectation_gaps.append(
                    ExpectationGapItem(
                        dimension=item.get("dimension", ""),
                        expectation=item.get("expectation", ""),
                        actual_experience=item.get("actual_experience", ""),
                        gap_severity=item.get("gap_severity", "medium"),
                        gap_description=item.get("gap_description", ""),
                        recommended_action=item.get("recommended_action", ""),
                        supporting_reviews=item.get("supporting_reviews", []),
                    )
                )
            self.log(f"Expectation gap analysis: {len(result.expectation_gaps)} dimensions analyzed")
        except Exception as e:
            self.log(f"[red]Expectation gap analysis failed: {e}")

        return result
