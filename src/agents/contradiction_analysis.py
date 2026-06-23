"""Task 6: Rating-Review Contradiction Analysis (Type A: 5★ with complaint, Type B: 1★ with praise)."""
from __future__ import annotations

from src.agents.base import BaseAgent
from src.config import settings
from src.data.models import ContradictionCase, Review, VOCAnalysisResult
from src.rag.retriever import ReviewRetriever

SYSTEM_PROMPT = """You are an expert in behavioral economics and consumer psychology analyzing
consumer product reviews. Your task is to detect contradictions between a review's star rating and
the actual content of the review.

Type A contradiction: High rating (4-5 stars) BUT the text contains significant complaints,
disappointments, or negative statements about the product.

Type B contradiction: Low rating (1-2 stars) BUT the text praises the product itself and
the dissatisfaction is directed at non-product factors (shipping, warranty, seller, etc.).

These contradictions reveal important insights about customer psychology, satisfaction thresholds,
and product vs. service quality gaps. The star rating alone is unreliable evidence — the review text
is the real signal — so every case must be classified into one specific mismatch_category, not left
as free-text observation:

- "hidden_complaint" (type_a only): the product itself has a real flaw the customer is tolerating
  despite a high rating. route_to "product_engineering", counts_as_product_issue true.
- "accidental_low_rating" (type_b): the text is wholly positive with no real complaint about anything —
  the low rating looks like a misclick, a misunderstanding of the star scale, or unrelated frustration
  vented at the wrong target. route_to "marketing_cs_followup", counts_as_product_issue false.
- "service_failure_with_product_praise" (type_b): the text explicitly praises the TV itself but blames
  a specific service failure (late/damaged delivery, denied warranty claim, bad support interaction,
  seller issue). route_to "cx_fulfillment_warranty", counts_as_product_issue false.
- "non_product_issue" (type_b): dissatisfaction is about something non-product (price, account/login,
  return policy, etc.) without a clear, explicit statement that the TV itself works well.
  route_to "cx_fulfillment_warranty", counts_as_product_issue false.

For each case, also draft a ready-to-post public reply that acknowledges the mismatch instead of
reacting to the star rating alone:
- hidden_complaint: respond to the complaint itself, not the stars — do not thank the customer for
  "5 stars" when the text describes a real problem.
- accidental_low_rating / service_failure_with_product_praise / non_product_issue: thank the customer
  for the positive product feedback, note that the rating shown is low, and invite them to update it
  if that was a mistake — this both surfaces the mismatch to other shoppers and gives the reviewer a
  path to correct it.
Internally, every case should be tagged for human investigation of the mismatch rather than taken
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
        self.log(f"Detecting rating-review contradictions across {len(reviews)} reviews (Task 6)...")

        # `reviews` here is typically the FULL fetched population, not just the analyzed sample —
        # it usually hasn't been through the cleaning step, so is_duplicate/is_short are unset.
        # Guard against noise from very short reviews with an explicit word-count check instead.
        candidates = [
            r for r in reviews
            if not r.is_duplicate and len((r.cleaned_text or r.text).split()) >= 5
        ]
        flagged = self._flag_contradictions(candidates)

        if not flagged:
            self.log("No contradictions detected in initial pass")
            return result

        # Deep analysis of flagged reviews. Type B (low rating + praise) is rare — at full-population
        # scale, common Type A candidates ("but"/"however" style phrasing) can outnumber it by 10-50x,
        # so a plain flagged[:N] slice would routinely crowd Type B out of the LLM's context entirely.
        # Give Type B priority and fill the remaining budget with Type A.
        type_a = [r for r in flagged if r.rating >= 4]
        type_b = [r for r in flagged if r.rating <= 2]
        CONTEXT_CAP = 20
        type_b_pool = type_b[:10]
        type_a_pool = type_a[: max(CONTEXT_CAP - len(type_b_pool), 5)]
        context_pool = type_b_pool + type_a_pool
        context = retriever.format_for_context(context_pool, max_chars=6000)

        prompt = f"""Analyze these {len(context_pool)} TV reviews that show rating-content contradictions
(out of {len(flagged)} candidates found across {len(reviews)} reviews scanned).

Type A (high rating + complaint): {len(type_a_pool)} reviews in context ({len(type_a)} total found)
Type B (low rating + praise): {len(type_b_pool)} reviews in context ({len(type_b)} total found)

Reviews:
{context}

For each contradiction, provide deep analysis. Return:
{{
  "contradictions": [
    {{
      "review_id": "SAMPLE_UN50U7900FFXZA_XXXX",
      "rating": 5,
      "contradiction_type": "type_a",
      "mismatch_category": "hidden_complaint|accidental_low_rating|service_failure_with_product_praise|non_product_issue",
      "positive_elements": ["element praised in text"],
      "negative_elements": ["complaint buried in text"],
      "review_text": "brief quote from review",
      "implication": "what this reveals about customer psychology or product/service gap",
      "route_to": "product_engineering|cx_fulfillment_warranty|marketing_cs_followup|no_action_needed",
      "counts_as_product_issue": true,
      "suggested_public_response": "ready-to-post company reply, 2-3 sentences, addressing the mismatch per the rules above"
    }}
  ],
  "type_a_pattern": "common pattern in 5-star reviews with hidden complaints",
  "type_b_pattern": "common pattern in 1-star reviews with product praise",
  "key_insight": "strategic insight from contradiction analysis"
}}"""

        try:
            data = self.call_json(prompt, max_tokens=6000)
            contradictions_raw = data.get("contradictions", []) if isinstance(data, dict) else []

            for item in contradictions_raw:
                result.contradictions.append(
                    ContradictionCase(
                        review_id=item.get("review_id", ""),
                        rating=float(item.get("rating", 0)),
                        contradiction_type=item.get("contradiction_type", "type_a"),
                        mismatch_category=item.get("mismatch_category", ""),
                        positive_elements=item.get("positive_elements", []),
                        negative_elements=item.get("negative_elements", []),
                        review_text=item.get("review_text", ""),
                        implication=item.get("implication", ""),
                        route_to=item.get("route_to", ""),
                        counts_as_product_issue=item.get("counts_as_product_issue", True),
                        suggested_public_response=item.get("suggested_public_response", ""),
                    )
                )

            self.log(
                f"Found {len(result.contradictions)} contradictions from {len(context_pool)} candidates "
                f"analyzed (heuristic scan flagged {len(type_a)} Type A, {len(type_b)} Type B total)"
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
