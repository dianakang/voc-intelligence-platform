"use client";

import { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { api, VOCResult, ExpectationGapItem, ContradictionCase, ImprovementPoint } from "@/lib/api";
import { SentimentPieChart } from "@/components/charts/SentimentPieChart";
import { AspectBarChart } from "@/components/charts/AspectBarChart";
import { ImportanceMatrix } from "@/components/charts/ImportanceMatrix";

function GapSeverityBadge({ severity }: { severity: string }) {
  const colors: Record<string, string> = {
    high: "bg-red-100 text-red-700",
    medium: "bg-yellow-100 text-yellow-700",
    low: "bg-green-100 text-green-700",
  };
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${colors[severity] || "bg-gray-100 text-gray-600"}`}>
      {severity.toUpperCase()}
    </span>
  );
}

function PriorityBadge({ priority }: { priority: string }) {
  const colors: Record<string, string> = {
    high: "bg-red-100 text-red-700",
    medium: "bg-yellow-100 text-yellow-700",
    low: "bg-green-100 text-green-700",
  };
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${colors[priority] || "bg-gray-100 text-gray-600"}`}>
      {priority.toUpperCase()}
    </span>
  );
}

function SectionHeader({ number, title, badge }: { number: string; title: string; badge?: string }) {
  return (
    <div className="flex items-center gap-3 mb-5">
      <div className="w-8 h-8 rounded-full bg-blue-600 text-white text-sm font-bold flex items-center justify-center flex-shrink-0">
        {number}
      </div>
      <h2 className="text-xl font-bold text-gray-900">{title}</h2>
      {badge && <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-semibold">{badge}</span>}
    </div>
  );
}

function EvidenceQuotes({ quotes, limit = 2 }: { quotes: string[]; limit?: number }) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? quotes : quotes.slice(0, limit);
  if (quotes.length === 0) return null;
  return (
    <div className="mt-3 space-y-1.5">
      {shown.map((q, i) => (
        <blockquote key={i} className="text-xs text-gray-500 italic border-l-2 border-gray-200 pl-3 py-0.5">
          "{q}"
        </blockquote>
      ))}
      {quotes.length > limit && (
        <button onClick={() => setExpanded(!expanded)} className="text-xs text-blue-500 hover:underline">
          {expanded ? "Show less" : `+${quotes.length - limit} more reviews`}
        </button>
      )}
    </div>
  );
}

function ExpectationGapSection({ gaps }: { gaps: ExpectationGapItem[] }) {
  const sorted = [...gaps].sort((a, b) => {
    const order = { high: 0, medium: 1, low: 2 };
    return (order[a.gap_severity] ?? 3) - (order[b.gap_severity] ?? 3);
  });
  return (
    <div className="space-y-4">
      {sorted.map((gap, i) => (
        <div key={i} className="bg-white border border-gray-200 rounded-xl p-5">
          <div className="flex items-start justify-between gap-2 mb-3">
            <h3 className="font-semibold text-gray-900">{gap.dimension}</h3>
            <GapSeverityBadge severity={gap.gap_severity} />
          </div>
          <div className="grid sm:grid-cols-2 gap-3 text-sm mb-3">
            <div>
              <div className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Customer Expectation</div>
              <p className="text-gray-700">{gap.expectation}</p>
            </div>
            <div>
              <div className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Actual Experience</div>
              <p className="text-gray-700">{gap.actual_experience}</p>
            </div>
          </div>
          <p className="text-sm text-gray-600 mb-2">{gap.gap_description}</p>
          <div className="p-3 bg-blue-50 rounded-lg text-sm text-blue-800">
            <strong>Recommended Action:</strong> {gap.recommended_action}
          </div>
          <EvidenceQuotes quotes={gap.supporting_reviews} />
        </div>
      ))}
    </div>
  );
}

