"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { api, ReportMeta } from "@/lib/api";

export default function ReportsPage() {
  const [reports, setReports] = useState<ReportMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listReports()
      .then(setReports)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="max-w-3xl mx-auto px-4 py-10 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Saved Reports</h1>
          <p className="text-sm text-gray-500 mt-0.5">Previously generated VOC analysis results</p>
        </div>
        <Link href="/analysis" className="text-sm bg-brand-600 text-white px-4 py-2 rounded-lg hover:bg-brand-700 font-medium">
          + New Analysis
        </Link>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-16">
          <div className="w-8 h-8 border-4 border-brand-600 border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">{error}</div>
      )}

      {!loading && !error && reports.length === 0 && (
        <div className="text-center py-16 text-gray-400">
          <p className="font-medium">No reports yet</p>
          <Link href="/analysis" className="text-brand-600 hover:underline text-sm mt-1 block">
            Run your first analysis →
          </Link>
        </div>
      )}

      <div className="space-y-3">
        {reports.map((r) => (
          <Link
            key={r.filename}
            href={`/report?filename=${encodeURIComponent(r.filename)}`}
            className="block bg-white border border-gray-200 rounded-xl p-5 hover:border-brand-300 hover:shadow-sm transition-all"
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="flex items-center gap-2">
                  {r.category && (
                    <span className="text-[10px] font-semibold text-brand-600 bg-brand-50 px-1.5 py-0.5 rounded uppercase tracking-wider">
                      {r.category}
                    </span>
                  )}
                  <p className="font-semibold text-gray-900">{r.model}</p>
                </div>
                <p className="text-xs text-gray-400 mt-0.5">
                  {new Date(r.analysis_date).toLocaleString()} · {r.total_reviews.toLocaleString()} reviews
                </p>
              </div>
              <div className="text-right flex-shrink-0">
                <div className="flex items-center gap-1">
                  <span className="text-yellow-400 text-sm">★</span>
                  <span className="font-bold text-gray-800">{r.avg_rating.toFixed(1)}</span>
                </div>
                <p className="text-xs text-brand-600 mt-1">View report →</p>
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
