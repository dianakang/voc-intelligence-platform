"use client";

import { useEffect, useState } from "react";
import { JobStatus } from "@/lib/api";
import { cn } from "@/lib/utils";

const AGENT_LABELS: Record<string, string> = {
  DataCollectionAgent: "Data Collection",
  ReviewCleaningAgent: "Review Cleaning",
  VOCTaxonomyAgent: "VOC Taxonomy + RAG Index",
  SentimentAnalysisAgent: "Sentiment Analysis",
  ComplaintAnalysisAgent: "Complaint Analysis",
  SatisfactionAnalysisAgent: "Satisfaction Analysis",
  ImprovementAnalysisAgent: "Improvement Analysis",
  MarketingAnalysisAgent: "Marketing Analysis",
  CompetitivePositioningAgent: "Competitive Positioning",
  ContradictionAgent: "Contradiction Detection",
  ImportanceAnalysisAgent: "Importance Matrix",
  ExpectationGapAgent: "Expectation Gap (핵심)",
  ReportGenerationAgent: "Executive Report",
};

const STATUS_CONFIG: Record<string, { icon: string; color: string; bg: string }> = {
  done: { icon: "✓", color: "text-green-700", bg: "bg-green-100" },
  running: { icon: "⟳", color: "text-brand-700", bg: "bg-brand-100" },
  error: { icon: "✗", color: "text-red-700", bg: "bg-red-100" },
  pending: { icon: "○", color: "text-gray-400", bg: "bg-gray-100" },
};

function useElapsedTime(active: boolean) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!active) return;
    setSeconds(0);
    const id = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [active]);
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

interface Props {
  status: JobStatus;
}

export function AgentExecutionPanel({ status }: Props) {
  const agents = Object.entries(status.agent_statuses);
  const doneCount = agents.filter(([, s]) => s === "done").length;
  const isActive = status.status === "running" || status.status === "pending";
  const elapsed = useElapsedTime(isActive);

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6">
      {/* Header row */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold text-gray-900">Agent Execution</h2>
          {isActive && (
            <span className="flex items-center gap-1.5 text-xs text-brand-600 bg-brand-50 px-2 py-0.5 rounded-full font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-brand-500 animate-pulse inline-block" />
              Live
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 text-sm text-gray-500">
          {isActive && (
            <span className="tabular-nums text-gray-400">{elapsed}</span>
          )}
          <span>
            {doneCount}/{agents.length} complete
          </span>
        </div>
      </div>

      {/* Progress bar */}
      <div className="mb-6">
        <div className="flex items-center justify-between text-sm mb-1.5">
          <span className="text-gray-600 truncate max-w-xs">{status.current_step}</span>
          <span className="font-medium text-brand-600 ml-2 flex-shrink-0">{status.progress_pct}%</span>
        </div>
        <div className="w-full bg-gray-100 rounded-full h-2 overflow-hidden">
          <div
            className={cn(
              "h-2 rounded-full transition-all duration-700",
              status.status === "error" ? "bg-red-500" :
              status.status === "done" ? "bg-green-500" : "bg-brand-500"
            )}
            style={{ width: `${status.progress_pct}%` }}
          />
        </div>
      </div>

      {/* Agent grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {agents.map(([agentName, agentStatus]) => {
          const cfg = STATUS_CONFIG[agentStatus] || STATUS_CONFIG.pending;
          const label = AGENT_LABELS[agentName] || agentName;
          const isKeyTask = agentName === "ExpectationGapAgent";
          const isThisRunning = agentStatus === "running";

          return (
            <div
              key={agentName}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-lg transition-colors duration-300",
                isKeyTask ? "ring-1 ring-brand-200 bg-brand-50/50" :
                isThisRunning ? "bg-brand-50" :
                agentStatus === "done" ? "bg-green-50/60" :
                "bg-gray-50"
              )}
            >
              <div className={cn(
                "w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0",
                cfg.bg, cfg.color
              )}>
                {isThisRunning ? (
                  <span className="animate-spin inline-block">⟳</span>
                ) : (
                  cfg.icon
                )}
              </div>
              <span className={cn(
                "text-sm",
                agentStatus === "pending" ? "text-gray-400" :
                agentStatus === "running" ? "text-brand-800 font-medium" :
                "text-gray-800"
              )}>
                {label}
                {isKeyTask && <span className="ml-1 text-xs text-brand-500 font-medium">★</span>}
              </span>
            </div>
          );
        })}
      </div>

      {status.error && (
        <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          <strong>Error:</strong> {status.error}
        </div>
      )}
    </div>
  );
}
