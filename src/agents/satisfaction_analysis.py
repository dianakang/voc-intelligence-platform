"""Task 2 & 3: Satisfaction Factor Analysis and Product Improvement Points."""
from __future__ import annotations

from src.agents.base import BaseAgent
from src.config import settings
from src.data.models import ImprovementPoint, Priority, Review, SatisfactionDriver, VOCAnalysisResult
from src.rag.retriever import ReviewRetriever

SATISFACTION_SYSTEM = """You are a customer experience expert analyzing what drives purchase satisfaction
for consumer electronics. Identify the core factors that make customers happy with their TV purchase.
Focus on genuine satisfaction drivers, not just absence of complaints.
Return structured JSON only."""

IMPROVEMENT_SYSTEM = """You are a product management expert who translates customer VOC data into
actionable product improvement recommendations. You prioritize improvements by business impact,
implementation feasibility, and customer need frequency.
Return structured JSON only."""


class SatisfactionAnalysisAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="SatisfactionAnalysisAgent",
            model=settings.model_sonnet,
            system_prompt=SATISFACTION_SYSTEM,
            temperature=0.2,
        )

    def analyze(
        self,
        reviews: list[Review],
        retriever: ReviewRetriever,
        result: VOCAnalysisResult,
    ) -> VOCAnalysisResult:
        self.log("Analyzing satisfaction factors (Task 2)...")

        positive_reviews = [
            r for r in reviews
            if not r.is_duplicate and not r.is_short and r.rating >= 4
        ]
        rag_positive = retriever.retrieve_positive("excellent great love satisfied happy recommend", top_k=15)
        pool = list({r.review_id: r for r in positive_reviews + rag_positive}.values())

        context = retriever.format_for_context(pool[:20], max_chars=7000)

        prompt = f"""Analyze these positive Samsung TV reviews to identify the TOP 6 satisfaction drivers.

Reviews ({len(pool)} positive reviews):
{context}

Product: Samsung 50" Crystal UHD U7900F
Total 4-5 star reviews: {len(positive_reviews)} out of {len([r for r in reviews if not r.is_duplicate])} total

Return:
{{
  "satisfaction_drivers": [
    {{
      "rank": 1,
      "factor": "specific satisfaction factor",
      "aspect": "picture_quality|sound|smart_tv|price|reliability|design|gaming|connectivity",
      "positive_rate": <percentage 0-100>,
      "mention_count": <estimated count>,
      "representative_reviews": ["actual quote 1", "actual quote 2", "actual quote 3"]
    }}
  ]
}}"""

        try:
            data = self.call_json(prompt, max_tokens=3000)
            drivers = data.get("satisfaction_drivers", data) if isinstance(data, dict) else data
            for item in drivers:
                result.satisfaction_drivers.append(
                    SatisfactionDriver(
                        rank=item.get("rank", 0),
                        factor=item.get("factor", ""),
                        aspect=item.get("aspect", "other"),
                        positive_rate=item.get("positive_rate", 0.0),
                        mention_count=item.get("mention_count", 0),
                        representative_reviews=item.get("representative_reviews", []),
                    )
                )
            self.log(f"Identified {len(result.satisfaction_drivers)} satisfaction drivers")
        except Exception as e:
            self.log(f"[red]Satisfaction analysis failed: {e}")

        return result


class ImprovementAnalysisAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="ImprovementAnalysisAgent",
            model=settings.model_sonnet,
            system_prompt=IMPROVEMENT_SYSTEM,
            temperature=0.3,
        )

    def analyze(
        self,
        reviews: list[Review],
        retriever: ReviewRetriever,
        result: VOCAnalysisResult,
    ) -> VOCAnalysisResult:
        self.log("Deriving product improvement points (Task 3)...")

        complaints_summary = "\n".join(
            f"- {c.category}: {c.frequency} mentions, root cause: {c.root_cause}"
            for c in result.complaints[:8]
        )
        satisfaction_summary = "\n".join(
            f"- {s.factor}: {s.positive_rate:.0f}% positive rate"
            for s in result.satisfaction_drivers[:6]
        )

        rag_improvement = retriever.retrieve("wish could improve better if only would be better", top_k=10)
        context = retriever.format_for_context(rag_improvement, max_chars=4000)

        prompt = f"""Based on VOC analysis of Samsung 50" Crystal UHD U7900F reviews, generate prioritized product improvement recommendations.

COMPLAINT ANALYSIS:
{complaints_summary}

SATISFACTION DRIVERS:
{satisfaction_summary}

ADDITIONAL CUSTOMER VOICE:
{context}

Product spec context:
- Display: Crystal UHD (VA panel), 60Hz, HDR10+
- Audio: 20W 2.0 channel, no Dolby Atmos
- Smart TV: Tizen OS, Bixby/Alexa/Google
- Gaming: FreeSync Premium, ~13ms input lag

Generate TOP 8 improvement recommendations. Prioritize by: customer impact × feasibility × competitive gap.

Return:
{{
  "improvements": [
    {{
      "area": "specific improvement area",
      "expected_effect": "what business/customer outcome this improvement delivers",
      "priority": "high|medium|low",
      "frequency": <how many customers mentioned this>,
      "impact_score": <1-10>,
      "supporting_evidence": ["quote 1", "quote 2"]
    }}
  ]
}}"""

        try:
            data = self.call_json(prompt, max_tokens=4096)
            improvements = data.get("improvements", data) if isinstance(data, dict) else data
            priority_map = {"high": Priority.HIGH, "medium": Priority.MEDIUM, "low": Priority.LOW}
            for item in improvements:
                result.improvement_points.append(
                    ImprovementPoint(
                        area=item.get("area", ""),
                        expected_effect=item.get("expected_effect", ""),
                        priority=priority_map.get(item.get("priority", "medium"), Priority.MEDIUM),
                        frequency=item.get("frequency", 0),
                        impact_score=item.get("impact_score", 5.0),
                        supporting_evidence=item.get("supporting_evidence", []),
                    )
                )
            self.log(f"Generated {len(result.improvement_points)} improvement recommendations")
        except Exception as e:
            self.log(f"[red]Improvement analysis failed: {e}")

        return result
