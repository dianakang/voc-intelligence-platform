"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { api, JobStatus } from "@/lib/api";
import { AgentExecutionPanel } from "@/components/agents/AgentExecutionPanel";

const DEFAULT_PRODUCT_URL =
  "https://www.samsung.com/us/tvs/uhd-4k-tv/50-inch-class-crystal-uhd-u7900f-4k-smart-tv-sku-un50u7900ffxza/";

export default function AnalysisPage() {
  const router = useRouter();
  const [productUrl, setProductUrl] = useState(DEFAULT_PRODUCT_URL);
  const [maxReviews, setMaxReviews] = useState(200);
  const [skipIfCached, setSkipIfCached] = useState(true);
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const startPolling = (id: string) => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const s = await api.getStatus(id);
        setStatus(s);
        if (s.status === "done") {
          stopPolling();
          setTimeout(() => router.push(`/report?jobId=${id}`), 1200);
        } else if (s.status === "error") {
          stopPolling();
        }
      } catch {
        // ignore transient poll errors
      }
    }, 2000);
  };

  useEffect(() => () => stopPolling(), []);

  const handleRun = async () => {
    if (!productUrl.trim()) {
      setError("Enter a Samsung product URL.");
      return;
    }
    setError(null);
    setLoading(true);
    setStatus(null);
    setJobId(null);
    try {
      const res = await api.startAnalysis(maxReviews, productUrl.trim(), skipIfCached);
      setJobId(res.job_id);
      startPolling(res.job_id);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to start analysis");
    } finally {
      setLoading(false);
    }
  };

  const isPending = status?.status === "pending";
  const isRunning = status?.status === "running";
  const isDone = status?.status === "done";
  const isActive = isRunning || isPending || (!!jobId && !status);

  return (
    <div className="max-w-3xl mx-auto px-4 py-10 space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Run VOC Analysis</h1>
        <p className="text-sm text-gray-500 mt-1">
          Trigger the 5-stage LangGraph pipeline to analyze customer reviews.
        </p>
      </div>

      {/* Configuration card */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-5">
        <h2 className="text-base font-semibold text-gray-800">Configuration</h2>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Samsung Product URL
          </label>
          <input
            type="url"
            value={productUrl}
            onChange={(e) => setProductUrl(e.target.value)}
            disabled={isRunning}
            placeholder="https://www.samsung.com/us/tvs/.../sku-un55.../"
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50"
          />
          <p className="text-xs text-gray-400 mt-1">
            The model code is read from the URL&apos;s &quot;-sku-...&quot; segment.
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Max Reviews to Fetch
          </label>
          <input
            type="number"
            value={maxReviews}
            min={10}
            max={1000}
            step={10}
            onChange={(e) => setMaxReviews(parseInt(e.target.value))}
            disabled={isRunning}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50"
          />
          <p className="text-xs text-gray-400 mt-1">Recommended: 200–500 for best results</p>
        </div>

        <div>
          <label className="flex items-center gap-2 text-sm font-medium text-gray-700">
            <input
              type="checkbox"
              checked={skipIfCached}
              onChange={(e) => setSkipIfCached(e.target.checked)}
              disabled={isRunning}
              className="rounded border-gray-300 text-brand-600 focus:ring-brand-500 disabled:opacity-50"
            />
            Reuse cached result if data unchanged
          </label>
          <p className="text-xs text-gray-400 mt-1">
            Skips all LLM analysis and re-uses the last saved result if this URL, max reviews, and the
            underlying review/spec data haven&apos;t changed since the last full run. Saves cost on repeat runs.
          </p>
        </div>

        <div className="pt-1">
          <button
            onClick={handleRun}
            disabled={isActive || loading}
            className="w-full py-2.5 px-4 bg-brand-600 hover:bg-brand-700 text-white font-semibold rounded-lg text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? "Starting…" : isActive ? "Analysis Running…" : "Run VOC Analysis"}
          </button>
          {error && (
            <p className="text-sm text-red-600 mt-2">{error}</p>
          )}
        </div>
      </div>

      {/* Pipeline stages legend */}
      {!status && !jobId && (
        <div className="bg-gray-50 rounded-xl border border-gray-200 p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">5-Stage Pipeline</h3>
          <ol className="space-y-2 text-sm text-gray-600">
            {[
              ["1", "Data Collection", "Fetch Samsung BazaarVoice reviews (with fallback)"],
              ["2", "Review Cleaning", "Deduplication + LLM-powered cleaning (Haiku)"],
              ["3", "VOC Taxonomy + RAG", "Aspect classification + vector index build"],
              ["4", "Parallel Analysis", "8 analysis tasks via Sonnet + Opus agents"],
              ["5", "Executive Report", "Narrative synthesis by Claude Opus"],
            ].map(([num, name, desc]) => (
              <li key={num} className="flex items-start gap-3">
                <span className="w-5 h-5 rounded-full bg-brand-100 text-brand-700 text-xs font-bold flex items-center justify-center flex-shrink-0 mt-0.5">{num}</span>
                <span><strong>{name}</strong> — {desc}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* Live execution panel */}
      {status && (
        <div className="space-y-4">
          <AgentExecutionPanel status={status} />

          {isDone && (
            <div className="p-4 bg-green-50 border border-green-200 rounded-lg text-sm text-green-700 font-medium text-center">
              Analysis complete — redirecting to report…
            </div>
          )}
        </div>
      )}

      {/* Job ID */}
      {jobId && (
        <p className="text-xs text-gray-400 text-center">Job ID: {jobId}</p>
      )}
    </div>
  );
}