function ContradictionSection({ cases }: { cases: ContradictionCase[] }) {
  if (cases.length === 0) {
    return <p className="text-sm text-gray-400">No contradictions detected.</p>;
  }
  return (
    <div className="space-y-4">
      {cases.map((c, i) => (
        <div key={i} className="bg-white border border-gray-200 rounded-xl p-5">
          <div className="flex items-center gap-3 mb-3">
            <div className={`text-xs font-bold px-2 py-0.5 rounded-full ${c.contradiction_type === "type_a" ? "bg-orange-100 text-orange-700" : "bg-purple-100 text-purple-700"}`}>
              {c.contradiction_type === "type_a" ? "Type A: Hidden Complaint" : "Type B: Hidden Praise"}
            </div>
            <div className="flex gap-0.5">
              {Array.from({ length: 5 }).map((_, j) => (
                <span key={j} className={j < c.rating ? "text-yellow-400" : "text-gray-200"}>★</span>
              ))}
            </div>
          </div>
          <blockquote className="text-sm text-gray-700 italic border-l-2 border-gray-300 pl-3 mb-3">
            "{c.review_text.slice(0, 280)}{c.review_text.length > 280 ? "…" : ""}"
          </blockquote>
          <div className="grid sm:grid-cols-2 gap-3 text-xs">
            <div>
              <p className="font-semibold text-green-700 mb-1">Positive elements</p>
              <ul className="list-disc list-inside text-gray-600 space-y-0.5">
                {c.positive_elements.map((e, j) => <li key={j}>{e}</li>)}
              </ul>
            </div>
            <div>
              <p className="font-semibold text-red-700 mb-1">Negative elements</p>
              <ul className="list-disc list-inside text-gray-600 space-y-0.5">
                {c.negative_elements.map((e, j) => <li key={j}>{e}</li>)}
              </ul>
            </div>
          </div>
          {c.implication && (
            <p className="text-xs text-gray-500 mt-3 italic">{c.implication}</p>
          )}
        </div>
      ))}
    </div>
  );
}

function ImprovementSection({ improvements }: { improvements: ImprovementPoint[] }) {
  return (
    <div className="space-y-3">
      {improvements.map((imp, i) => (
        <div key={i} className="bg-white border border-gray-200 rounded-xl p-5">
          <div className="flex items-start justify-between gap-2 mb-2">
            <h3 className="font-semibold text-gray-900">{imp.area}</h3>
            <PriorityBadge priority={imp.priority} />
          </div>
          <p className="text-sm text-gray-700 mb-2">{imp.expected_effect}</p>
          <div className="flex items-center gap-4 text-xs text-gray-500">
            <span>Frequency: {imp.frequency} mentions</span>
            <span>Impact score: {imp.impact_score}/10</span>
          </div>
          <EvidenceQuotes quotes={imp.supporting_evidence} />
        </div>
      ))}
    </div>
  );
}

