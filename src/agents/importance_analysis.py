"""Task 11: Importance Analysis — frequency vs. business impact, synthesized into an actionable priority list."""
from __future__ import annotations

from typing import Optional

from src.agents.base import BaseAgent
from src.config import settings
from src.data.models import ImportanceItem, ProductSpec, Review, VOCAnalysisResult
from src.rag.retriever import ReviewRetriever

SYSTEM_PROMPT = """You are a product strategy analyst specializing in customer issue prioritization.
Your job is to distinguish between issues that are frequently mentioned but have low business impact,
versus issues that are rarely mentioned but carry high business risk — and then turn that distinction
into a concrete, ranked action plan.

High Frequency / Low Impact: Issues mentioned often but don't significantly affect purchase decisions,
brand loyalty, or repeat sales (e.g., minor UX annoyances, cosmetic preferences).

Low Frequency / High Impact: Issues mentioned rarely but with severe consequences — defects that
cause returns, warranty claims, negative word-of-mouth, or damage to brand reputation
(e.g., dead pixels, power failures, panel defects, complete hardware failures).

The frequency/impact quadrant alone is NOT a fix priority. Two issues in the same quadrant can need
completely different responses: a hardware defect needs an engineering fix; a delivery or account-setup
complaint needs a support script or a PDP copy change. Always ground your recommended action in:
1. the quadrant (frequency x impact),
2. whether it's a product_defect (engineering/QA owns it) or purchase_experience issue (CX/ops/marketing owns it),
3. the business_risk text (what actually breaks if it's ignored),
4. whether a mitigation already exists (a CX action or a tracked expectation gap) — if one does, the
   recommended action is to close the loop on that existing effort, not to invent a new one.

Return structured JSON only."""


class ImportanceAnalysisAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="ImportanceAnalysisAgent",
            model=settings.model_sonnet,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.2,
        )

    def analyze(
        self,
        reviews: list[Review],
        retriever: ReviewRetriever,
        result: VOCAnalysisResult,
        product_spec: Optional[ProductSpec] = None,
    ) -> VOCAnalysisResult:
        self.log("Synthesizing issue priority from frequency/impact + complaints + gaps + CX actions (Task 11)...")

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
            f"- [{c.issue_type}] {c.category} (~{c.frequency} mentions, {c.frequency_pct:.0f}%): {c.root_cause}"
            for c in result.complaints[:8]
        )
        gaps_context = "\n".join(
            f"- {g.dimension} [{g.gap_severity} gap]: {g.gap_description} -> recommended: {g.recommended_action}"
            for g in result.expectation_gaps[:6]
        ) or "(none identified)"
        cx_actions_context = "\n".join(
            f"- [{a.issue_type}] {a.title} (addresses: {a.related_issue}, priority: {a.priority})"
            for a in result.cx_actions[:8]
        ) or "(none generated)"

        all_reviews_context = retriever.format_for_context(
            high_impact_reviews + low_impact_reviews, max_chars=4000
        )

        product_label = product_spec.product_name if product_spec and product_spec.product_name else result.model

        prompt = f"""Classify customer issues for {product_label} by frequency vs. business impact,
then synthesize a recommended fix and priority rank for each, using ALL the signals below — not the
quadrant alone.

Total reviews analyzed: {total}

KNOWN COMPLAINT CATEGORIES (tagged product_defect vs purchase_experience):
{complaints_context}

EXISTING EXPECTATION GAP FINDINGS (already analyzed elsewhere in this pipeline):
{gaps_context}

EXISTING CX ACTIONS (support/FAQ assets already generated for some issues):
{cx_actions_context}

SAMPLE REVIEWS (high/low impact):
{all_reviews_context}

Identify ALL issues and classify them. For each issue:
- issue_type: "product_defect" if it's a defect in the product itself, "purchase_experience" if it's about
  delivery/account/installation/pickup — match against the complaint categories above where possible.
- linked_expectation_gap: the matching dimension name from the expectation gap findings above, or "" if none.
- linked_cx_action: the matching title from the CX actions above, or "" if none.
- recommended_action: leave this as an EMPTY STRING whenever you set linked_expectation_gap or
  linked_cx_action above — the full fix is already written out in full there, and this report shows
  only one or the other, never both, so writing both means duplicating the same recommendation twice.
  Only fill in recommended_action (one concrete next step) when NEITHER link applies, i.e. this is a
  genuinely new issue with no existing mitigation to point to.

Return:
{{
  "importance_matrix": [
    {{
      "issue": "specific issue name",
      "frequency": <estimated count>,
      "frequency_pct": <percentage of all reviews>,
      "impact": "high" or "low",
      "category": "high_freq_low_impact" or "low_freq_high_impact" or "high_freq_high_impact" or "low_freq_low_impact",
      "business_risk": "description of business consequence if unaddressed",
      "representative_reviews": ["quote 1", "quote 2"],
      "issue_type": "product_defect" or "purchase_experience",
      "recommended_action": "concrete next step, grounded in the signals above",
      "linked_expectation_gap": "dimension name or empty string",
      "linked_cx_action": "CX action title or empty string",
      "priority_rank": <integer, 1 = fix first, unique across all issues returned>
    }}
  ]
}}

Include at minimum:
- 3 High Frequency / Low Impact issues
- 3 Low Frequency / High Impact issues
- 2 High Frequency / High Impact issues

Rank priority holistically: a low-frequency/high-impact defect with no existing mitigation should usually
outrank a high-frequency/low-impact annoyance that already has a published CX action."""

        try:
            data = self.call_json(prompt, max_tokens=4096)
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
                        issue_type=item.get("issue_type", "product_defect"),
                        recommended_action=item.get("recommended_action", ""),
                        linked_expectation_gap=item.get("linked_expectation_gap", ""),
                        linked_cx_action=item.get("linked_cx_action", ""),
                        priority_rank=item.get("priority_rank", 0),
                    )
                )
            result.importance_matrix.sort(key=lambda i: i.priority_rank or 999)
            self.log(f"Importance matrix: {len(result.importance_matrix)} issues classified and ranked")
        except Exception as e:
            self.log(f"[red]Importance analysis failed: {e}")

        return result
