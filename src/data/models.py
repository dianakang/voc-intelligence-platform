from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class Sentiment(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class Priority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Aspect(str, Enum):
    PICTURE_QUALITY = "picture_quality"
    SOUND = "sound"
    SMART_TV = "smart_tv"
    PRICE = "price"
    INSTALLATION = "installation"
    RELIABILITY = "reliability"
    DESIGN = "design"
    GAMING = "gaming"
    CONNECTIVITY = "connectivity"
    REMOTE = "remote"
    OTHER = "other"


class Review(BaseModel):
    review_id: str
    product_id: str
    model: str
    rating: float = Field(ge=1, le=5)
    title: Optional[str] = None
    text: str
    date: Optional[str] = None
    helpful_votes: int = 0
    verified_purchase: bool = False
    is_duplicate: bool = False
    is_short: bool = False

    # Enriched fields (filled during analysis)
    aspects: list[Aspect] = Field(default_factory=list)
    aspect_sentiments: dict[str, str] = Field(default_factory=dict)
    overall_sentiment: Optional[Sentiment] = None
    has_contradiction: bool = False
    contradiction_type: Optional[str] = None
    complaint_categories: list[str] = Field(default_factory=list)
    satisfaction_factors: list[str] = Field(default_factory=list)
    expectation_keywords: list[str] = Field(default_factory=list)
    experience_keywords: list[str] = Field(default_factory=list)
    cleaned_text: Optional[str] = None

    class Config:
        use_enum_values = True


class SpecGroup(BaseModel):
    group_name: str
    items: dict[str, str] = Field(default_factory=dict)


class CompetitorSpec(BaseModel):
    """Schema for both the hardcoded COMPETITOR_SPECS fallback and a live,
    search-grounded fetch (see src/data/competitor_spec_fetcher.py) — kept as
    a single source of truth so the prompt, the LLM-response validator, and
    the on-disk cache file all agree on the same shape."""

    model: str
    price_usd: float
    display_type: str
    panel: str
    refresh_rate: str
    local_dimming: str
    hdr: list[str] = Field(default_factory=list)
    audio_power: str
    dolby_atmos: bool
    os: str
    hdmi: str
    vrr: str
    gaming_input_lag: str
    wifi: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    fetched_at: str = ""


class ProductSpec(BaseModel):
    product_name: str
    model: str
    category: str
    screen_size: str
    series: str
    display: dict = Field(default_factory=dict)
    resolution: dict = Field(default_factory=dict)
    hdr: dict = Field(default_factory=dict)
    smart_tv: dict = Field(default_factory=dict)
    gaming: dict = Field(default_factory=dict)
    audio: dict = Field(default_factory=dict)
    connectivity: dict = Field(default_factory=dict)
    design: dict = Field(default_factory=dict)
    energy: dict = Field(default_factory=dict)
    other: dict = Field(default_factory=dict)

    # Full-fidelity data straight from the spec source(s) below, for grounding
    # LLM prompts without lossy remapping into the category dicts above.
    raw_spec_groups: list[SpecGroup] = Field(default_factory=list)
    spec_highlights: list[str] = Field(default_factory=list)
    # "pdf+live_scrape" | "pdf+cache" | "pdf_only" | "live_scrape" | "cache" | "hardcoded_fallback"
    spec_source: str = "hardcoded_fallback"


class PageSnapshot(BaseModel):
    url: str
    fetched_at: str
    status_code: int
    html_path: str
    title: Optional[str] = None
    model_code: str
    spec_source: str = "live_scrape"


class ComplaintItem(BaseModel):
    rank: int
    category: str
    frequency: int
    frequency_pct: float
    root_cause: str
    representative_reviews: list[str]
    aspect: str
    issue_type: str = "product_defect"  # "product_defect" | "purchase_experience"


class SatisfactionDriver(BaseModel):
    rank: int
    factor: str
    positive_rate: float
    mention_count: int
    representative_reviews: list[str]
    aspect: str


class ImprovementPoint(BaseModel):
    area: str
    expected_effect: str
    priority: Priority
    frequency: int
    impact_score: float
    supporting_evidence: list[str]


class ContradictionCase(BaseModel):
    review_id: str
    rating: float
    contradiction_type: str  # "type_a" or "type_b"
    # "hidden_complaint" (type_a) | "accidental_low_rating" | "service_failure_with_product_praise" |
    # "non_product_issue" (type_b) — see SYSTEM_PROMPT in contradiction_analysis.py for definitions
    mismatch_category: str = ""
    positive_elements: list[str]
    negative_elements: list[str]
    review_text: str
    implication: str
    # Who should act on this case, derived from mismatch_category rather than the star rating
    route_to: str = ""  # "product_engineering" | "cx_fulfillment_warranty" | "marketing_cs_followup" | "no_action_needed"
    # Whether this review's rating/text should count as evidence of a product defect elsewhere in
    # the report (e.g. product_defect frequency, importance matrix) — False for cases where the
    # text's dissatisfaction is about shipping/support/seller, not the TV itself.
    counts_as_product_issue: bool = True
    # Ready-to-post public reply that acknowledges the rating/text mismatch rather
    # than reacting to the star rating alone (e.g. not "thanks for 5 stars" on a
    # review that's actually a complaint).
    suggested_public_response: str = ""


class ImportanceItem(BaseModel):
    issue: str
    frequency: int
    frequency_pct: float
    impact: str  # "high" | "low"
    category: str  # "high_freq_low_impact" | "low_freq_high_impact"
    business_risk: str
    representative_reviews: list[str]
    issue_type: str = "product_defect"  # "product_defect" | "purchase_experience" — who owns the fix
    recommended_action: str = ""  # concrete next step, synthesized from category + issue_type + business_risk + any linked gap/CX action below
    linked_expectation_gap: str = ""  # matching ExpectationGapItem.dimension, if this issue is also a tracked expectation gap
    linked_cx_action: str = ""  # matching CXActionItem.title, if a support mitigation already exists for this issue
    priority_rank: int = 0  # 1 = fix first, assigned holistically across all issues — not derived from the quadrant alone


class CompetitorData(BaseModel):
    name: str
    model: str
    price_range: str
    picture_quality: str
    sound_quality: str
    ux: str
    smart_features: str
    strengths: list[str]
    weaknesses: list[str]


class PositioningAttribute(BaseModel):
    attribute: str
    samsung_assessment: str  # "win" | "lose" | "mixed" | "neutral"
    mention_volume: str  # "high" | "medium" | "low"
    sentiment_score: float  # -1.0 (very negative) to 1.0 (very positive)
    business_impact: str  # "purchase_driver" | "purchase_barrier" | "upsell_opportunity" | "trust_risk" | "neutral"
    vs_competitor_note: str


class PositioningAnalysis(BaseModel):
    samsung_strengths: list[str]
    samsung_weaknesses: list[str]
    competitive_advantages: list[str]
    competitive_threats: list[str]
    competitors: list[CompetitorData]
    positioning_recommendation: str

    # Quantified positioning map (volume/sentiment/gap/business impact per attribute)
    # and the 4-box executive summary, instead of a flat strengths/weaknesses list.
    attribute_map: list[PositioningAttribute] = Field(default_factory=list)
    defend: list[str] = Field(default_factory=list)
    differentiate: list[str] = Field(default_factory=list)
    fix: list[str] = Field(default_factory=list)
    monitor: list[str] = Field(default_factory=list)


class ExpectationGapItem(BaseModel):
    dimension: str
    expectation: str
    actual_experience: str
    gap_severity: str  # "high" | "medium" | "low"
    gap_description: str
    recommended_action: str
    supporting_reviews: list[str]


class MarketingRecommendation(BaseModel):
    current_perception: str
    actual_value_drivers: list[str]
    new_message_proposals: list[str]
    messages_to_avoid: list[str]
    evidence: list[str]


class SegmentInsight(BaseModel):
    segment: str
    size_estimate: int
    key_positive_factors: list[str]
    key_pain_points: list[str]
    expectation_gap: str
    business_implication: str
    recommended_action: str
    evidence: list[str]


class SegmentDivergenceAnalysis(BaseModel):
    segment_insights: list[SegmentInsight]
    emerging_risks: list[str]
    emerging_opportunities: list[str]
    priority_actions: list[str]
    marketing_message_by_segment: list[str]


class CXActionItem(BaseModel):
    action_type: str  # "faq" | "support_script" | "proactive_notice" | "install_guide"
    title: str
    content: str
    related_issue: str
    issue_type: str  # "product_defect" | "purchase_experience"
    priority: str  # "high" | "medium" | "low"


class VOCAnalysisResult(BaseModel):
    product_id: str
    model: str
    analysis_date: str
    total_reviews: int  # size of the sample actually analyzed
    total_reviews_available: int = 0  # real population size discovered during scraping (0 = unknown)
    avg_rating: float

    # Task outputs
    complaints: list[ComplaintItem] = Field(default_factory=list)
    satisfaction_drivers: list[SatisfactionDriver] = Field(default_factory=list)
    improvement_points: list[ImprovementPoint] = Field(default_factory=list)
    marketing_recommendations: Optional[MarketingRecommendation] = None
    positioning_analysis: Optional[PositioningAnalysis] = None
    segment_divergence_analysis: Optional[SegmentDivergenceAnalysis] = None
    contradictions: list[ContradictionCase] = Field(default_factory=list)
    importance_matrix: list[ImportanceItem] = Field(default_factory=list)
    expectation_gaps: list[ExpectationGapItem] = Field(default_factory=list)
    cx_actions: list[CXActionItem] = Field(default_factory=list)

    # Sentiment distribution
    sentiment_distribution: dict[str, int] = Field(default_factory=dict)
    aspect_sentiment_summary: dict[str, dict] = Field(default_factory=dict)

    # Executive summary
    executive_summary: str = ""
    key_insights: list[str] = Field(default_factory=list)
