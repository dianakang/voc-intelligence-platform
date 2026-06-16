"""Report Generation Agent: executive summary + key insights using Claude Opus."""
from __future__ import annotations

from datetime import datetime

from src.agents.base import BaseAgent
from src.config import settings
from src.data.models import VOCAnalysisResult

SYSTEM_PROMPT = """You are a senior management consultant generating executive-level reports
for Samsung's product intelligence team. Your audience is senior product managers, VP-level
marketing leaders, and quality engineering heads.

Your reports must be:
1. Evidence-based: every claim references actual customer data
2. Actionable: recommendations are specific and implementable
3. Strategic: connects VOC data to business outcomes
4. Concise: executives need crisp insights, not verbose summaries

Write in professional business English. Be direct and confident."""


class ReportGenerationAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="ReportGenerationAgent",
            model=settings.model_opus,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.4,
        )

    def generate_executive_summary(self, result: VOCAnalysisResult) -> VOCAnalysisResult:
        self.log("Generating executive summary with Claude Opus...")

        top_complaints = "\n".join(
            f"{c.rank}. {c.category} ({c.frequency_pct:.0f}% of complaints): {c.root_cause}"
            for c in result.complaints[:5]
        )
        top_satisfiers = "\n".join(
            f"{s.rank}. {s.factor} ({s.positive_rate:.0f}% positive)"
            for s in result.satisfaction_drivers[:4]
        )
        top_gaps = "\n".join(
            f"- {g.dimension} [{g.gap_severity.upper()}]: {g.gap_description[:120]}..."
            for g in sorted(result.expectation_gaps, key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.gap_severity, 1))[:4]
        )
        top_improvements = "\n".join(
            f"- [{i.priority.upper()}] {i.area}: {i.expected_effect}"
            for i in sorted(result.improvement_points, key=lambda x: x.impact_score, reverse=True)[:5]
        )
        contradiction_summary = (
            f"{len(result.contradictions)} contradictions detected "
            f"({sum(1 for c in result.contradictions if c.contradiction_type == 'type_a')} Type A, "
            f"{sum(1 for c in result.contradictions if c.contradiction_type == 'type_b')} Type B)"
        )
        positioning_note = ""
        if result.positioning_analysis:
            positioning_note = f"Key competitive edge: {', '.join(result.positioning_analysis.competitive_advantages[:2])}"

        sentiment = result.sentiment_distribution
        total = sum(sentiment.values()) or 1

        prompt = f"""Generate an executive summary for Samsung 50" Crystal UHD U7900F VOC Intelligence Report.

ANALYSIS DATE: {result.analysis_date}
TOTAL REVIEWS ANALYZED: {result.total_reviews}
AVERAGE RATING: {result.avg_rating:.1f}/5
SENTIMENT: {sentiment.get('positive',0)} positive ({sentiment.get('positive',0)/total*100:.0f}%), {sentiment.get('neutral',0)} neutral, {sentiment.get('negative',0)} negative

TOP 5 CUSTOMER COMPLAINTS:
{top_complaints}

TOP 4 SATISFACTION DRIVERS:
{top_satisfiers}

EXPECTATION GAPS:
{top_gaps}

PRODUCT IMPROVEMENT PRIORITIES:
{top_improvements}

CONTRADICTION ANALYSIS:
{contradiction_summary}

COMPETITIVE POSITIONING:
{positioning_note}

Generate:
1. Executive Summary (3-4 paragraphs, ~300 words): strategic overview connecting data to business impact
2. 8-10 Key Insights (bullet points, specific and actionable)

Format as:
EXECUTIVE SUMMARY:
[summary here]

KEY INSIGHTS:
• [insight 1]
• [insight 2]
..."""

        try:
            response = self.call(prompt, max_tokens=3000)

            # Split into summary and insights
            if "KEY INSIGHTS:" in response:
                parts = response.split("KEY INSIGHTS:")
                result.executive_summary = parts[0].replace("EXECUTIVE SUMMARY:", "").strip()
                insights_text = parts[1].strip()
                result.key_insights = [
                    line.lstrip("•-* ").strip()
                    for line in insights_text.split("\n")
                    if line.strip() and line.strip() not in ("", "KEY INSIGHTS:")
                ][:10]
            else:
                result.executive_summary = response
                result.key_insights = []

            self.log(f"Executive summary generated ({len(result.executive_summary)} chars, {len(result.key_insights)} insights)")
        except Exception as e:
            self.log(f"[red]Report generation failed: {e}")
            result.executive_summary = "Report generation failed. Please check API configuration."
            result.key_insights = ["Analysis complete — see individual sections for details."]

        return result
