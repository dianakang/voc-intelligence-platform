"""Task 1: Major Customer Complaint Analysis with Root Cause."""
from __future__ import annotations

from collections import defaultdict

from src.agents.base import BaseAgent
from src.config import settings
from src.data.models import ComplaintItem, Review, VOCAnalysisResult
from src.rag.retriever import ReviewRetriever

SYSTEM_PROMPT = """You are a customer experience analyst specializing in identifying and analyzing
product complaints in consumer electronics reviews.

Your task is to:
1. Identify the main complaint categories from negative reviews
2. Determine the root cause of each complaint
3. Rank complaints by frequency and severity
4. Extract representative review quotes
5. Classify each complaint as either a genuine PRODUCT DEFECT (hardware/software issue with the
   TV itself, e.g. dead pixels, laggy UI, weak speakers) or a PURCHASE EXPERIENCE issue (anything
   about buying, account setup/login, delivery, installation, or pickup that is NOT a flaw in the
   TV itself). This separation matters because product issues drive engineering/roadmap decisions
   while purchase experience issues drive logistics/CX decisions.

Return structured JSON only. Be specific and actionable in your analysis."""


class ComplaintAnalysisAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="ComplaintAnalysisAgent",
            model=settings.model_sonnet,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.2,
        )

    def analyze(
        self,
        reviews: list[Review],
        retriever: ReviewRetriever,
        result: VOCAnalysisResult,
    ) -> VOCAnalysisResult:
        self.log("Analyzing customer complaints (Task 1)...")

        negative_reviews = [
            r for r in reviews
            if not r.is_duplicate and not r.is_short and r.rating <= 3
        ]
        self.log(f"Found {len(negative_reviews)} negative/neutral reviews")

        # Get additional evidence via RAG
        rag_complaints = retriever.retrieve(
            "product defects problems issues complaints disappointments",
            top_k=20,
        )
        complaint_pool = list({r.review_id: r for r in negative_reviews + rag_complaints}.values())

        context = retriever.format_for_context(complaint_pool[:25], max_chars=8000)

        prompt = f"""Analyze the following Samsung TV reviews to identify the top customer complaints.

Reviews (total pool: {len(complaint_pool)} negative/neutral reviews):
{context}

Product: Samsung 50" Crystal UHD U7900F (UN50U7900FFXZA)
Total reviews analyzed: {len([r for r in reviews if not r.is_duplicate])}

Identify the TOP 8 complaint categories. For each, provide:
{{
  "complaints": [
    {{
      "rank": 1,
      "category": "category name",
      "aspect": "picture_quality|sound|smart_tv|price|installation|reliability|design|gaming|connectivity|remote",
      "issue_type": "product_defect|purchase_experience",
      "frequency": <estimated count>,
      "frequency_pct": <percentage of negative reviews>,
      "root_cause": "specific technical or experiential root cause",
      "representative_reviews": ["quote 1 from actual reviews above", "quote 2", "quote 3"]
    }}
  ]
}}

Focus on actionable, specific complaints. Rank by frequency × severity."""

        try:
            data = self.call_json(prompt, max_tokens=4096)
            complaints_raw = data.get("complaints", data) if isinstance(data, dict) else data
            for item in complaints_raw:
                result.complaints.append(
                    ComplaintItem(
                        rank=item.get("rank", 0),
                        category=item.get("category", ""),
                        aspect=item.get("aspect", "other"),
                        frequency=item.get("frequency", 0),
                        frequency_pct=item.get("frequency_pct", 0.0),
                        root_cause=item.get("root_cause", ""),
                        representative_reviews=item.get("representative_reviews", []),
                        issue_type=item.get("issue_type", "product_defect"),
                    )
                )
            self.log(f"Identified {len(result.complaints)} complaint categories")
        except Exception as e:
            self.log(f"[red]Complaint analysis failed: {e}")

        return result
