const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export interface JobStatus {
  job_id: string;
  status: "pending" | "running" | "done" | "error";
  progress_pct: number;
  current_step: string;
  agent_statuses: Record<string, string>;
  error?: string;
}

export interface ReportMeta {
  filename: string;
  model: string;
  analysis_date: string;
  total_reviews: number;
  avg_rating: number;
  category: string;
  product_name: string;
}

export interface VOCResult {
  product_id: string;
  model: string;
  analysis_date: string;
  total_reviews: number;
  total_reviews_available: number;
  avg_rating: number;
  complaints: Complaint[];
  satisfaction_drivers: SatisfactionDriver[];
  improvement_points: ImprovementPoint[];
  marketing_recommendations: MarketingRecommendation | null;
  positioning_analysis: PositioningAnalysis | null;
  segment_divergence_analysis: SegmentDivergenceAnalysis | null;
  contradictions: ContradictionCase[];
  importance_matrix: ImportanceItem[];
  expectation_gaps: ExpectationGapItem[];
  cx_actions: CXActionItem[];
  sentiment_distribution: Record<string, number>;
  aspect_sentiment_summary: Record<string, AspectSentiment>;
  executive_summary: string;
  key_insights: string[];
}

export interface Complaint {
  rank: number;
  category: string;
  aspect: string;
  frequency: number;
  frequency_pct: number;
  root_cause: string;
  representative_reviews: string[];
  issue_type: "product_defect" | "purchase_experience";
}

export interface CXActionItem {
  action_type: "faq" | "support_script" | "proactive_notice" | "install_guide";
  title: string;
  content: string;
  related_issue: string;
  issue_type: "product_defect" | "purchase_experience";
  priority: "high" | "medium" | "low";
}

export interface SatisfactionDriver {
  rank: number;
  factor: string;
  aspect: string;
  positive_rate: number;
  mention_count: number;
  representative_reviews: string[];
}

export interface ImprovementPoint {
  area: string;
  expected_effect: string;
  priority: "high" | "medium" | "low";
  frequency: number;
  impact_score: number;
  supporting_evidence: string[];
}

export interface TargetAudienceProfile {
  persona_name: string;
  demographic_profile: string;
  psychographic_traits: string[];
  why_product_fits: string;
  recommended_channels: string[];
  evidence: string[];
}

export interface MarketingRecommendation {
  current_perception: string;
  actual_value_drivers: string[];
  new_message_proposals: string[];
  target_audience: TargetAudienceProfile[];
  evidence: string[];
}

export interface PositioningAttribute {
  attribute: string;
  samsung_assessment: "win" | "lose" | "mixed" | "neutral";
  mention_volume: "high" | "medium" | "low";
  sentiment_score: number;
  business_impact: "purchase_driver" | "purchase_barrier" | "upsell_opportunity" | "trust_risk" | "neutral";
  vs_competitor_note: string;
}

export interface PositioningAnalysis {
  samsung_strengths: string[];
  samsung_weaknesses: string[];
  competitive_advantages: string[];
  competitive_threats: string[];
  competitors: CompetitorData[];
  positioning_recommendation: string;
  attribute_map: PositioningAttribute[];
  defend: string[];
  differentiate: string[];
  fix: string[];
  monitor: string[];
}

export interface CompetitorData {
  name: string;
  model: string;
  price_range: string;
  ux: string;
  key_attributes: Record<string, string>;
  strengths: string[];
  weaknesses: string[];
}

export interface ContradictionCase {
  review_id: string;
  rating: number;
  contradiction_type: "type_a" | "type_b";
  mismatch_category: string;
  positive_elements: string[];
  negative_elements: string[];
  review_text: string;
  implication: string;
  route_to: string;
  counts_as_product_issue: boolean;
  suggested_public_response: string;
}

export interface ImportanceItem {
  issue: string;
  frequency: number;
  frequency_pct: number;
  impact: string;
  category: string;
  business_risk: string;
  representative_reviews: string[];
  issue_type: string;
  recommended_action: string;
  linked_expectation_gap: string;
  linked_cx_action: string;
  priority_rank: number;
}

export interface ExpectationGapItem {
  dimension: string;
  expectation: string;
  actual_experience: string;
  gap_severity: "high" | "medium" | "low";
  gap_description: string;
  recommended_action: string;
  supporting_reviews: string[];
}

export interface SegmentInsight {
  segment: string;
  size_estimate: number;
  key_positive_factors: string[];
  key_pain_points: string[];
  expectation_gap: string;
  business_implication: string;
  recommended_action: string;
  evidence: string[];
}

export interface SegmentDivergenceAnalysis {
  segment_insights: SegmentInsight[];
  emerging_risks: string[];
  emerging_opportunities: string[];
  priority_actions: string[];
  marketing_message_by_segment: string[];
}

export interface AspectSentiment {
  total_mentions: number;
  positive: number;
  negative: number;
  neutral: number;
  positive_rate: number;
  negative_rate: number;
  insight?: string;
}

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) throw new Error(`API error ${res.status}: ${await res.text()}`);
  return res.json();
}

export const api = {
  startAnalysis: (maxReviews: number, url: string, skipIfCached: boolean) =>
    fetchAPI<{ job_id: string; status: string }>("/analysis/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ max_reviews: maxReviews, url, skip_if_cached: skipIfCached }),
    }),

  getStatus: (jobId: string) => fetchAPI<JobStatus>(`/analysis/status/${jobId}`),

  getResult: (jobId: string) => fetchAPI<VOCResult>(`/analysis/result/${jobId}`),

  listReports: () => fetchAPI<ReportMeta[]>("/reports/list"),

  getReport: (filename: string) => fetchAPI<VOCResult>(`/reports/${filename}`),

  getProductSpec: (modelCode: string) => fetchAPI<Record<string, unknown>>(`/product/spec/${modelCode}`),

  getSampleReviews: (modelCode: string, limit = 10) =>
    fetchAPI<unknown[]>(`/reviews/sample/${modelCode}?limit=${limit}`),

  health: () => fetchAPI<{ status: string }>("/health"),
};
