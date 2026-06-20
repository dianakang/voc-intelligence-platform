"use client";

import { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { api, VOCResult, ExpectationGapItem, ContradictionCase, ImprovementPoint, SegmentInsight } from "@/lib/api";
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
    <div className="mt-4 space-y-2">
      {shown.map((q, i) => (
        <blockquote key={i} className="text-xs text-gray-500 italic border-l-3 border-gray-200 pl-3 py-1 leading-relaxed">
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

function firstSentence(text: string) {
  const end = text.search(/[.!?]\s/);
  return end > 0 ? text.slice(0, end + 1) : text;
}

function ExpectationGapCard({ gap }: { gap: ExpectationGapItem }) {
  const [open, setOpen] = useState(false);
  const severityBorder = { high: "border-l-red-400", medium: "border-l-yellow-400", low: "border-l-green-400" }[gap.gap_severity] ?? "border-l-gray-300";
  const expectedSnippet = firstSentence(gap.expectation);
  const actualSnippet = firstSentence(gap.actual_experience);
  return (
    <div className={`bg-white border border-gray-200 border-l-4 ${severityBorder} rounded-xl overflow-hidden`}>
      {/* Header */}
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between gap-3 px-5 py-4 text-left hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-center gap-3 min-w-0">
          <GapSeverityBadge severity={gap.gap_severity} />
          <h3 className="font-semibold text-gray-900 text-sm truncate">{gap.dimension}</h3>
        </div>
        <span className="text-xs text-gray-400 flex-shrink-0">{open ? "↑" : "↓"}</span>
      </button>

      {/* Expected → Actual comparison — always visible */}
      <div className="grid sm:grid-cols-2 divide-y sm:divide-y-0 sm:divide-x divide-gray-100 border-t border-gray-100">
        <div className="px-5 py-3">
          <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-1">Expected</p>
          <p className="text-sm text-gray-700 leading-snug">{expectedSnippet}</p>
        </div>
        <div className="px-5 py-3 bg-red-50/40">
          <p className="text-[10px] font-semibold text-red-400 uppercase tracking-wider mb-1">Reality</p>
          <p className="text-sm text-gray-700 leading-snug">{actualSnippet}</p>
        </div>
      </div>

      {/* Expanded detail */}
      {open && (
        <div className="border-t border-gray-100 px-5 py-4 space-y-3">
          {(gap.expectation !== expectedSnippet || gap.actual_experience !== actualSnippet) && (
            <div className="grid sm:grid-cols-2 gap-3 text-xs text-gray-600">
              <p className="leading-relaxed"><span className="font-medium text-gray-700">Full expectation: </span>{gap.expectation}</p>
              <p className="leading-relaxed"><span className="font-medium text-gray-700">Full experience: </span>{gap.actual_experience}</p>
            </div>
          )}
          <div className="p-3 bg-blue-50 rounded-lg">
            <p className="text-[10px] font-semibold text-blue-500 uppercase tracking-wider mb-1">Recommended Action</p>
            <p className="text-sm text-blue-800 leading-relaxed">{gap.recommended_action}</p>
          </div>
          <EvidenceQuotes quotes={gap.supporting_reviews} limit={2} />
        </div>
      )}

      {/* Recommended action teaser when collapsed */}
      {!open && (
        <div className="border-t border-gray-100 px-5 py-2.5 bg-blue-50/50">
          <p className="text-xs text-blue-700 leading-snug line-clamp-1">
            <span className="font-semibold">Action: </span>{firstSentence(gap.recommended_action)}
          </p>
        </div>
      )}
    </div>
  );
}

function ExpectationGapSection({ gaps }: { gaps: ExpectationGapItem[] }) {
  if (gaps.length === 0) {
    return (
      <div className="bg-gray-50 border border-gray-200 rounded-xl p-8 text-center text-gray-400 text-sm">
        No expectation gap data in this report. Re-run the analysis to generate this section.
      </div>
    );
  }
  const sorted = [...gaps].sort((a, b) => {
    const order = { high: 0, medium: 1, low: 2 };
    return (order[a.gap_severity] ?? 3) - (order[b.gap_severity] ?? 3);
  });
  return (
    <div className="space-y-3">
      {sorted.map((gap, i) => <ExpectationGapCard key={i} gap={gap} />)}
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

function SegmentInsightCard({ item }: { item: SegmentInsight }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between gap-3 px-5 py-4 text-left hover:bg-gray-50 transition-colors"
      >
        <div>
          <h3 className="font-semibold text-gray-900 text-sm">{item.segment}</h3>
          <p className="text-xs text-gray-500 mt-1">Size estimate: {item.size_estimate}</p>
        </div>
        <span className="text-xs text-gray-400 flex-shrink-0">{open ? "↑" : "↓"}</span>
      </button>
      <div className="grid sm:grid-cols-2 divide-y sm:divide-y-0 sm:divide-x divide-gray-100 border-t border-gray-100">
        <div className="px-5 py-3">
          <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-1">Positive Factors</p>
          <ul className="text-sm text-gray-700 space-y-1 list-disc list-inside">
            {item.key_positive_factors.slice(0, 3).map((factor, idx) => <li key={idx}>{factor}</li>)}
          </ul>
        </div>
        <div className="px-5 py-3 bg-red-50/40">
          <p className="text-[10px] font-semibold text-red-400 uppercase tracking-wider mb-1">Pain Points</p>
          <ul className="text-sm text-gray-700 space-y-1 list-disc list-inside">
            {item.key_pain_points.slice(0, 3).map((point, idx) => <li key={idx}>{point}</li>)}
          </ul>
        </div>
      </div>
      {open && (
        <div className="border-t border-gray-100 px-5 py-4 space-y-3">
          <div className="grid sm:grid-cols-2 gap-3 text-xs text-gray-600">
            <p className="leading-relaxed"><span className="font-medium text-gray-700">Expectation gap: </span>{item.expectation_gap}</p>
            <p className="leading-relaxed"><span className="font-medium text-gray-700">Business implication: </span>{item.business_implication}</p>
          </div>
          <div className="p-3 bg-blue-50 rounded-lg">
            <p className="text-[10px] font-semibold text-blue-500 uppercase tracking-wider mb-1">Recommended Action</p>
            <p className="text-sm text-blue-800 leading-relaxed">{item.recommended_action}</p>
          </div>
          <EvidenceQuotes quotes={item.evidence} limit={2} />
        </div>
      )}
    </div>
  );
}

function SegmentDivergenceSection({
  items,
  risks,
  opportunities,
  actions,
}: {
  items: SegmentInsight[];
  risks: string[];
  opportunities: string[];
  actions: string[];
}) {
  if (items.length === 0) {
    return (
      <div className="bg-gray-50 border border-gray-200 rounded-xl p-8 text-center text-gray-400 text-sm">
        No segment divergence data in this report.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {items.map((item, i) => <SegmentInsightCard key={i} item={item} />)}

      {risks.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <h3 className="font-semibold text-gray-900 mb-3">Emerging Risks</h3>
          <ul className="list-disc list-inside text-sm text-gray-700 space-y-1">
            {risks.map((risk, i) => <li key={i}>{risk}</li>)}
          </ul>
        </div>
      )}

      {opportunities.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <h3 className="font-semibold text-gray-900 mb-3">Emerging Opportunities</h3>
          <ul className="list-disc list-inside text-sm text-gray-700 space-y-1">
            {opportunities.map((opportunity, i) => <li key={i}>{opportunity}</li>)}
          </ul>
        </div>
      )}

      {actions.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <h3 className="font-semibold text-gray-900 mb-3">Priority Actions</h3>
          <ul className="list-disc list-inside text-sm text-gray-700 space-y-1">
            {actions.map((action, i) => <li key={i}>{action}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}

// ── Executive Summary ────────────────────────────────────────────────────────

function stripMarkdown(text: string): string {
  return text
    .replace(/^#{1,3}\s.*/gm, "")          // remove headers
    .replace(/^\s*---+\s*$/gm, "")          // remove HR
    .replace(/^\s*\*{2,4}\s*$/gm, "")       // remove bare ** lines
    .replace(/^\*\*[^*]+\*\*.*\|.*$/gm, "") // remove meta lines like **Analysis Date:** x | **Reviews:** y
    .replace(/\*\*([^*]+)\*\*/g, "$1")      // strip bold markers
    .replace(/\n{3,}/g, "\n\n")             // collapse excess newlines
    .trim();
}

function parseParagraphs(text: string): string[] {
  return stripMarkdown(text)
    .split(/\n\n+/)
    .map(p => p.replace(/\n/g, " ").trim())
    .filter(p => p.length > 20);
}

function parseInsight(raw: string): { headline: string; detail: string } {
  // Pattern: "Headline sentence.** Detail text"  (LLM bold bullet stripped of leading **)
  const boldSplit = raw.match(/^([\s\S]+?\.\s*)\*+\s*([\s\S]*)$/);
  if (boldSplit) return { headline: boldSplit[1].trim(), detail: boldSplit[2].trim() };
  // Fallback: split at first ". "
  const dot = raw.indexOf(". ");
  if (dot > 0 && dot < 100) return { headline: raw.slice(0, dot + 1), detail: raw.slice(dot + 2) };
  return { headline: raw, detail: "" };
}

function ExecutiveSummarySection({ summary, insights }: { summary: string; insights: string[] }) {
  const [expanded, setExpanded] = useState(false);
  const paragraphs = parseParagraphs(summary);
  const visible = expanded ? paragraphs : paragraphs.slice(0, 2);
  const cleanInsights = insights.filter(i => i.trim().length > 10);

  return (
    <div className="space-y-4">
      {/* Summary paragraphs */}
      <div className="bg-white border border-gray-200 rounded-xl p-6">
        <div className="space-y-3">
          {visible.map((p, i) => (
            <p key={i} className="text-sm text-gray-700 leading-relaxed">{p}</p>
          ))}
        </div>
        {paragraphs.length > 2 && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="mt-3 text-xs text-blue-600 hover:underline"
          >
            {expanded ? "Show less ↑" : `Read full summary (${paragraphs.length - 2} more paragraphs) ↓`}
          </button>
        )}
      </div>

      {/* Key insights grid */}
      {cleanInsights.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <h3 className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-4">Key Insights</h3>
          <div className="grid sm:grid-cols-2 gap-3">
            {cleanInsights.map((raw, i) => {
              const { headline, detail } = parseInsight(raw);
              return (
                <div key={i} className="flex items-start gap-3 p-3 bg-gray-50 rounded-lg">
                  <span className="w-5 h-5 rounded-full bg-blue-600 text-white text-[10px] font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
                    {i + 1}
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-gray-900 leading-snug">{headline}</p>
                    {detail && <p className="text-xs text-gray-500 mt-1 leading-relaxed">{detail}</p>}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Positioning priority cards ────────────────────────────────────────────────

function parsePositioningPriorities(text: string) {
  // Try format: (1) LABEL — Topic: text
  const numbered = [...text.matchAll(/\((\d+)\)\s+([^—]+?)\s+—\s+([^:]+):\s+([\s\S]*?)(?=\s*\(\d+\)|$)/g)];
  if (numbered.length > 0) {
    const introEnd = text.search(/\s*\(\d+\)/);
    return {
      intro: introEnd > 0 ? text.slice(0, introEnd).trim() : "",
      priorities: numbered.map((m, i) => ({
        num: String(i + 1),
        label: m[2].trim(),
        topic: m[3].trim(),
        body: m[4].trim(),
      })),
    };
  }
  // Try format: TIMEFRAME (period): text  e.g. "IMMEDIATE (0-3 months):"
  const timeboxed = [...text.matchAll(/([A-Z][A-Z\s-]+?)\s*\([^)]+\):\s*([\s\S]*?)(?=[A-Z]{3,}[^a-z]*\([^)]+\):|$)/g)];
  if (timeboxed.length > 0) {
    const introEnd = text.search(/[A-Z]{3,}[^a-z]*\([^)]+\):/);
    return {
      intro: introEnd > 0 ? text.slice(0, introEnd).trim() : "",
      priorities: timeboxed.map((m, i) => ({
        num: String(i + 1),
        label: m[1].trim(),
        topic: "",
        body: m[2].trim(),
      })),
    };
  }
  return { intro: text, priorities: [] };
}

const PRIORITY_PALETTE: Record<number, { bg: string; border: string; badge: string; num: string }> = {
  1: { bg: "bg-red-50",    border: "border-red-200",    badge: "bg-red-100 text-red-700",       num: "bg-red-500 text-white" },
  2: { bg: "bg-orange-50", border: "border-orange-200", badge: "bg-orange-100 text-orange-700", num: "bg-orange-500 text-white" },
  3: { bg: "bg-blue-50",   border: "border-blue-200",   badge: "bg-blue-100 text-blue-700",     num: "bg-blue-500 text-white" },
  4: { bg: "bg-purple-50", border: "border-purple-200", badge: "bg-purple-100 text-purple-700", num: "bg-purple-500 text-white" },
};

function PriorityCard({ num, label, topic, body }: { num: string; label: string; topic: string; body: string }) {
  const [expanded, setExpanded] = useState(false);
  const colors = PRIORITY_PALETTE[parseInt(num)] ?? PRIORITY_PALETTE[4];
  const sentenceEnd = body.search(/[.!?]\s/);
  const summary = sentenceEnd > 0 ? body.slice(0, sentenceEnd + 1) : body;
  const rest = sentenceEnd > 0 ? body.slice(sentenceEnd + 2).trim() : null;
  return (
    <div className={`rounded-xl border ${colors.border} ${colors.bg} p-4`}>
      <div className="flex items-start gap-3 mb-2">
        <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${colors.num}`}>{num}</span>
        <div className="flex-1 min-w-0">
          <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${colors.badge}`}>{label}</span>
          <h4 className="font-semibold text-gray-900 text-sm mt-1.5">{topic}</h4>
        </div>
      </div>
      <p className="text-sm text-gray-700 leading-relaxed pl-9">{summary}</p>
      {rest && (
        <>
          {expanded && <p className="text-sm text-gray-600 leading-relaxed pl-9 mt-2">{rest}</p>}
          <button onClick={() => setExpanded(!expanded)} className="pl-9 mt-1.5 text-xs text-blue-600 hover:underline">
            {expanded ? "Show less ↑" : "Read more ↓"}
          </button>
        </>
      )}
    </div>
  );
}

// ── Marketing sub-components ──────────────────────────────────────────────────

function MessagesToAvoid({ messages }: { messages: string[] }) {
  const [openIdx, setOpenIdx] = useState<number | null>(null);
  const parsed = messages.map(m => {
    const quoted = m.match(/^'([^']+)':\s*([\s\S]*)/);
    if (quoted) return { label: quoted[1], explanation: quoted[2].trim() };
    const colon = m.indexOf(": ");
    return colon > 0
      ? { label: m.slice(0, colon), explanation: m.slice(colon + 2) }
      : { label: m.slice(0, 60), explanation: m };
  });
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5">
      <h3 className="text-[10px] font-semibold text-red-500 uppercase tracking-wider mb-3">Messages to Avoid</h3>
      <div className="space-y-1.5">
        {parsed.map(({ label, explanation }, i) => (
          <div key={i} className="border border-red-100 rounded-lg overflow-hidden">
            <button
              onClick={() => setOpenIdx(openIdx === i ? null : i)}
              className="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-red-50/70 transition-colors"
            >
              <span className="text-red-400 text-xs flex-shrink-0">✗</span>
              <span className="text-sm font-medium text-gray-800 flex-1 text-left">'{label}'</span>
              <span className="text-xs text-gray-400 flex-shrink-0">{openIdx === i ? "↑" : "↓"}</span>
            </button>
            {openIdx === i && (
              <div className="px-4 pb-3 pt-0 bg-red-50/50 border-t border-red-100">
                <p className="text-xs text-gray-600 leading-relaxed pt-2">{explanation}</p>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function MarketingSection({ rec }: { rec: import("@/lib/api").MarketingRecommendation }) {
  const quoteMatch = rec.current_perception.match(/'([^']{10,80}?)'/);
  const dominantQuote = quoteMatch ? quoteMatch[1] : null;
  return (
    <div className="space-y-4">
      {/* Current perception */}
      <div className="bg-white border border-gray-200 rounded-xl p-5">
        <h3 className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-3">Customer Perception Today</h3>
        {dominantQuote && (
          <div className="flex items-start gap-3 bg-amber-50 border-l-4 border-amber-400 px-4 py-3 rounded-r-xl mb-3">
            <div>
              <p className="text-base font-semibold text-amber-900 italic leading-snug">"{dominantQuote}"</p>
              <p className="text-xs text-amber-600 mt-1">Dominant customer sentiment</p>
            </div>
          </div>
        )}
        <p className="text-sm text-gray-600 leading-relaxed">{rec.current_perception}</p>
      </div>

      {/* Value drivers as tags */}
      <div className="bg-white border border-gray-200 rounded-xl p-5">
        <h3 className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-3">Actual Value Drivers</h3>
        <div className="flex flex-wrap gap-2">
          {rec.actual_value_drivers.map((v, i) => {
            const dashIdx = v.indexOf(" — ");
            const label = dashIdx > 0 ? v.slice(0, dashIdx) : v;
            return (
              <span
                key={i}
                title={v}
                className="inline-flex items-center gap-1.5 bg-green-50 border border-green-200 text-green-800 text-sm font-medium px-3 py-1.5 rounded-full cursor-default"
              >
                <span className="text-green-500 text-xs">✓</span>
                {label}
              </span>
            );
          })}
        </div>
      </div>

      {/* Message proposals */}
      <div className="bg-white border border-gray-200 rounded-xl p-5">
        <h3 className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-3">Recommended Messages</h3>
        <div className="space-y-2">
          {rec.new_message_proposals.map((msg, i) => (
            <div key={i} className="flex items-start gap-3 p-3 bg-blue-50 rounded-lg">
              <span className="w-5 h-5 rounded-full bg-blue-600 text-white text-[10px] font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
                {i + 1}
              </span>
              <p className="text-sm text-blue-800 italic leading-relaxed">"{msg}"</p>
            </div>
          ))}
        </div>
      </div>

      <MessagesToAvoid messages={rec.messages_to_avoid} />
      <EvidenceQuotes quotes={rec.evidence} limit={2} />
    </div>
  );
}

function CompetitorCard({ comp }: { comp: import("@/lib/api").CompetitorData }) {
  const [expanded, setExpanded] = useState(false);
  const features: [string, string][] = [
    ["Picture", comp.picture_quality],
    ["Sound", comp.sound_quality],
    ["UX", comp.ux],
    ["Smart TV", comp.smart_features],
  ];
  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
        <div>
          <h3 className="font-semibold text-gray-900">{comp.name}</h3>
          <p className="text-xs text-gray-400 mt-0.5">{comp.model}</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-gray-600 bg-gray-100 px-2.5 py-1 rounded-lg">{comp.price_range}</span>
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-blue-600 hover:text-blue-800 font-medium"
          >
            {expanded ? "Less ↑" : "Details ↓"}
          </button>
        </div>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-y sm:divide-y-0 divide-gray-100">
        {features.map(([label, text]) => {
          const firstSentenceEnd = text.search(/[.!?]\s/);
          const headline = firstSentenceEnd > 0 ? text.slice(0, firstSentenceEnd + 1) : text;
          const rest = firstSentenceEnd > 0 ? text.slice(firstSentenceEnd + 2) : null;
          return (
            <div key={label} className="px-4 py-3">
              <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-1">{label}</p>
              <p className="text-xs text-gray-700 leading-relaxed">{headline}</p>
              {expanded && rest && (
                <p className="text-xs text-gray-500 mt-1 leading-relaxed">{rest}</p>
              )}
            </div>
          );
        })}
      </div>
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
        <ExecutiveSummarySection summary={result.executive_summary} insights={result.key_insights} />
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
                <div className="w-7 h-7 rounded-full bg-red-100 text-red-700 text-sm font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
                  {c.rank}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-2">
                    <span className="font-semibold text-gray-900">{c.category}</span>
                    <span className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">{c.aspect}</span>
                    <span className="text-xs text-red-600 font-medium">{c.frequency_pct.toFixed(1)}% of reviews</span>
                  </div>
                  <p className="text-sm text-gray-600 leading-relaxed">{c.root_cause}</p>
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

      {/* Task 9: Segment divergence */}
      {result.segment_divergence_analysis && result.segment_divergence_analysis.segment_insights.length > 0 && (
        <section>
          <SectionHeader number="9" title="Segment / Use-Case Divergence" badge="NEW" />
          <SegmentDivergenceSection
            items={result.segment_divergence_analysis.segment_insights}
            risks={result.segment_divergence_analysis.emerging_risks}
            opportunities={result.segment_divergence_analysis.emerging_opportunities}
            actions={result.segment_divergence_analysis.priority_actions}
          />
        </section>
      )}

      {/* Task 4: Marketing */}
      {result.marketing_recommendations && (
        <section>
          <SectionHeader number="4" title="Marketing Recommendations" />
          <MarketingSection rec={result.marketing_recommendations} />
        </section>
      )}

      {/* Task 5: Competitive Positioning */}
      {result.positioning_analysis && (
        <section>
          <SectionHeader number="5" title="Competitive Positioning" />
          <div className="space-y-5">
            <div className="grid sm:grid-cols-2 gap-4">
              <div className="bg-white border border-green-200 rounded-xl p-5">
                <div className="flex items-center gap-2 mb-4">
                  <span className="w-5 h-5 rounded-full bg-green-100 text-green-700 text-xs font-bold flex items-center justify-center">+</span>
                  <h3 className="text-sm font-semibold text-green-700">Samsung Strengths</h3>
                </div>
                <ul className="space-y-3">
                  {result.positioning_analysis.samsung_strengths.map((s, i) => {
                    const dot = s.indexOf(". ");
                    const headline = dot > 0 ? s.slice(0, dot + 1) : s;
                    const detail = dot > 0 ? s.slice(dot + 2) : null;
                    return (
                      <li key={i} className="pl-3 border-l-2 border-green-200">
                        <p className="text-sm font-medium text-gray-900 leading-snug">{headline}</p>
                        {detail && <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">{detail}</p>}
                      </li>
                    );
                  })}
                </ul>
              </div>
              <div className="bg-white border border-red-200 rounded-xl p-5">
                <div className="flex items-center gap-2 mb-4">
                  <span className="w-5 h-5 rounded-full bg-red-100 text-red-700 text-xs font-bold flex items-center justify-center">−</span>
                  <h3 className="text-sm font-semibold text-red-700">Samsung Weaknesses</h3>
                </div>
                <ul className="space-y-3">
                  {result.positioning_analysis.samsung_weaknesses.map((w, i) => {
                    const dot = w.indexOf(". ");
                    const headline = dot > 0 ? w.slice(0, dot + 1) : w;
                    const detail = dot > 0 ? w.slice(dot + 2) : null;
                    return (
                      <li key={i} className="pl-3 border-l-2 border-red-200">
                        <p className="text-sm font-medium text-gray-900 leading-snug">{headline}</p>
                        {detail && <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">{detail}</p>}
                      </li>
                    );
                  })}
                </ul>
              </div>
            </div>

            {result.positioning_analysis.competitors.map((comp) => (
              <CompetitorCard key={comp.name} comp={comp} />
            ))}

            {(() => {
              const { intro, priorities } = parsePositioningPriorities(
                result.positioning_analysis.positioning_recommendation
              );
              return priorities.length > 0 ? (
                <div>
                  <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Priority Action Areas</h3>
                  {intro && <p className="text-sm text-gray-600 leading-relaxed mb-4">{intro}</p>}
                  <div className="grid sm:grid-cols-2 gap-3">
                    {priorities.map(p => (
                      <PriorityCard key={p.num} {...p} />
                    ))}
                  </div>
                </div>
              ) : (
                <div className="bg-blue-50 border border-blue-200 rounded-xl p-5">
                  <h3 className="text-sm font-semibold text-blue-800 mb-2">Positioning Recommendation</h3>
                  <p className="text-sm text-blue-700 leading-relaxed">{result.positioning_analysis.positioning_recommendation}</p>
                </div>
              );
            })()}
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
