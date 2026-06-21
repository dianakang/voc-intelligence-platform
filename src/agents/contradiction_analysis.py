"""Task 6: Rating-Review Contradiction Analysis (Type A: 5★ with complaint, Type B: 1★ with praise)."""
from __future__ import annotations

from src.agents.base import BaseAgent
from src.config import settings
from src.data.models import ContradictionCase, Review, VOCAnalysisResult
from src.rag.retriever import ReviewRetriever

SYSTEM_PROMPT = """You are an expert in behavioral economics and consumer psychology analyzing
TV product reviews. Your task is to detect contradictions between a review's star rating and
the actual content of the review.

Type A contradiction: High rating (4-5 stars) BUT the text contains significant complaints,
disappointments, or negative statements about the product.

Type B contradiction: Low rating (1-2 stars) BUT the text praises the product itself and
the dissatisfaction is directed at non-product factors (shipping, warranty, seller, etc.).

These contradictions reveal important insights about customer psychology, satisfaction thresholds,
and product vs. service quality gaps.

For each case, also draft a ready-to-post public reply that acknowledges the mismatch instead of
reacting to the star rating alone:
- Type A (high rating, hidden complaint): respond to the complaint itself, not the stars — do not
  thank the customer for "5 stars" when the text describes a real problem.
- Type B (low rating, hidden praise): thank the customer for the positive feedback, note that the
  rating shown is low, and invite them to update it if that was a mistake — this both surfaces the
  mismatch to other shoppers and gives the reviewer a path to correct it.
Internally, both types should be tagged for human investigation of the mismatch rather than taken
at face value — trust the review text for operational decisions, the star rating may be accidental.

Return structured JSON only."""


class ContradictionAnalysisAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="ContradictionAgent",
            model=settings.model_sonnet,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.2,
        )

    def analyze(self, reviews: list[Review], retriever: ReviewRetriever, result: VOCAnalysisResult) -> VOCAnalysisResult:
        self.log("Detecting rating-review contradictions (Task 6)...")

        # Flag contradictions per-review first
        candidates = [r for r in reviews if not r.is_duplicate and not r.is_short]
        flagged = self._flag_contradictions(candidates)

        if not flagged:
            self.log("No contradictions detected in initial pass")
            return result

        # Deep analysis of flagged reviews
        context = retriever.format_for_context(flagged[:15], max_chars=6000)
        type_a = [r for r in flagged if r.rating >= 4]
        type_b = [r for r in flagged if r.rating <= 2]

        prompt = f"""Analyze these {len(flagged)} TV reviews that show rating-content contradictions.

Type A (high rating + complaint): {len(type_a)} reviews
Type B (low rating + praise): {len(type_b)} reviews

Reviews:
{context}

For each contradiction, provide deep analysis. Return:
{{
  "contradictions": [
    {{
      "review_id": "SAMPLE_UN50U7900FFXZA_XXXX",
      "rating": 5,
      "contradiction_type": "type_a",
      "positive_elements": ["element praised in text"],
      "negative_elements": ["complaint buried in text"],
      "review_text": "brief quote from review",
      "implication": "what this reveals about customer psychology or product/service gap",
      "suggested_public_response": "ready-to-post company reply, 2-3 sentences, addressing the mismatch per the rules above"
    }}
  ],
  "type_a_pattern": "common pattern in 5-star reviews with hidden complaints",
  "type_b_pattern": "common pattern in 1-star reviews with product praise",
  "key_insight": "strategic insight from contradiction analysis"
}}"""

        try:
            data = self.call_json(prompt, max_tokens=5000)
            contradictions_raw = data.get("contradictions", []) if isinstance(data, dict) else []

            for item in contradictions_raw:
                result.contradictions.append(
                    ContradictionCase(
                        review_id=item.get("review_id", ""),
                        rating=float(item.get("rating", 0)),
                        contradiction_type=item.get("contradiction_type", "type_a"),
                        positive_elements=item.get("positive_elements", []),
                        negative_elements=item.get("negative_elements", []),
                        review_text=item.get("review_text", ""),
                        implication=item.get("implication", ""),
                        suggested_public_response=item.get("suggested_public_response", ""),
                    )
                )

            self.log(
                f"Found {len(result.contradictions)} contradictions | "
                f"Type A: {len(type_a)}, Type B: {len(type_b)}"
            )
        except Exception as e:
            self.log(f"[red]Contradiction analysis failed: {e}")

        return result

    def _flag_contradictions(self, reviews: list[Review]) -> list[Review]:
        """Heuristic pre-screening for contradiction candidates."""
        negative_markers = [
            "but", "however", "although", "though", "unfortunately", "except",
            "disappointing", "disappointed", "wished", "wish", "could be better",
            "not great", "poor", "weak", "terrible", "bad", "hate", "annoying",
            "problem", "issue", "fix", "broken", "slow", "crash", "freeze",
        ]
        positive_markers = [
            "great", "excellent", "amazing", "perfect", "love", "beautiful",
            "stunning", "impressive", "best", "fantastic", "good quality",
            "works well", "happy", "satisfied",
        ]

        flagged = []
        for r in reviews:
            text_lower = (r.cleaned_text or r.text).lower()

            if r.rating >= 4:
                # Type A: high rating but text has negative markers
                neg_count = sum(1 for m in negative_markers if m in text_lower)
                if neg_count >= 2:
                    r.has_contradiction = True
                    r.contradiction_type = "type_a"
                    flagged.append(r)

            elif r.rating <= 2:
                # Type B: low rating but text has positive markers about the product
                pos_count = sum(1 for m in positive_markers if m in text_lower)
                if pos_count >= 2:
                    r.has_contradiction = True
                    r.contradiction_type = "type_b"
                    flagged.append(r)

        return flagged
