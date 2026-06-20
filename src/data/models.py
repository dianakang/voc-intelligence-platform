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


class ComplaintItem(BaseModel):
    rank: int
    category: str
    frequency: int
    frequency_pct: float
    root_cause: str
    representative_reviews: list[str]
    aspect: str


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
    positive_elements: list[str]
    negative_elements: list[str]
    review_text: str
    implication: str


class ImportanceItem(BaseModel):
    issue: str
    frequency: int
    frequency_pct: float
    impact: str  # "high" | "low"
    category: str  # "high_freq_low_impact" | "low_freq_high_impact"
    business_risk: str
    representative_reviews: list[str]


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


class PositioningAnalysis(BaseModel):
    samsung_strengths: list[str]
    samsung_weaknesses: list[str]
    competitive_advantages: list[str]
    competitive_threats: list[str]
    competitors: list[CompetitorData]
    positioning_recommendation: str


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


class VOCAnalysisResult(BaseModel):
    product_id: str
    model: str
    analysis_date: str
    total_reviews: int
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

    # Sentiment distribution
    sentiment_distribution: dict[str, int] = Field(default_factory=dict)
    aspect_sentiment_summary: dict[str, dict] = Field(default_factory=dict)

    # Executive summary
    executive_summary: str = ""
    key_insights: list[str] = Field(default_factory=list)
