"""Task 5: Competitive Positioning Analysis vs. TCL Q6, Hisense A7, LG UT70."""
from __future__ import annotations

from src.agents.base import BaseAgent
from src.config import settings
from src.data.models import CompetitorData, PositioningAnalysis, Review, VOCAnalysisResult
from src.data.spec_extractor import COMPETITOR_SPECS, SAMSUNG_U7900F_SPEC
from src.rag.retriever import ReviewRetriever

SYSTEM_PROMPT = """You are a competitive intelligence analyst for Samsung's TV business.
You analyze Samsung TV customer reviews and compare them against competitor product specifications
and known market positioning to generate strategic competitive insights.

Base your analysis on:
1. Actual customer review evidence (what customers say)
2. Product specification comparisons (factual capability differences)
3. Market positioning and brand perception

Provide actionable competitive strategy recommendations.
Return structured JSON only."""


class CompetitivePositioningAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="CompetitivePositioningAgent",
            model=settings.model_sonnet,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.3,
        )

    def analyze(self, reviews: list[Review], retriever: ReviewRetriever, result: VOCAnalysisResult) -> VOCAnalysisResult:
        self.log("Analyzing competitive positioning (Task 5)...")

        # Get reviews mentioning competitors or comparisons
        competitor_reviews = retriever.retrieve(
            "compared TCL LG Hisense better worse alternative cheaper",
            top_k=10,
        )
        value_reviews = retriever.retrieve(
            "price value money worth cheap expensive premium",
            top_k=8,
        )

        pool = list({r.review_id: r for r in competitor_reviews + value_reviews}.values())[:15]
        context = retriever.format_for_context(pool, max_chars=5000)

        samsung_spec = SAMSUNG_U7900F_SPEC
        comp_specs = COMPETITOR_SPECS

        complaints_summary = "\n".join(
            f"- {c.category}: {c.root_cause}" for c in result.complaints[:6]
        )
        strengths_summary = "\n".join(
            f"- {s.factor}" for s in result.satisfaction_drivers[:4]
        )

        prompt = f"""Analyze Samsung 50" Crystal UHD U7900F competitive positioning vs. TCL Q6, Hisense A7, LG UT70.

SAMSUNG PRODUCT SPECS:
- Price: ${samsung_spec['other']['price_usd']}
- Display: {samsung_spec['display']['type']}
- Audio: {samsung_spec['audio']['output_power']} {samsung_spec['audio']['speakers']}
- OS: {samsung_spec['smart_tv']['os']}
- Gaming: {samsung_spec['gaming']['vrr']}, {samsung_spec['gaming']['input_lag_4k_60hz']} input lag
- HDR: {', '.join(samsung_spec['resolution']['hdr_support'])}
- WiFi: {samsung_spec['connectivity']['wifi']}

COMPETITOR OVERVIEW:
TCL Q6: ${comp_specs['TCL Q6']['price_usd']}, QLED, Google TV, Dolby Vision+Atmos, Full Array LD, WiFi 6
Hisense A7: ${comp_specs['Hisense A7']['price_usd']}, ULED, Dolby Vision+Atmos, VIDAA OS
LG UT70: ${comp_specs['LG UT70']['price_usd']}, IPS panel, webOS, ~9ms input lag, FreeSync

SAMSUNG CUSTOMER STRENGTHS (from VOC):
{strengths_summary}

SAMSUNG CUSTOMER COMPLAINTS (from VOC):
{complaints_summary}

CUSTOMER COMPARISON MENTIONS:
{context}

Generate strategic positioning analysis:
{{
  "samsung_strengths": ["strength 1", "strength 2", ...],
  "samsung_weaknesses": ["weakness 1", "weakness 2", ...],
  "competitive_advantages": ["specific advantage vs competitors"],
  "competitive_threats": ["specific threat from competitors"],
  "competitors": [
    {{
      "name": "TCL Q6",
      "model": "55Q650G",
      "price_range": "$330-380",
      "picture_quality": "assessment",
      "sound_quality": "assessment",
      "ux": "assessment",
      "smart_features": "assessment",
      "strengths": ["vs Samsung strength"],
      "weaknesses": ["vs Samsung weakness"]
    }}
  ],
  "positioning_recommendation": "strategic recommendation for Samsung marketing and product team"
}}"""

        try:
            data = self.call_json(prompt, max_tokens=4096)

            competitors = []
            for comp in data.get("competitors", []):
                competitors.append(
                    CompetitorData(
                        name=comp.get("name", ""),
                        model=comp.get("model", ""),
                        price_range=comp.get("price_range", ""),
                        picture_quality=comp.get("picture_quality", ""),
                        sound_quality=comp.get("sound_quality", ""),
                        ux=comp.get("ux", ""),
                        smart_features=comp.get("smart_features", ""),
                        strengths=comp.get("strengths", []),
                        weaknesses=comp.get("weaknesses", []),
                    )
                )

            result.positioning_analysis = PositioningAnalysis(
                samsung_strengths=data.get("samsung_strengths", []),
                samsung_weaknesses=data.get("samsung_weaknesses", []),
                competitive_advantages=data.get("competitive_advantages", []),
                competitive_threats=data.get("competitive_threats", []),
                competitors=competitors,
                positioning_recommendation=data.get("positioning_recommendation", ""),
            )
            self.log(f"Competitive analysis complete: {len(competitors)} competitors analyzed")
        except Exception as e:
            self.log(f"[red]Competitive analysis failed: {e}")

        return result
