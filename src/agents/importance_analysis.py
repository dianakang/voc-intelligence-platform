"""Task 7: Importance Analysis — frequency vs. business impact matrix."""
from __future__ import annotations

from src.agents.base import BaseAgent
from src.config import settings
from src.data.models import ImportanceItem, Review, VOCAnalysisResult
from src.rag.retriever import ReviewRetriever

SYSTEM_PROMPT = """You are a product strategy analyst specializing in customer issue prioritization.
Your job is to distinguish between issues that are frequently mentioned but have low business impact,
versus issues that are rarely mentioned but carry high business risk.

High Frequency / Low Impact: Issues mentioned often but don't significantly affect purchase decisions,
brand loyalty, or repeat sales (e.g., minor UX annoyances, cosmetic preferences).

Low Frequency / High Impact: Issues mentioned rarely but with severe consequences — defects that
cause returns, warranty claims, negative word-of-mouth, or damage to brand reputation
(e.g., dead pixels, power failures, panel defects, complete hardware failures).

This distinction is critical for product prioritization and quality engineering.
Return structured JSON only."""


class ImportanceAnalysisAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="ImportanceAnalysisAgent",
            model=settings.model_sonnet,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.2,
        )

    def analyze(self, reviews: list[Review], retriever: ReviewRetriever, result: VOCAnalysisResult) -> VOCAnalysisResult:
        self.log("Analyzing issue frequency vs. impact matrix (Task 7)...")

        usable = [r for r in reviews if not r.is_duplicate and not r.is_short]
        total = len(usable)

        # Get reviews mentioning high-impact issues
        high_impact_reviews = retriever.retrieve(
            "dead pixel panel defect power failure hardware broken warranty return",
            top_k=10,
        )
        # Get reviews mentioning common minor issues
        low_impact_reviews = retriever.retrieve(
            "remote control menu UI interface ads home screen annoying minor",
            top_k=10,
        )

        complaints_context = "\n".join(
            f"- {c.category} (mentioned ~{c.frequency} times, {c.frequency_pct:.0f}%): {c.root_cause}"
            for c in result.complaints[:8]
        )

        all_reviews_context = retriever.format_for_context(
            high_impact_reviews + low_impact_reviews, max_chars=4000
        )

        prompt = f"""Classify customer issues for Samsung 50" Crystal UHD U7900F by frequency vs. business impact.

Total reviews analyzed: {total}

KNOWN COMPLAINT CATEGORIES:
{complaints_context}

SAMPLE REVIEWS (high/low impact):
{all_reviews_context}

Identify ALL issues and classify them. Return:
{{
  "importance_matrix": [
    {{
      "issue": "specific issue name",
      "frequency": <estimated count>,
      "frequency_pct": <percentage of all reviews>,
      "impact": "high" or "low",
      "category": "high_freq_low_impact" or "low_freq_high_impact" or "high_freq_high_impact" or "low_freq_low_impact",
      "business_risk": "description of business consequence if unaddressed",
      "representative_reviews": ["quote 1", "quote 2"]
    }}
  ]
}}

Include at minimum:
- 3 High Frequency / Low Impact issues
- 3 Low Frequency / High Impact issues
- 2 High Frequency / High Impact issues"""

        try:
            data = self.call_json(prompt, max_tokens=3000)
            matrix = data.get("importance_matrix", data) if isinstance(data, dict) else data

            for item in matrix:
                result.importance_matrix.append(
                    ImportanceItem(
                        issue=item.get("issue", ""),
                        frequency=item.get("frequency", 0),
                        frequency_pct=item.get("frequency_pct", 0.0),
                        impact=item.get("impact", "low"),
                        category=item.get("category", "low_freq_low_impact"),
                        business_risk=item.get("business_risk", ""),
                        representative_reviews=item.get("representative_reviews", []),
                    )
                )
            self.log(f"Importance matrix: {len(result.importance_matrix)} issues classified")
        except Exception as e:
            self.log(f"[red]Importance analysis failed: {e}")

        return result
