"""Task 9: Customer segment / use-case divergence analysis."""
from __future__ import annotations

from typing import Optional

from src.agents.base import BaseAgent
from src.config import settings
from src.data.models import ProductSpec, Review, SegmentDivergenceAnalysis, SegmentInsight, VOCAnalysisResult
from src.rag.retriever import ReviewRetriever

SYSTEM_PROMPT = """You are a VOC strategy analyst specializing in segment-level divergence.
Your job is to find where different customer segments experience the product differently.

Focus on segment patterns relevant to this specific product's category, such as:
- core-performance-first customers (the attribute this product category is bought for)
- price/value-sensitive customers
- usability/setup-focused customers
- brand-premium expectation customers
- reliability / long-term ownership customers

Use review evidence to identify which segments are satisfied, which are frustrated,
and which are strategically important even if they are not the largest group.
Return structured JSON only."""


class SegmentDivergenceAnalysisAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="SegmentDivergenceAnalysisAgent",
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
        self.log("Analyzing segment and use-case divergence (Task 9)...")

        usable = [r for r in reviews if not r.is_duplicate and not r.is_short]
        verified = [r for r in usable if r.verified_purchase]
        helpful = sorted(usable, key=lambda r: r.helpful_votes, reverse=True)[:12]
        recent_signals = sorted(
            [r for r in usable if r.date],
            key=lambda r: r.date or "",
            reverse=True,
        )[:10]

        queries = [
            "performance quality how well it works for its main purpose",
            "price value worth money bang for buck cheap expensive",
            "setup installation easy to use straightforward",
            "Samsung brand premium expectation quality reputation",
            "reliability defect broken return warranty long term",
        ]

        segment_reviews = []
        for query in queries:
            segment_reviews.extend(retriever.retrieve(query, top_k=6))

        pool = list({r.review_id: r for r in verified + helpful + recent_signals + segment_reviews}.values())[:30]
        context = retriever.format_for_context(pool, max_chars=9000)

        complaint_summary = "\n".join(
            f"- {c.category}: {c.root_cause}" for c in result.complaints[:6]
        )
        satisfaction_summary = "\n".join(
            f"- {s.factor}: {s.positive_rate:.0f}% positive" for s in result.satisfaction_drivers[:6]
        )

        product_label = product_spec.product_name if product_spec and product_spec.product_name else result.model

        prompt = f"""Analyze how customer experience diverges by segment or use case for {product_label}.

KNOWN COMPLAINTS:
{complaint_summary}

KNOWN SATISFACTION DRIVERS:
{satisfaction_summary}

EVIDENCE POOL:
{context}

Interpret the reviews through segment lenses appropriate to this specific product category — e.g.
core-performance-first, price-sensitive, usability-focused, brand-premium expectation, and
reliability-focused customers.

Return JSON in this shape:
{{
  "segment_insights": [
    {{
      "segment": "segment name",
      "size_estimate": <estimated review count>,
      "key_positive_factors": ["..."],
      "key_pain_points": ["..."],
      "expectation_gap": "what this segment expected vs. what it experienced",
      "business_implication": "why this segment matters commercially",
      "recommended_action": "specific product or marketing action",
      "evidence": ["actual quote", "actual quote"]
    }}
  ],
  "emerging_risks": ["risk 1", "risk 2", "risk 3"],
  "emerging_opportunities": ["opportunity 1", "opportunity 2", "opportunity 3"],
  "priority_actions": ["action 1", "action 2", "action 3"],
  "marketing_message_by_segment": ["message for segment A", "message for segment B"]
}}"""

        try:
            data = self.call_json(prompt, max_tokens=4096)
            insights_raw = data.get("segment_insights", []) if isinstance(data, dict) else []
            segment_insights = []
            for item in insights_raw:
                segment_insights.append(
                    SegmentInsight(
                        segment=item.get("segment", ""),
                        size_estimate=item.get("size_estimate", 0),
                        key_positive_factors=item.get("key_positive_factors", []),
                        key_pain_points=item.get("key_pain_points", []),
                        expectation_gap=item.get("expectation_gap", ""),
                        business_implication=item.get("business_implication", ""),
                        recommended_action=item.get("recommended_action", ""),
                        evidence=item.get("evidence", []),
                    )
                )

            result.segment_divergence_analysis = SegmentDivergenceAnalysis(
                segment_insights=segment_insights,
                emerging_risks=data.get("emerging_risks", []) if isinstance(data, dict) else [],
                emerging_opportunities=data.get("emerging_opportunities", []) if isinstance(data, dict) else [],
                priority_actions=data.get("priority_actions", []) if isinstance(data, dict) else [],
                marketing_message_by_segment=data.get("marketing_message_by_segment", []) if isinstance(data, dict) else [],
            )
            self.log(f"Segment divergence analysis complete: {len(segment_insights)} segments analyzed")
        except Exception as e:
            self.log(f"[red]Segment divergence analysis failed: {e}")

        return result