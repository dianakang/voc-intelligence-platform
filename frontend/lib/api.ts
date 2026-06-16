const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export interface JobStatus {
  job_id: string;
  status: "pending" | "running" | "done" | "error";
  progress_pct: number;
  current_step: string;
  agent_statuses: Record<string, string>;
  error?: string;
}

export interface VOCResult {
  product_id: string;
  model: string;
  analysis_date: string;
  total_reviews: number;
  avg_rating: number;
  complaints: Complaint[];
  satisfaction_drivers: SatisfactionDriver[];
  improvement_points: ImprovementPoint[];
  marketing_recommendations: MarketingRecommendation | null;
  positioning_analysis: PositioningAnalysis | null;
  contradictions: ContradictionCase[];
  importance_matrix: ImportanceItem[];
  expectation_gaps: ExpectationGapItem[];
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

export interface MarketingRecommendation {
  current_perception: string;
  actual_value_drivers: string[];
  new_message_proposals: string[];
  messages_to_avoid: string[];
  evidence: string[];
}

export interface PositioningAnalysis {
  samsung_strengths: string[];
  samsung_weaknesses: string[];
  competitive_advantages: string[];
  competitive_threats: string[];
  competitors: CompetitorData[];
  positioning_recommendation: string;
}

export interface CompetitorData {
  name: string;
  model: string;
  price_range: string;
  picture_quality: string;
  sound_quality: string;
  ux: string;
  smart_features: string;
  strengths: string[];
  weaknesses: string[];
}

export interface ContradictionCase {
  review_id: string;
  rating: number;
  contradiction_type: "type_a" | "type_b";
  positive_elements: string[];
  negative_elements: string[];
  review_text: string;
  implication: string;
}

export interface ImportanceItem {
  issue: string;
  frequency: number;
  frequency_pct: number;
  impact: string;
  category: string;
  business_risk: string;
  representative_reviews: string[];
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
  startAnalysis: (modelCode: string, maxReviews: number) =>
    fetchAPI<{ job_id: string; status: string }>("/analysis/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_code: modelCode, max_reviews: maxReviews }),
    }),

  getStatus: (jobId: string) => fetchAPI<JobStatus>(`/analysis/status/${jobId}`),

  getResult: (jobId: string) => fetchAPI<VOCResult>(`/analysis/result/${jobId}`),

  listReports: () => fetchAPI<{ filename: string; model: string; analysis_date: string; total_reviews: number; avg_rating: number }[]>("/reports/list"),

  getReport: (filename: string) => fetchAPI<VOCResult>(`/reports/${filename}`),

  getProductSpec: (modelCode: string) => fetchAPI<Record<string, unknown>>(`/product/spec/${modelCode}`),

  getSampleReviews: (modelCode: string, limit = 10) =>
    fetchAPI<unknown[]>(`/reviews/sample/${modelCode}?limit=${limit}`),

  health: () => fetchAPI<{ status: string }>("/health"),
};
