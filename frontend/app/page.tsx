"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, ReportMeta } from "@/lib/api";

function groupByCategory(reports: ReportMeta[]): { category: string; reports: ReportMeta[] }[] {
  const groups = new Map<string, ReportMeta[]>();
  for (const r of reports) {
    const key = r.category || "Other";
    groups.set(key, [...(groups.get(key) ?? []), r]);
  }
  // reports arrives sorted by analysis_date desc, so each group's first item is its latest run
  return Array.from(groups.entries()).map(([category, reports]) => ({ category, reports }));
}

function CategoryCard({ category, reports }: { category: string; reports: ReportMeta[] }) {
  const latest = reports[0];
  return (
    <Link
      href={`/report?filename=${encodeURIComponent(latest.filename)}`}
      className="block bg-white rounded-xl border border-gray-200 p-6 hover:border-brand-300 hover:shadow-sm transition-all"
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <p className="text-xs font-semibold text-brand-600 uppercase tracking-wider">{category}</p>
          <h2 className="text-lg font-bold text-gray-900 mt-0.5">{latest.product_name || latest.model}</h2>
          <p className="text-xs text-gray-400 mt-0.5">{latest.model}</p>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <span className="text-yellow-400">★</span>
          <span className="font-bold text-gray-800">{latest.avg_rating.toFixed(1)}</span>
        </div>
      </div>
      <div className="flex items-center gap-4 text-xs text-gray-500">
        <span>{latest.total_reviews.toLocaleString()} reviews analyzed</span>
        <span>{new Date(latest.analysis_date).toLocaleDateString()}</span>
      </div>
      {reports.length > 1 && (
        <p className="text-xs text-gray-400 mt-2">+{reports.length - 1} earlier run{reports.length - 1 > 1 ? "s" : ""} for this category</p>
      )}
      <p className="text-sm text-brand-600 font-medium mt-4">View report →</p>
    </Link>
  );
}

export default function Dashboard() {
  const [reports, setReports] = useState<ReportMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listReports()
      .then(setReports)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-brand-600" />
      </div>
    );
  }

  if (error) {
    return <div className="max-w-lg mx-auto px-4 py-16 text-center text-red-600 text-sm">{error}</div>;
  }

  if (reports.length === 0) {
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

  const groups = groupByCategory(reports);

  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">VOC Intelligence Dashboard</h1>
          <p className="text-gray-500 mt-1">
            {groups.length} product categor{groups.length === 1 ? "y" : "ies"} analyzed · {reports.length} total run{reports.length > 1 ? "s" : ""}
          </p>
        </div>
        <Link
          href="/analysis"
          className="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 font-medium"
        >
          New Analysis
        </Link>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
        {groups.map((g) => (
          <CategoryCard key={g.category} category={g.category} reports={g.reports} />
        ))}
      </div>

      <Link href="/reports" className="inline-block text-sm text-brand-600 hover:underline">
        View all {reports.length} saved reports →
      </Link>
    </div>
  );
}