function ReportContent({ result }: { result: VOCResult }) {
  return (
    <div className="space-y-12">
      {/* Overview */}
      <div className="bg-gradient-to-r from-blue-600 to-blue-700 rounded-2xl p-6 text-white">
        <h1 className="text-2xl font-bold mb-1">Samsung TV VOC Intelligence Report</h1>
        <p className="text-blue-100 text-sm mb-4">{result.model} · {new Date(result.analysis_date).toLocaleDateString()} · {result.total_reviews} reviews</p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            ["Avg Rating", `${result.avg_rating.toFixed(1)} / 5.0`],
            ["Total Reviews", result.total_reviews.toLocaleString()],
            ["Complaint Issues", result.complaints.length.toString()],
            ["Expectation Gaps", result.expectation_gaps.length.toString()],
          ].map(([label, value]) => (
            <div key={label} className="bg-blue-500/30 rounded-xl p-3">
              <p className="text-xs text-blue-200">{label}</p>
              <p className="text-xl font-bold">{value}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Executive Summary */}
      <section>
        <SectionHeader number="0" title="Executive Summary" />
        <div className="bg-white border border-gray-200 rounded-xl p-6 space-y-4">
          <p className="text-gray-700 text-sm leading-relaxed whitespace-pre-wrap">{result.executive_summary}</p>
          {result.key_insights.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-gray-800 mb-2">Key Insights</h3>
              <ul className="space-y-1.5">
                {result.key_insights.map((insight, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                    <span className="text-blue-500 font-bold mt-0.5">•</span>
                    {insight}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </section>

      {/* Sentiment Distribution */}
      <section>
        <SectionHeader number="S" title="Sentiment Overview" />
        <div className="grid sm:grid-cols-2 gap-5">
          <div className="bg-white border border-gray-200 rounded-xl p-5">
            <h3 className="text-sm font-semibold text-gray-700 mb-4">Overall Sentiment</h3>
            <SentimentPieChart data={Object.entries(result.sentiment_distribution).map(([name, value]) => ({ name, value }))} />
          </div>
          <div className="bg-white border border-gray-200 rounded-xl p-5">
            <h3 className="text-sm font-semibold text-gray-700 mb-4">Aspect Sentiment Breakdown</h3>
            <AspectBarChart data={Object.entries(result.aspect_sentiment_summary).map(([aspect, s]) => ({ aspect, positive: s.positive, negative: s.negative, neutral: s.neutral }))} />
          </div>
        </div>
      </section>

      {/* Task 1: Complaints */}
      <section>
        <SectionHeader number="1" title="Top Complaints" />
        <div className="space-y-3">
          {result.complaints.map((c) => (
            <div key={c.rank} className="bg-white border border-gray-200 rounded-xl p-5">
              <div className="flex items-start gap-3">
                <div className="w-7 h-7 rounded-full bg-red-100 text-red-700 text-sm font-bold flex items-center justify-center flex-shrink-0">
                  {c.rank}
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <span className="font-semibold text-gray-900">{c.category}</span>
                    <span className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">{c.aspect}</span>
                    <span className="text-xs text-red-600 font-medium">{c.frequency_pct.toFixed(1)}% of reviews</span>
                  </div>
                  <p className="text-sm text-gray-600">{c.root_cause}</p>
                  <EvidenceQuotes quotes={c.representative_reviews} />
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Task 2: Satisfaction Drivers */}
      <section>
        <SectionHeader number="2" title="Satisfaction Drivers" />
        <div className="space-y-3">
          {result.satisfaction_drivers.map((d) => (
            <div key={d.rank} className="bg-white border border-gray-200 rounded-xl p-5">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-3">
                  <div className="w-7 h-7 rounded-full bg-green-100 text-green-700 text-sm font-bold flex items-center justify-center flex-shrink-0">
                    {d.rank}
                  </div>
                  <div>
                    <span className="font-semibold text-gray-900">{d.factor}</span>
                    <span className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded ml-2">{d.aspect}</span>
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-bold text-green-700">{d.positive_rate.toFixed(0)}%</div>
                  <div className="text-xs text-gray-400">{d.mention_count} mentions</div>
                </div>
              </div>
              <div className="w-full bg-gray-100 rounded-full h-1.5">
                <div className="bg-green-500 h-1.5 rounded-full" style={{ width: `${Math.min(d.positive_rate, 100)}%` }} />
              </div>
              <EvidenceQuotes quotes={d.representative_reviews} />
            </div>
          ))}
        </div>
      </section>

      {/* Task 3: Improvements */}
      <section>
        <SectionHeader number="3" title="Improvement Priorities" />
        <ImprovementSection improvements={result.improvement_points} />
      </section>

      {/* Task 4: Marketing */}
      {result.marketing_recommendations && (
        <section>
          <SectionHeader number="4" title="Marketing Recommendations" />
          <div className="bg-white border border-gray-200 rounded-xl p-6 space-y-5">
            <div>
              <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-1">Current Customer Perception</h3>
              <p className="text-gray-800">{result.marketing_recommendations.current_perception}</p>
            </div>
            <div>
              <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-2">Actual Value Drivers</h3>
              <ul className="space-y-1">
                {result.marketing_recommendations.actual_value_drivers.map((v, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                    <span className="text-green-500">✓</span>{v}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-2">New Message Proposals</h3>
              <ul className="space-y-2">
                {result.marketing_recommendations.new_message_proposals.map((msg, i) => (
                  <li key={i} className="p-3 bg-blue-50 rounded-lg text-sm text-blue-800 italic">"{msg}"</li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="text-sm font-semibold text-red-600 uppercase tracking-wide mb-2">Messages to Avoid</h3>
              <ul className="space-y-1">
                {result.marketing_recommendations.messages_to_avoid.map((m, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                    <span className="text-red-500">✗</span>{m}
                  </li>
                ))}
              </ul>
            </div>
            <EvidenceQuotes quotes={result.marketing_recommendations.evidence} limit={3} />
          </div>
        </section>
      )}

      {/* Task 5: Competitive Positioning */}
      {result.positioning_analysis && (
        <section>
          <SectionHeader number="5" title="Competitive Positioning" />
          <div className="space-y-5">
            <div className="grid sm:grid-cols-2 gap-4">
              <div className="bg-white border border-green-200 rounded-xl p-5">
                <h3 className="text-sm font-semibold text-green-700 mb-3">Samsung Strengths</h3>
                <ul className="space-y-1.5">
                  {result.positioning_analysis.samsung_strengths.map((s, i) => (
                    <li key={i} className="text-sm text-gray-700 flex items-start gap-2"><span className="text-green-500">+</span>{s}</li>
                  ))}
                </ul>
              </div>
              <div className="bg-white border border-red-200 rounded-xl p-5">
                <h3 className="text-sm font-semibold text-red-700 mb-3">Samsung Weaknesses</h3>
                <ul className="space-y-1.5">
                  {result.positioning_analysis.samsung_weaknesses.map((w, i) => (
                    <li key={i} className="text-sm text-gray-700 flex items-start gap-2"><span className="text-red-500">−</span>{w}</li>
                  ))}
                </ul>
              </div>
            </div>

            {result.positioning_analysis.competitors.map((comp) => (
              <div key={comp.name} className="bg-white border border-gray-200 rounded-xl p-5">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-semibold text-gray-900">{comp.name}</h3>
                  <span className="text-sm text-gray-500">{comp.price_range}</span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs mb-3">
                  {[["Picture", comp.picture_quality], ["Sound", comp.sound_quality], ["UX", comp.ux], ["Smart TV", comp.smart_features]].map(([label, val]) => (
                    <div key={label} className="bg-gray-50 rounded-lg p-2">
                      <p className="text-gray-400 mb-0.5">{label}</p>
                      <p className={`font-semibold ${val === "better" ? "text-red-600" : val === "worse" ? "text-green-600" : "text-yellow-600"}`}>
                        {val}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            ))}

            <div className="bg-blue-50 border border-blue-200 rounded-xl p-5">
              <h3 className="text-sm font-semibold text-blue-800 mb-2">Positioning Recommendation</h3>
              <p className="text-sm text-blue-700">{result.positioning_analysis.positioning_recommendation}</p>
            </div>
          </div>
        </section>
      )}

      {/* Task 6: Contradictions */}
      <section>
        <SectionHeader number="6" title="Review Contradictions" />
        <ContradictionSection cases={result.contradictions} />
      </section>

      {/* Task 7: Importance Matrix */}
      <section>
        <SectionHeader number="7" title="Importance-Frequency Matrix" />
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <ImportanceMatrix data={result.importance_matrix} />
        </div>
      </section>

      {/* Task 8: Expectation Gap (핵심) */}
      <section>
        <SectionHeader number="8" title="Customer Expectation Gap Analysis" badge="핵심" />
        <ExpectationGapSection gaps={result.expectation_gaps} />
      </section>
    </div>
  );
}

function ReportPageInner() {
  const searchParams = useSearchParams();
  const jobId = searchParams.get("jobId");
  const filename = searchParams.get("filename");

  const [result, setResult] = useState<VOCResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId && !filename) {
      setError("No report specified. Use jobId or filename query param.");
      setLoading(false);
      return;
    }
    (async () => {
      try {
        const data = jobId ? await api.getResult(jobId) : await api.getReport(filename!);
        setResult(data);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Failed to load report");
      } finally {
        setLoading(false);
      }
    })();
  }, [jobId, filename]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-96">
        <div className="text-center space-y-3">
          <div className="w-10 h-10 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-sm text-gray-500">Loading report…</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-lg mx-auto px-4 py-16 text-center">
        <p className="text-red-600 mb-4">{error}</p>
        <Link href="/analysis" className="text-blue-600 hover:underline text-sm">
          ← Run a new analysis
        </Link>
      </div>
    );
  }

  if (!result) return null;

  return (
    <div className="max-w-4xl mx-auto px-4 py-10">
      <div className="flex items-center justify-between mb-8">
        <Link href="/" className="text-sm text-gray-500 hover:text-gray-700">← Dashboard</Link>
        <Link href="/analysis" className="text-sm bg-blue-600 text-white px-3 py-1.5 rounded-lg hover:bg-blue-700">
          New Analysis
        </Link>
      </div>
      <ReportContent result={result} />
    </div>
  );
}

export default function ReportPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center min-h-96"><div className="w-10 h-10 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" /></div>}>
      <ReportPageInner />
    </Suspense>
  );
}
