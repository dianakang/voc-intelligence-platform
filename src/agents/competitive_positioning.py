"""Task 5: Competitive Positioning Analysis.

Competitors are discovered and fetched per analyzed product (any category), via
`voc refresh-competitors {model_code}` (src/data/competitor_spec_fetcher.py),
cached at data/raw/{model_code}/competitors.json. That's a deliberate offline
step, not run automatically here — analyze() simply reads the cache via
get_competitor_specs(model_code) and skips gracefully (no positioning_analysis)
if it's empty, rather than blocking every `voc run` on extra web-search-grounded
LLM calls or fabricating a comparison with no real data.
"""
from __future__ import annotations

from typing import Optional

from src.agents.base import BaseAgent
from src.config import settings
from src.data.models import CompetitorData, PositioningAnalysis, PositioningAttribute, ProductSpec, Review, VOCAnalysisResult
from src.data.spec_extractor import get_competitor_specs
from src.rag.retriever import ReviewRetriever

SYSTEM_PROMPT = """You are a competitive intelligence analyst for an internal Marketing, Product
Marketing, CX, and Product team — not an outside reviewer. Your job is to turn raw customer voice
into prioritization and decision support, not just observations.

A flat list like "the app is laggy" is not useful on its own. For every attribute you assess,
you must answer:
1. How many customers mention it (mention_volume: high/medium/low) — ground this in the real
   frequency_pct / positive_rate numbers provided below, don't invent percentages.
2. How strongly do they feel about it (sentiment_score: -1.0 to +1.0, not just direction)?
3. How does Samsung compare to competitors on this specific attribute (samsung_assessment:
   win/lose/mixed/neutral, plus a one-line vs_competitor_note)?
4. Does this attribute actually drive or block purchase decisions, or is it just mentioned
   (business_impact: purchase_driver/purchase_barrier/upsell_opportunity/trust_risk/neutral)?
   A complaint mentioned often but never tied to returns/regret is not the same as one customers
   say almost made them return the product.

Then roll everything up into 4 executive boxes — the format Product Marketing, CX, and leadership
actually consume:
- Defend: attributes Samsung already wins on and should protect/keep messaging
- Differentiate: attributes Samsung wins on that aren't yet leveraged in marketing
- Fix: attributes Samsung loses on that are purchase barriers or trust risks
- Monitor: lower-volume but high-severity risks worth watching, not yet acting on

Return structured JSON only."""


def _describe_competitor(spec: dict) -> str:
    """Render a competitor's spec dict (see CompetitorSpec) into the prompt's one-line summary."""
    key_specs = spec.get("key_specs", {})
    specs_str = ", ".join(f"{k}: {v}" for k, v in key_specs.items()) or "N/A"
    return f"${spec.get('price_usd', 'N/A')} — {specs_str}"


def _describe_samsung_spec(product_spec: Optional[ProductSpec]) -> str:
    """Render the analyzed Samsung product's own spec highlights for the prompt,
    from whatever real spec data was scraped (no fixed field names — varies by category)."""
    if not product_spec:
        return "(no spec data available)"
    lines = []
    price = product_spec.other.get("price_usd")
    if price:
        lines.append(f"- Price: ${price}")
    for group in product_spec.raw_spec_groups[:6]:
        items = ", ".join(f"{k}: {v}" for k, v in list(group.items.items())[:4])
        if items:
            lines.append(f"- {group.group_name}: {items}")
    return "\n".join(lines) if lines else "(no spec data available)"


class CompetitivePositioningAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="CompetitivePositioningAgent",
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
        model_code = result.model
        comp_specs = get_competitor_specs(model_code)
        if not comp_specs:
            self.log(
                f"[yellow]Skipping competitive positioning — no cached competitor data for "
                f"{model_code}. Run `voc refresh-competitors {model_code}` first."
            )
            return result

        self.log("Analyzing competitive positioning (Task 5)...")

        competitor_names = ", ".join(comp_specs.keys())
        # Get reviews mentioning competitors or comparisons
        competitor_reviews = retriever.retrieve(
            f"compared {competitor_names} better worse alternative cheaper",
            top_k=10,
        )
        value_reviews = retriever.retrieve(
            "price value money worth cheap expensive premium",
            top_k=8,
        )

        pool = list({r.review_id: r for r in competitor_reviews + value_reviews}.values())[:15]
        context = retriever.format_for_context(pool, max_chars=5000)

        complaints_summary = "\n".join(
            f"- {c.category} ({c.frequency_pct:.0f}% of negative reviews, issue_type={c.issue_type}): {c.root_cause}"
            for c in result.complaints[:8]
        )
        strengths_summary = "\n".join(
            f"- {s.factor} ({s.positive_rate:.0f}% positive, {s.mention_count} mentions)"
            for s in result.satisfaction_drivers[:6]
        )

        product_label = product_spec.product_name if product_spec and product_spec.product_name else model_code

        prompt = f"""Analyze {product_label} competitive positioning vs. {competitor_names}.

SAMSUNG PRODUCT SPECS:
{_describe_samsung_spec(product_spec)}

COMPETITOR OVERVIEW:
{chr(10).join(f"{name}: {_describe_competitor(spec)}" for name, spec in comp_specs.items())}

SAMSUNG CUSTOMER STRENGTHS (real mention/sentiment numbers from VOC pipeline — use these, don't invent new ones):
{strengths_summary}

SAMSUNG CUSTOMER COMPLAINTS (real frequency numbers from VOC pipeline — use these, don't invent new ones):
{complaints_summary}

CUSTOMER COMPARISON MENTIONS:
{context}

Generate strategic positioning analysis. Use the real frequency_pct/positive_rate numbers above to
set mention_volume ("high" if roughly >=25%, "medium" if 10-25%, "low" if <10%) and sentiment_score
for each attribute in attribute_map — do not output a flat strengths/weaknesses list without these.
{{
  "samsung_strengths": ["strength 1", "strength 2", ...],
  "samsung_weaknesses": ["weakness 1", "weakness 2", ...],
  "competitive_advantages": ["specific advantage vs competitors"],
  "competitive_threats": ["specific threat from competitors"],
  "competitors": [
    {{
      "name": "competitor name from the overview above",
      "model": "competitor model from the overview above",
      "price_range": "$X-Y",
      "ux": "assessment",
      "key_attributes": {{"attribute name appropriate to this product category": "assessment vs Samsung", "...": "..."}},
      "strengths": ["vs Samsung strength"],
      "weaknesses": ["vs Samsung weakness"]
    }}
  ],
  "attribute_map": [
    {{
      "attribute": "an attribute genuinely relevant to this product category",
      "samsung_assessment": "win|lose|mixed|neutral",
      "mention_volume": "high|medium|low",
      "sentiment_score": 0.82,
      "business_impact": "purchase_driver|purchase_barrier|upsell_opportunity|trust_risk|neutral",
      "vs_competitor_note": "one-line comparison vs the competitors above on this specific attribute"
    }}
  ],
  "defend": ["attribute Samsung already wins on and should protect"],
  "differentiate": ["attribute Samsung wins on but underleverages in marketing"],
  "fix": ["attribute Samsung loses on that is a purchase barrier or trust risk"],
  "monitor": ["lower-volume but high-severity risk worth watching"],
  "positioning_recommendation": "strategic recommendation for Samsung marketing and product team"
}}"""

        try:
            data = self.call_json(prompt, max_tokens=8192)

            competitors = []
            for comp in data.get("competitors", []):
                competitors.append(
                    CompetitorData(
                        name=comp.get("name", ""),
                        model=comp.get("model", ""),
                        price_range=comp.get("price_range", ""),
                        ux=comp.get("ux", ""),
                        key_attributes=comp.get("key_attributes", {}),
                        strengths=comp.get("strengths", []),
                        weaknesses=comp.get("weaknesses", []),
                    )
                )

            attribute_map = [
                PositioningAttribute(
                    attribute=a.get("attribute", ""),
                    samsung_assessment=a.get("samsung_assessment", "neutral"),
                    mention_volume=a.get("mention_volume", "low"),
                    sentiment_score=float(a.get("sentiment_score", 0.0)),
                    business_impact=a.get("business_impact", "neutral"),
                    vs_competitor_note=a.get("vs_competitor_note", ""),
                )
                for a in data.get("attribute_map", [])
            ]

            result.positioning_analysis = PositioningAnalysis(
                samsung_strengths=data.get("samsung_strengths", []),
                samsung_weaknesses=data.get("samsung_weaknesses", []),
                competitive_advantages=data.get("competitive_advantages", []),
                competitive_threats=data.get("competitive_threats", []),
                competitors=competitors,
                positioning_recommendation=data.get("positioning_recommendation", ""),
                attribute_map=attribute_map,
                defend=data.get("defend", []),
                differentiate=data.get("differentiate", []),
                fix=data.get("fix", []),
                monitor=data.get("monitor", []),
            )
            self.log(
                f"Competitive analysis complete: {len(competitors)} competitors, "
                f"{len(attribute_map)} attributes mapped"
            )
        except Exception as e:
            self.log(f"[red]Competitive analysis failed: {e}")

        return result
