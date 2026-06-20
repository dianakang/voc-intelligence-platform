"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, VOCResult } from "@/lib/api";
import { SentimentPieChart } from "@/components/charts/SentimentPieChart";
import { AspectBarChart } from "@/components/charts/AspectBarChart";
import { ComplaintRankTable } from "@/components/dashboard/ComplaintRankTable";
import { SatisfactionDrivers } from "@/components/dashboard/SatisfactionDrivers";
import { StatCard } from "@/components/dashboard/StatCard";

export default function Dashboard() {
  const [result, setResult] = useState<VOCResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listReports()
      .then((reports) => {
        if (reports.length > 0) {
          return api.getReport(reports[0].filename);
        }
        return null;
      })
      .then((r) => {
        setResult(r);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-brand-600" />
      </div>
    );
  }

  if (!result) {
    return (
      <div className="text-center py-24">
        <h2 className="text-2xl font-semibold text-gray-900 mb-2">No Analysis Yet</h2>
        <p className="text-gray-500 mb-6">Run your first VOC analysis to see insights here.</p>
        <Link
          href="/analysis"
          className="inline-flex items-center px-6 py-3 bg-brand-600 text-white rounded-lg hover:bg-brand-700 font-medium"
        >
          Start Analysis →
        </Link>
      </div>
    );
  }

  const sentimentData = Object.entries(result.sentiment_distribution).map(([name, value]) => ({
    name: name.charAt(0).toUpperCase() + name.slice(1),
    value,
  }));

  const aspectData = Object.entries(result.aspect_sentiment_summary)
    .map(([aspect, data]) => ({
      aspect: aspect.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase()),
      positive: data.positive,
      negative: data.negative,
      neutral: data.neutral,
    }))
    .sort((a, b) => b.positive + b.negative - (a.positive + a.negative))
    .slice(0, 8);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">VOC Intelligence Dashboard</h1>
          <p className="text-gray-500 mt-1">
            Samsung 50&quot; Crystal UHD U7900F · Analyzed {result.analysis_date}
          </p>
        </div>
        <Link
          href="/analysis"
          className="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 font-medium"
        >
          Re-run Analysis
        </Link>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total Reviews" value={result.total_reviews.toLocaleString()} />
        <StatCard label="Avg Rating" value={`${result.avg_rating}/5`} />
        <StatCard
          label="Positive Rate"
          value={`${Math.round((result.sentiment_distribution.positive || 0) / result.total_reviews * 100)}%`}
        />
        <StatCard
          label="Key Insights"
          value={result.key_insights.length.toString()}
        />
      </div>

      {/* Executive Summary */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Executive Summary</h2>
        <p className="text-gray-700 leading-relaxed whitespace-pre-line">{result.executive_summary}</p>
        {result.key_insights.length > 0 && (
          <div className="mt-6 pt-5 border-t border-gray-100">
            <h3 className="text-sm font-semibold text-gray-700 mb-3">Key Insights</h3>
            <ul className="space-y-2">
              {result.key_insights.map((insight, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                  <span className="text-brand-500 font-bold mt-0.5">{i + 1}.</span>
                  <span>{insight}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-brand-100 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Sentiment Distribution</h2>
          <SentimentPieChart data={sentimentData} />
        </div>
        <div className="bg-white rounded-xl border border-brand-100 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Aspect Sentiment Analysis</h2>
          <AspectBarChart data={aspectData} />
        </div>
      </div>

      {/* Complaints + Satisfaction */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-brand-100 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Top Complaints</h2>
          <ComplaintRankTable complaints={result.complaints.slice(0, 6)} />
        </div>
        <div className="bg-white rounded-xl border border-brand-100 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Satisfaction Drivers</h2>
          <SatisfactionDrivers drivers={result.satisfaction_drivers.slice(0, 5)} />
        </div>
      </div>

      {/* Segment Divergence preview */}
      {result.segment_divergence_analysis && result.segment_divergence_analysis.segment_insights.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900">Segment Divergence</h2>
            <span className="text-xs text-gray-600 bg-gray-100 px-2 py-1 rounded font-medium">NEW</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {result.segment_divergence_analysis.segment_insights.slice(0, 2).map((item, i) => (
              <div key={i} className="rounded-lg border border-gray-200 bg-gray-50 p-4">
                <div className="flex items-center justify-between gap-3 mb-2">
                  <h3 className="text-sm font-semibold text-gray-900">{item.segment}</h3>
                  <span className="text-xs text-gray-500">{item.size_estimate} mentions</span>
                </div>
                <p className="text-sm text-gray-700 line-clamp-3">{item.business_implication}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Expectation Gaps preview */}
      {result.expectation_gaps.length > 0 && (
        <div className="bg-white rounded-xl border border-brand-100 p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900">Expectation Gap Analysis</h2>
            <span className="text-xs text-brand-600 bg-brand-50 px-2 py-1 rounded font-medium">핵심</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {result.expectation_gaps
              .sort((a, b) => ({ high: 0, medium: 1, low: 2 }[a.gap_severity] - { high: 0, medium: 1, low: 2 }[b.gap_severity]))
              .slice(0, 4)
              .map((gap, i) => (
                <div key={i} className={`rounded-lg border p-4 ${gap.gap_severity === "high" ? "border-brand-300 bg-brand-50" : gap.gap_severity === "medium" ? "border-brand-200 bg-brand-50/50" : "border-brand-100 bg-white"}`}>
                  <div className="flex items-center gap-2 mb-2">
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${gap.gap_severity === "high" ? "bg-brand-200 text-brand-800" : gap.gap_severity === "medium" ? "bg-brand-100 text-brand-700" : "bg-brand-50 text-brand-600"}`}>
                      {gap.gap_severity.toUpperCase()} GAP
                    </span>
                    <h3 className="text-sm font-semibold text-gray-900">{gap.dimension}</h3>
                  </div>
                  <div className="space-y-1 text-xs text-gray-600">
                    <div><span className="font-medium">Expected:</span> {gap.expectation}</div>
                    <div><span className="font-medium">Actual:</span> {gap.actual_experience}</div>
                  </div>
                </div>
              ))}
          </div>
          <Link href="/report" className="inline-block mt-4 text-sm text-brand-600 hover:text-brand-800 font-medium">
            View Full Report →
          </Link>
        </div>
      )}
    </div>
  );
}
