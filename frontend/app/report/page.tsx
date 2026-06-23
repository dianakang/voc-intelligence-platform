"use client";

import { useState, useEffect, Suspense } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { api, VOCResult, ExpectationGapItem, ContradictionCase, ImprovementPoint, SegmentInsight, CXActionItem, Complaint, SatisfactionDriver } from "@/lib/api";
import { SentimentPieChart } from "@/components/charts/SentimentPieChart";
import { AspectBarChart } from "@/components/charts/AspectBarChart";
import { ImportanceMatrix } from "@/components/charts/ImportanceMatrix";

interface SectionMeta {
  id: string;
  label: string;
  group: string;
  stat: (result: VOCResult) => string;
}

function pct(n: number, total: number) {
  return total === 0 ? 0 : Math.round((n / total) * 100);
}

function stripEmDashes<T>(value: T): T {
  if (typeof value === "string") {
    return value.replace(/\s*—\s*/g, ", ") as unknown as T;
  }
  if (Array.isArray(value)) {
    return value.map((v) => stripEmDashes(v)) as unknown as T;
  }
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      out[k] = stripEmDashes(v);
    }
    return out as T;
  }
  return value;
}

// A few fields use " — " as a deliberate label/explanation delimiter that
// downstream parsing splits on (see actual_value_drivers rendering and
// parsePositioningPriorities). Those are kept raw here; each consumer cleans
// its own derived output strings after splitting on the dash.
function sanitizeReport(raw: VOCResult): VOCResult {
  const sanitized = stripEmDashes(raw);
  return {
    ...sanitized,
    marketing_recommendations: raw.marketing_recommendations
      ? {
          ...sanitized.marketing_recommendations!,
          actual_value_drivers: raw.marketing_recommendations.actual_value_drivers,
        }
      : sanitized.marketing_recommendations,
    positioning_analysis: raw.positioning_analysis
      ? {
          ...sanitized.positioning_analysis!,
          positioning_recommendation: raw.positioning_analysis.positioning_recommendation,
          defend: raw.positioning_analysis.defend,
          differentiate: raw.positioning_analysis.differentiate,
          fix: raw.positioning_analysis.fix,
          monitor: raw.positioning_analysis.monitor,
        }
      : sanitized.positioning_analysis,
  };
}

// Splits "Headline — supporting detail" (or "Headline. detail" as a fallback)
// into a bold headline and a lighter detail line, the way samsung_strengths/
// weaknesses already render below the quadrant.
function splitHeadlineDetail(item: string): { headline: string; detail: string | null } {
  const dashIdx = item.indexOf(" — ");
  if (dashIdx > 0) {
    return { headline: stripEmDashes(item.slice(0, dashIdx)), detail: stripEmDashes(item.slice(dashIdx + 3)) };
  }
  const dot = item.indexOf(". ");
  if (dot > 0) {
    return { headline: stripEmDashes(item.slice(0, dot + 1)), detail: stripEmDashes(item.slice(dot + 2)) };
  }
  return { headline: stripEmDashes(item), detail: null };
}

const GROUP_VOC = "Voice of the Customer";
const GROUP_ACTIONS = "Recommended Actions";
const GROUP_STRATEGY = "Strategic Analysis";
const GROUP_DATA_QUALITY = "Data Quality Checks";

const SECTION_META: SectionMeta[] = [
  { id: "sentiment", label: "Sentiment Overview", group: GROUP_VOC, stat: (r) => `${pct(r.sentiment_distribution.positive ?? 0, r.total_reviews)}% positive overall` },
  {
    id: "complaints",
    label: "Top Complaints",
    group: GROUP_VOC,
    stat: (r) => {
      const product = r.complaints.filter((c) => c.issue_type !== "purchase_experience").length;
      const purchase = r.complaints.length - product;
      return `${r.complaints.length} complaints · ${product} product / ${purchase} purchase`;
    },
  },
  { id: "satisfaction", label: "Satisfaction Drivers", group: GROUP_VOC, stat: (r) => `${r.satisfaction_drivers.length} drivers identified` },
  {
    id: "improvements",
    label: "Improvement Priorities",
    group: GROUP_ACTIONS,
    stat: (r) => `${r.improvement_points.length} priorities · ${r.improvement_points.filter((p) => p.priority === "high").length} high priority`,
  },
  { id: "marketing", label: "Marketing Recommendations", group: GROUP_ACTIONS, stat: () => "Messaging and positioning ideas" },
  {
    id: "cx-actions",
    label: "CX Action Toolkit",
    group: GROUP_ACTIONS,
    stat: (r) => `${r.cx_actions?.length ?? 0} action items ready`,
  },
  { id: "positioning", label: "Competitive Positioning", group: GROUP_STRATEGY, stat: (r) => `${r.positioning_analysis?.competitors.length ?? 0} competitors compared` },
  {
    id: "segment-divergence",
    label: "Segment / Use-Case Divergence",
    group: GROUP_STRATEGY,
    stat: (r) => `${r.segment_divergence_analysis?.segment_insights.length ?? 0} segments analyzed`,
  },
  { id: "importance", label: "Importance-Frequency Matrix", group: GROUP_STRATEGY, stat: (r) => `${r.importance_matrix.length} issues ranked by priority` },
  {
    id: "contradictions",
    label: "Paradox Reviews",
    group: GROUP_DATA_QUALITY,
    stat: (r) => {
      const product = r.contradictions.filter((c) => c.counts_as_product_issue).length;
      return `${r.contradictions.length} cases found · ${product} count as product issues`;
    },
  },
  {
    id: "expectation-gaps",
    label: "Customer Expectation Gap Analysis",
    group: GROUP_DATA_QUALITY,
    stat: (r) => `${r.expectation_gaps.length} gaps · ${r.expectation_gaps.filter((g) => g.gap_severity === "high").length} high severity`,
  },
];

function activeSections(result: VOCResult): SectionMeta[] {
  return SECTION_META.filter((s) => {
    if (s.id === "segment-divergence") return !!result.segment_divergence_analysis && result.segment_divergence_analysis.segment_insights.length > 0;
    if (s.id === "marketing") return !!result.marketing_recommendations;
    if (s.id === "positioning") return !!result.positioning_analysis;
    if (s.id === "cx-actions") return !!result.cx_actions && result.cx_actions.length > 0;
    return true;
  });
}

function IssueTypeFilter({
  value,
  onChange,
}: {
  value: "all" | "product" | "purchase";
  onChange: (v: "all" | "product" | "purchase") => void;
}) {
  const options: { key: "all" | "product" | "purchase"; label: string }[] = [
    { key: "all", label: "All" },
    { key: "product", label: "Product Issues" },
    { key: "purchase", label: "Purchase Experience" },
  ];
  return (
    <div className="flex items-center gap-2 mb-4">
      {options.map((o) => (
        <button
          key={o.key}
          onClick={() => onChange(o.key)}
          className={`text-xs font-medium px-3 py-1.5 rounded-full border transition-colors ${
            value === o.key
              ? o.key === "product"
                ? "bg-red-50 text-red-700 border-red-200"
                : o.key === "purchase"
                ? "bg-gray-100 text-gray-700 border-gray-300"
                : "bg-brand-600 text-white border-brand-600"
              : "bg-white text-gray-500 border-gray-200 hover:bg-gray-50"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

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
      <div className="w-8 h-8 rounded-full bg-brand-600 text-white text-sm font-bold flex items-center justify-center flex-shrink-0">
        {number}
      </div>
      <h2 className="text-xl font-bold text-gray-900">{title}</h2>
      {badge && <span className="text-xs bg-brand-100 text-brand-700 px-2 py-0.5 rounded-full font-semibold">{badge}</span>}
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
        <button onClick={() => setExpanded(!expanded)} className="text-xs text-brand-500 hover:underline">
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
          {gap.gap_description && (
            <p className="text-xs text-gray-500 leading-relaxed">
              <span className="font-medium text-gray-700">Why it matters: </span>{gap.gap_description}
            </p>
          )}
          <div className="p-3 bg-brand-50 rounded-lg">
            <p className="text-[10px] font-semibold text-brand-500 uppercase tracking-wider mb-1">Recommended Action</p>
            <p className="text-sm text-brand-800 leading-relaxed">{gap.recommended_action}</p>
          </div>
          <EvidenceQuotes quotes={gap.supporting_reviews} limit={2} />
        </div>
      )}

      {/* Recommended action teaser when collapsed */}
      {!open && (
        <div className="border-t border-gray-100 px-5 py-2.5 bg-brand-50/50">
          <p className="text-xs text-brand-700 leading-snug line-clamp-1">
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

const QUADRANT_BOXES: { key: "defend" | "differentiate" | "fix" | "monitor"; label: string; hint: string }[] = [
  { key: "defend", label: "Defend", hint: "Already winning, so protect it" },
  { key: "differentiate", label: "Differentiate", hint: "Winning, underleveraged in marketing" },
  { key: "fix", label: "Fix", hint: "Losing, a purchase barrier or trust risk" },
  { key: "monitor", label: "Monitor", hint: "Lower volume but high severity, worth watching" },
];

function QuadrantItem({ item }: { item: string }) {
  const [expanded, setExpanded] = useState(false);
  const { headline, detail } = splitHeadlineDetail(item);
  const snippet = detail ? firstSentence(detail) : null;
  const hasMore = !!detail && snippet !== detail;
  return (
    <li className="pl-2.5 border-l-2 border-brand-100">
      <p className="text-xs font-semibold text-gray-900 leading-snug">{headline}</p>
      {detail && (
        <p className="text-[11px] text-gray-500 mt-0.5 leading-relaxed">{expanded ? detail : snippet}</p>
      )}
      {hasMore && (
        <button onClick={() => setExpanded(!expanded)} className="text-[11px] text-brand-600 hover:underline mt-0.5">
          {expanded ? "Show less ↑" : "Read more ↓"}
        </button>
      )}
    </li>
  );
}

function ExecutiveQuadrant({ analysis }: { analysis: import("@/lib/api").PositioningAnalysis }) {
  return (
    <div>
      <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Executive Summary</h3>
      <div className="grid sm:grid-cols-2 gap-3">
        {QUADRANT_BOXES.map(({ key, label, hint }) => {
          const items = analysis[key];
          return (
            <div key={key} className="bg-white border border-brand-200 rounded-xl p-4">
              <p className="text-sm font-semibold text-brand-800">{label}</p>
              <p className="text-[11px] text-gray-400 mb-2">{hint}</p>
              {items.length > 0 ? (
                <ul className="space-y-2">
                  {items.map((item, i) => (
                    <QuadrantItem key={i} item={item} />
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-gray-300">None</p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

const ASSESSMENT_STYLES: Record<string, string> = {
  win: "bg-green-100 text-green-700",
  lose: "bg-red-100 text-red-700",
  mixed: "bg-yellow-100 text-yellow-700",
  neutral: "bg-gray-100 text-gray-500",
};

function PositioningMapTable({ attributes }: { attributes: import("@/lib/api").PositioningAttribute[] }) {
  return (
    <div>
      <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Customer Voice Positioning Map</h3>
      <div className="overflow-x-auto bg-white border border-gray-200 rounded-xl">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-gray-200 text-left text-gray-400">
              <th className="px-3 py-2 font-medium">Attribute</th>
              <th className="px-3 py-2 font-medium">Samsung</th>
              <th className="px-3 py-2 font-medium">Volume</th>
              <th className="px-3 py-2 font-medium">Sentiment</th>
              <th className="px-3 py-2 font-medium">Business Impact</th>
              <th className="px-3 py-2 font-medium">vs. Competitors</th>
            </tr>
          </thead>
          <tbody>
            {attributes.map((a, i) => (
              <tr key={i} className="border-b border-gray-100 last:border-0">
                <td className="px-3 py-2 font-medium text-gray-900">{a.attribute}</td>
                <td className="px-3 py-2">
                  <span className={`px-2 py-0.5 rounded-full text-[11px] font-semibold ${ASSESSMENT_STYLES[a.samsung_assessment] ?? ASSESSMENT_STYLES.neutral}`}>
                    {a.samsung_assessment.toUpperCase()}
                  </span>
                </td>
                <td className="px-3 py-2 text-gray-600 capitalize">{a.mention_volume}</td>
                <td className={`px-3 py-2 font-medium ${a.sentiment_score >= 0 ? "text-green-600" : "text-red-600"}`}>
                  {a.sentiment_score >= 0 ? "+" : ""}{a.sentiment_score.toFixed(2)}
                </td>
                <td className="px-3 py-2 text-gray-600">{a.business_impact.replace(/_/g, " ")}</td>
                <td className="px-3 py-2 text-gray-500">{a.vs_competitor_note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const MISMATCH_CATEGORY_LABEL: Record<string, string> = {
  hidden_complaint: "Hidden product complaint",
  accidental_low_rating: "Likely accidental rating",
  service_failure_with_product_praise: "Service failure, product praised",
  non_product_issue: "Non-product issue",
};

const ROUTE_TO_LABEL: Record<string, string> = {
  product_engineering: "Route to: Product / Engineering",
  cx_fulfillment_warranty: "Route to: CX / Fulfillment / Warranty",
  marketing_cs_followup: "Route to: Marketing / CS follow-up",
  no_action_needed: "No action needed",
};

function ContradictionCard({ c }: { c: ContradictionCase }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-start gap-3 px-5 py-4 text-left hover:bg-gray-50 transition-colors"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <div className={`text-xs font-bold px-2 py-0.5 rounded-full ${c.contradiction_type === "type_a" ? "bg-orange-100 text-orange-700" : "bg-brand-100 text-brand-700"}`}>
              {c.contradiction_type === "type_a" ? "High rating, hidden complaint" : "Low rating, praises product"}
            </div>
            {c.mismatch_category && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 border border-gray-200">
                {MISMATCH_CATEGORY_LABEL[c.mismatch_category] || c.mismatch_category.replace(/_/g, " ")}
              </span>
            )}
            <span
              className={`text-[10px] px-1.5 py-0.5 rounded border ${
                c.counts_as_product_issue
                  ? "bg-red-50 text-red-600 border-red-100"
                  : "bg-green-50 text-green-600 border-green-100"
              }`}
            >
              {c.counts_as_product_issue ? "Counts as product issue" : "Excluded from product metrics"}
            </span>
            <div className="flex gap-0.5 ml-auto flex-shrink-0">
              {Array.from({ length: 5 }).map((_, j) => (
                <span key={j} className={j < c.rating ? "text-yellow-400" : "text-gray-200"}>★</span>
              ))}
            </div>
          </div>
          <p className="text-sm text-gray-600 italic line-clamp-1">"{c.review_text}"</p>
        </div>
        <span className="text-xs text-gray-400 flex-shrink-0 mt-1">{open ? "↑" : "↓"}</span>
      </button>
      {open && (
        <div className="border-t border-gray-100 px-5 py-4 space-y-3">
          <blockquote className="text-sm text-gray-700 italic border-l-2 border-gray-300 pl-3">
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
            <p className="text-xs text-gray-500 italic">{c.implication}</p>
          )}
          {c.route_to && (
            <p className="text-xs text-gray-600">
              <span className="font-medium text-gray-700">{ROUTE_TO_LABEL[c.route_to] || c.route_to}</span>
            </p>
          )}
          {c.suggested_public_response && (
            <div className="bg-brand-50 border border-brand-100 rounded-lg p-3">
              <p className="text-[11px] font-semibold text-brand-700 uppercase tracking-wide mb-1">Suggested public response</p>
              <p className="text-xs text-gray-700 leading-relaxed">{c.suggested_public_response}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ContradictionSection({ cases }: { cases: ContradictionCase[] }) {
  const [expanded, setExpanded] = useState(false);
  if (cases.length === 0) {
    return <p className="text-sm text-gray-400">No contradictions detected.</p>;
  }
  const limit = 4;
  const visible = expanded ? cases : cases.slice(0, limit);
  return (
    <div className="space-y-3">
      {visible.map((c, i) => <ContradictionCard key={i} c={c} />)}
      {cases.length > limit && (
        <button onClick={() => setExpanded(!expanded)} className="text-xs text-brand-600 hover:underline">
          {expanded ? "Show less ↑" : `Show ${cases.length - limit} more ↓`}
        </button>
      )}
    </div>
  );
}

function ImprovementCard({ imp }: { imp: ImprovementPoint }) {
  const [expanded, setExpanded] = useState(false);
  const snippet = firstSentence(imp.expected_effect);
  const hasMore = snippet !== imp.expected_effect;
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5">
      <div className="flex items-start justify-between gap-2 mb-2">
        <h3 className="font-semibold text-gray-900">{imp.area}</h3>
        <PriorityBadge priority={imp.priority} />
      </div>
      <p className="text-sm text-gray-700">{expanded ? imp.expected_effect : snippet}</p>
      {hasMore && (
        <button onClick={() => setExpanded(!expanded)} className="text-xs text-brand-600 hover:underline mt-1 mb-1 block">
          {expanded ? "Show less ↑" : "Read more ↓"}
        </button>
      )}
      <div className="flex items-center gap-4 text-xs text-gray-500 mt-2">
        <span>Frequency: {imp.frequency} mentions</span>
        <span>Impact score: {imp.impact_score}/10</span>
      </div>
      <EvidenceQuotes quotes={imp.supporting_evidence} />
    </div>
  );
}

function ImprovementSection({ improvements }: { improvements: ImprovementPoint[] }) {
  const [expanded, setExpanded] = useState(false);
  const limit = 4;
  const visible = expanded ? improvements : improvements.slice(0, limit);
  return (
    <div className="space-y-3">
      {visible.map((imp, i) => <ImprovementCard key={i} imp={imp} />)}
      {improvements.length > limit && (
        <button onClick={() => setExpanded(!expanded)} className="text-xs text-brand-600 hover:underline">
          {expanded ? "Show less ↑" : `Show ${improvements.length - limit} more ↓`}
        </button>
      )}
    </div>
  );
}

const ACTION_TYPE_LABELS: Record<string, string> = {
  faq: "FAQ",
  support_script: "Support Script",
  proactive_notice: "Proactive Notice",
  install_guide: "Install Guide",
};

function CXActionCard({ action }: { action: CXActionItem }) {
  const [open, setOpen] = useState(false);
  const snippet = firstSentence(action.content);
  const hasMore = snippet !== action.content;
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5">
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs font-semibold bg-brand-100 text-brand-700 px-2 py-0.5 rounded-full">
            {ACTION_TYPE_LABELS[action.action_type] || action.action_type}
          </span>
          <span
            className={`text-xs px-1.5 py-0.5 rounded font-medium ${
              action.issue_type === "purchase_experience" ? "bg-gray-100 text-gray-600" : "bg-red-50 text-red-600"
            }`}
          >
            {action.issue_type === "purchase_experience" ? "Purchase Experience" : "Product Issue"}
          </span>
        </div>
        <PriorityBadge priority={action.priority} />
      </div>
      <h3 className="font-semibold text-gray-900 text-sm mb-1.5">{action.title}</h3>
      <p className="text-sm text-gray-700 leading-relaxed">{open ? action.content : snippet}</p>
      {hasMore && (
        <button onClick={() => setOpen(!open)} className="text-xs text-brand-600 hover:underline mt-1.5">
          {open ? "Show less ↑" : "Read more ↓"}
        </button>
      )}
      <p className="text-xs text-gray-400 mt-2">Addresses: {action.related_issue}</p>
    </div>
  );
}

function CXActionSection({ actions }: { actions: CXActionItem[] }) {
  if (actions.length === 0) {
    return <p className="text-sm text-gray-400">No CX actions generated.</p>;
  }
  return (
    <div className="grid sm:grid-cols-2 gap-4">
      {actions.map((action, i) => (
        <CXActionCard key={i} action={action} />
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
          <div className="p-3 bg-brand-50 rounded-lg">
            <p className="text-[10px] font-semibold text-brand-500 uppercase tracking-wider mb-1">Recommended Action</p>
            <p className="text-sm text-brand-800 leading-relaxed">{item.recommended_action}</p>
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
  const [insightsExpanded, setInsightsExpanded] = useState(false);
  const paragraphs = parseParagraphs(summary);
  const visible = expanded ? paragraphs : paragraphs.slice(0, 2);
  const cleanInsights = insights.filter(i => i.trim().length > 10);
  const insightsLimit = 4;
  const visibleInsights = insightsExpanded ? cleanInsights : cleanInsights.slice(0, insightsLimit);

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
            className="mt-3 text-xs text-brand-600 hover:underline"
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
            {visibleInsights.map((raw, i) => {
              const { headline, detail } = parseInsight(raw);
              return (
                <div key={i} className="flex items-start gap-3 p-3 bg-gray-50 rounded-lg">
                  <span className="w-5 h-5 rounded-full bg-brand-600 text-white text-[10px] font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
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
          {cleanInsights.length > insightsLimit && (
            <button
              onClick={() => setInsightsExpanded(!insightsExpanded)}
              className="mt-3 text-xs text-brand-600 hover:underline"
            >
              {insightsExpanded ? "Show less ↑" : `Show ${cleanInsights.length - insightsLimit} more insights ↓`}
            </button>
          )}
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
    return stripEmDashes({
      intro: introEnd > 0 ? text.slice(0, introEnd).trim() : "",
      priorities: numbered.map((m, i) => ({
        num: String(i + 1),
        label: m[2].trim(),
        topic: m[3].trim(),
        body: m[4].trim(),
      })),
    });
  }
  // Try format: TIMEFRAME (period): text  e.g. "IMMEDIATE (0-3 months):"
  const timeboxed = [...text.matchAll(/([A-Z][A-Z\s-]+?)\s*\([^)]+\):\s*([\s\S]*?)(?=[A-Z]{3,}[^a-z]*\([^)]+\):|$)/g)];
  if (timeboxed.length > 0) {
    const introEnd = text.search(/[A-Z]{3,}[^a-z]*\([^)]+\):/);
    return stripEmDashes({
      intro: introEnd > 0 ? text.slice(0, introEnd).trim() : "",
      priorities: timeboxed.map((m, i) => ({
        num: String(i + 1),
        label: m[1].trim(),
        topic: "",
        body: m[2].trim(),
      })),
    });
  }
  return stripEmDashes({ intro: text, priorities: [] });
}

const PRIORITY_PALETTE: Record<number, { bg: string; border: string; badge: string; num: string }> = {
  1: { bg: "bg-red-50",    border: "border-red-200",    badge: "bg-red-100 text-red-700",       num: "bg-red-500 text-white" },
  2: { bg: "bg-orange-50", border: "border-orange-200", badge: "bg-orange-100 text-orange-700", num: "bg-orange-500 text-white" },
  3: { bg: "bg-brand-50",   border: "border-brand-200",   badge: "bg-brand-100 text-brand-700",     num: "bg-brand-500 text-white" },
  4: { bg: "bg-gray-50",   border: "border-gray-200",   badge: "bg-gray-100 text-gray-700",     num: "bg-gray-500 text-white" },
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
          <button onClick={() => setExpanded(!expanded)} className="pl-9 mt-1.5 text-xs text-brand-600 hover:underline">
            {expanded ? "Show less ↑" : "Read more ↓"}
          </button>
        </>
      )}
    </div>
  );
}

// ── Marketing sub-components ──────────────────────────────────────────────────

function TargetAudienceProfileCard({ profile }: { profile: import("@/lib/api").TargetAudienceProfile }) {
  const [expanded, setExpanded] = useState(false);
  const snippet = firstSentence(profile.why_product_fits);
  const hasMore = snippet !== profile.why_product_fits;
  return (
    <div className="border border-gray-200 rounded-lg p-4">
      <h4 className="text-sm font-semibold text-gray-900">{profile.persona_name}</h4>
      <p className="text-xs text-brand-600 font-medium mt-0.5 mb-2 line-clamp-2">{profile.demographic_profile}</p>

      {profile.psychographic_traits.length > 0 && (
        <ul className="text-xs text-gray-600 space-y-1 mb-3 list-disc list-inside marker:text-gray-300">
          {profile.psychographic_traits.slice(0, 3).map((t, i) => (
            <li key={i}>{t}</li>
          ))}
        </ul>
      )}

      <p className="text-sm text-gray-700 leading-relaxed">{expanded ? profile.why_product_fits : snippet}</p>
      {hasMore && (
        <button onClick={() => setExpanded(!expanded)} className="text-xs text-brand-600 hover:underline mt-1 mb-2 block">
          {expanded ? "Show less ↑" : "Read more ↓"}
        </button>
      )}

      {profile.recommended_channels.length > 0 && (
        <div className="mt-2 mb-2">
          <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-1">Best reached via</p>
          <ul className="text-xs text-gray-600 space-y-0.5 list-disc list-inside marker:text-gray-300">
            {profile.recommended_channels.slice(0, 2).map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      )}

      <EvidenceQuotes quotes={profile.evidence} limit={1} />
    </div>
  );
}

function TargetAudienceSection({ profiles }: { profiles: import("@/lib/api").TargetAudienceProfile[] }) {
  if (profiles.length === 0) {
    return <p className="text-sm text-gray-400">No target audience data generated.</p>;
  }
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5">
      <h3 className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-3">Target Audience</h3>
      <div className="grid sm:grid-cols-2 gap-3">
        {profiles.map((p, i) => (
          <TargetAudienceProfileCard key={i} profile={p} />
        ))}
      </div>
    </div>
  );
}

function MarketingSection({ rec }: { rec: import("@/lib/api").MarketingRecommendation }) {
  // The lookbehind-style `(?:^|\s)` keeps this from matching apostrophes in
  // contractions/possessives (e.g. "brand's"), which always sit right after a letter.
  const quoteMatch = rec.current_perception.match(/(?:^|\s)'([^']{6,80}?)'(?=[\s,.;:!?]|$)/);
  const dominantQuote = quoteMatch ? stripEmDashes(quoteMatch[1]) : null;
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
                title={stripEmDashes(v)}
                className="inline-flex items-center gap-1.5 bg-green-50 border border-green-200 text-green-800 text-sm font-medium px-3 py-1.5 rounded-full cursor-default"
              >
                <span className="text-green-500 text-xs">✓</span>
                {stripEmDashes(label)}
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
            <div key={i} className="flex items-start gap-3 p-3 bg-brand-50 rounded-lg">
              <span className="w-5 h-5 rounded-full bg-brand-600 text-white text-[10px] font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
                {i + 1}
              </span>
              <p className="text-sm text-brand-800 italic leading-relaxed">"{msg}"</p>
            </div>
          ))}
        </div>
      </div>

      <TargetAudienceSection profiles={rec.target_audience} />
    </div>
  );
}

function CompetitorCard({ comp }: { comp: import("@/lib/api").CompetitorData }) {
  const [expanded, setExpanded] = useState(false);
  const features: [string, string][] = [
    ["UX", comp.ux],
    ...Object.entries(comp.key_attributes),
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
            className="text-xs text-brand-600 hover:text-brand-800 font-medium"
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

function ComplaintCard({ c }: { c: Complaint }) {
  const [expanded, setExpanded] = useState(false);
  const snippet = firstSentence(c.root_cause);
  const hasMore = snippet !== c.root_cause;
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5">
      <div className="flex items-start gap-3">
        <div className="w-7 h-7 rounded-full bg-red-100 text-red-700 text-sm font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
          {c.rank}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-2">
            <span className="font-semibold text-gray-900">{c.category}</span>
            <span className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">{c.aspect}</span>
            <span
              className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                c.issue_type === "purchase_experience" ? "bg-gray-100 text-gray-600" : "bg-red-50 text-red-600"
              }`}
            >
              {c.issue_type === "purchase_experience" ? "Purchase Experience" : "Product Issue"}
            </span>
            <span className="text-xs text-red-600 font-medium">{c.frequency_pct.toFixed(1)}% of reviews</span>
          </div>
          <p className="text-sm text-gray-600 leading-relaxed">{expanded ? c.root_cause : snippet}</p>
          {hasMore && (
            <button onClick={() => setExpanded(!expanded)} className="text-xs text-brand-600 hover:underline mt-1 mb-1 block">
              {expanded ? "Show less ↑" : "Read more ↓"}
            </button>
          )}
          <EvidenceQuotes quotes={c.representative_reviews} />
        </div>
      </div>
    </div>
  );
}

function SatisfactionDriverCard({ d }: { d: SatisfactionDriver }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5">
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
  );
}

function SectionAccordion({
  result,
  activeSection,
  onToggleSection,
}: {
  result: VOCResult;
  activeSection: string | null;
  onToggleSection: (id: string) => void;
}) {
  const [complaintsFilter, setComplaintsFilter] = useState<"all" | "product" | "purchase">("all");
  const [paradoxFilter, setParadoxFilter] = useState<"all" | "product" | "purchase">("all");
  const [cxFilter, setCxFilter] = useState<"all" | "product" | "purchase">("all");
  const [complaintsExpanded, setComplaintsExpanded] = useState(false);
  const [satisfactionExpanded, setSatisfactionExpanded] = useState(false);
  const LIST_LIMIT = 4;

  const filteredComplaints = result.complaints.filter((c) =>
    complaintsFilter === "all" ? true : complaintsFilter === "product" ? c.issue_type !== "purchase_experience" : c.issue_type === "purchase_experience"
  );
  const filteredContradictions = result.contradictions.filter((c) =>
    paradoxFilter === "all" ? true : paradoxFilter === "product" ? c.counts_as_product_issue : !c.counts_as_product_issue
  );
  const filteredCxActions = (result.cx_actions ?? []).filter((a) =>
    cxFilter === "all" ? true : cxFilter === "product" ? a.issue_type !== "purchase_experience" : a.issue_type === "purchase_experience"
  );

  return (
    <div>
      <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Explore the Report</h2>
      <div className="divide-y divide-gray-100 bg-white border border-gray-200 rounded-xl overflow-hidden">
        {activeSections(result).map((s, i, arr) => {
          const sectionId = s.id;
          const isOpen = activeSection === sectionId;
          const showGroupHeader = i === 0 || arr[i - 1].group !== s.group;
          return (
            <div key={sectionId}>
              {showGroupHeader && (
                <div className="px-5 pt-4 pb-1.5 bg-gray-50/60">
                  <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">{s.group}</p>
                </div>
              )}
              <button
                onClick={() => onToggleSection(sectionId)}
                className="w-full flex items-center justify-between gap-4 px-5 py-4 text-left hover:bg-gray-50 transition-colors"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-7 h-7 rounded-full bg-brand-100 text-brand-700 text-xs font-bold flex items-center justify-center flex-shrink-0">
                    {i + 1}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-gray-900">{s.label}</p>
                    <p className="text-xs text-gray-500 mt-0.5 truncate">{s.stat(result)}</p>
                  </div>
                </div>
                <span className="text-gray-400 text-sm flex-shrink-0">{isOpen ? "↑" : "↓"}</span>
              </button>
              {isOpen && (
                <div className="px-5 pb-6 pt-1 bg-gray-50/40 border-t border-gray-100">

      {sectionId === "sentiment" && (
        <section>
          <div className="grid sm:grid-cols-2 gap-5">
            <div className="bg-white border border-gray-200 rounded-xl p-5">
              <h3 className="text-sm font-semibold text-gray-700 mb-4">Overall Sentiment</h3>
              <SentimentPieChart data={Object.entries(result.sentiment_distribution).map(([name, value]) => ({ name, value }))} />
            </div>
            <div className="bg-white border border-gray-200 rounded-xl p-5">
              <h3 className="text-sm font-semibold text-gray-700 mb-4">Aspect Sentiment Breakdown</h3>
              <AspectBarChart
                data={Object.entries(result.aspect_sentiment_summary)
                  .map(([aspect, s]) => ({ aspect, positive: s.positive, negative: s.negative, neutral: s.neutral }))
                  .sort((a, b) => (b.positive + b.negative + b.neutral) - (a.positive + a.negative + a.neutral))}
              />
            </div>
          </div>
        </section>
      )}

      {sectionId === "complaints" && (
        <section>
          <p className="text-xs text-gray-500 mb-4">
            Tagged by type: <span className="font-semibold text-red-600">Product Issue</span> (a defect routed to engineering)
            vs. <span className="font-semibold text-gray-600">Purchase Experience</span> (delivery, account, or setup issues routed to CX).
          </p>
          <IssueTypeFilter value={complaintsFilter} onChange={setComplaintsFilter} />
          <div className="space-y-3">
            {(complaintsExpanded ? filteredComplaints : filteredComplaints.slice(0, LIST_LIMIT)).map((c) => (
              <ComplaintCard key={c.rank} c={c} />
            ))}
            {filteredComplaints.length === 0 && <p className="text-sm text-gray-400">No complaints match this filter.</p>}
            {filteredComplaints.length > LIST_LIMIT && (
              <button onClick={() => setComplaintsExpanded(!complaintsExpanded)} className="text-xs text-brand-600 hover:underline">
                {complaintsExpanded ? "Show less ↑" : `Show ${filteredComplaints.length - LIST_LIMIT} more ↓`}
              </button>
            )}
          </div>
        </section>
      )}

      {sectionId === "satisfaction" && (
        <section>
          <div className="space-y-3">
            {(satisfactionExpanded ? result.satisfaction_drivers : result.satisfaction_drivers.slice(0, LIST_LIMIT)).map((d) => (
              <SatisfactionDriverCard key={d.rank} d={d} />
            ))}
            {result.satisfaction_drivers.length > LIST_LIMIT && (
              <button onClick={() => setSatisfactionExpanded(!satisfactionExpanded)} className="text-xs text-brand-600 hover:underline">
                {satisfactionExpanded ? "Show less ↑" : `Show ${result.satisfaction_drivers.length - LIST_LIMIT} more ↓`}
              </button>
            )}
          </div>
        </section>
      )}

      {sectionId === "improvements" && (
        <section>
          <ImprovementSection improvements={result.improvement_points} />
        </section>
      )}

      {sectionId === "segment-divergence" && result.segment_divergence_analysis && result.segment_divergence_analysis.segment_insights.length > 0 && (
        <section>
          <SegmentDivergenceSection
            items={result.segment_divergence_analysis.segment_insights}
            risks={result.segment_divergence_analysis.emerging_risks}
            opportunities={result.segment_divergence_analysis.emerging_opportunities}
            actions={result.segment_divergence_analysis.priority_actions}
          />
        </section>
      )}

      {sectionId === "marketing" && result.marketing_recommendations && (
        <section>
          <MarketingSection rec={result.marketing_recommendations} />
        </section>
      )}

      {sectionId === "positioning" && result.positioning_analysis && (
        <section>
          <div className="space-y-5">
            {result.positioning_analysis.attribute_map.length > 0 && (
              <>
                <ExecutiveQuadrant analysis={result.positioning_analysis} />
                <PositioningMapTable attributes={result.positioning_analysis.attribute_map} />
              </>
            )}
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
                <div className="bg-brand-50 border border-brand-200 rounded-xl p-5">
                  <h3 className="text-sm font-semibold text-brand-800 mb-2">Positioning Recommendation</h3>
                  <p className="text-sm text-brand-700 leading-relaxed">{stripEmDashes(result.positioning_analysis.positioning_recommendation)}</p>
                </div>
              );
            })()}
          </div>
        </section>
      )}

      {sectionId === "contradictions" && (
        <section>
          <p className="text-xs text-gray-500 mb-4">
            A star rating doesn't always reflect product quality. These reviews separate <span className="font-semibold text-gray-700">emotional rating</span> from
            <span className="font-semibold text-gray-700"> actual product experience</span>, which helps tell roadmap priorities apart from service fixes.
          </p>
          <IssueTypeFilter value={paradoxFilter} onChange={setParadoxFilter} />
          <ContradictionSection cases={filteredContradictions} />
        </section>
      )}

      {sectionId === "importance" && (
        <section>
          <p className="text-xs text-gray-500 mb-4">
            Each dot is an issue, plotted by how often it's mentioned (x-axis) against its business impact
            (y-axis). Defects that drive returns or warranty claims score high impact even if rarely
            mentioned, while common-but-minor annoyances score low impact even at high frequency. The number
            on each dot matches its rank in the priority list below, which orders every issue by overall
            priority and points to where its fix is already detailed elsewhere in this report (Expectation
            Gaps, CX Actions), or gives a new recommendation if nothing covers it yet.
          </p>
          <div className="bg-white border border-gray-200 rounded-xl p-5">
            <ImportanceMatrix data={result.importance_matrix} />
          </div>
        </section>
      )}

      {sectionId === "expectation-gaps" && (
        <section>
          {(() => {
            const nonProductMismatches = result.contradictions.filter((c) => !c.counts_as_product_issue);
            if (nonProductMismatches.length === 0) return null;
            return (
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-4 text-xs text-amber-800">
                <span className="font-semibold">{nonProductMismatches.length} flagged rating/text mismatch{nonProductMismatches.length > 1 ? "es are" : " is"} excluded</span> from
                the gaps below. These are reviews where the product itself was praised but the rating was low for
                an unrelated reason (delivery, warranty, support, or likely a mistaken rating), so they're tracked as
                contradictions rather than genuine expectation gaps.{" "}
                <button onClick={() => onToggleSection("contradictions")} className="underline font-medium">See Paradox Reviews →</button>
              </div>
            );
          })()}
          <ExpectationGapSection gaps={result.expectation_gaps} />
        </section>
      )}

      {sectionId === "cx-actions" && result.cx_actions && result.cx_actions.length > 0 && (
        <section>
          <p className="text-xs text-gray-500 mb-4">
            Ready-to-use <span className="font-semibold text-gray-700">FAQ entries, support scripts, and proactive notices</span> generated
            directly from the complaint clusters above, ready for customer support and help-center publishing.
          </p>
          <IssueTypeFilter value={cxFilter} onChange={setCxFilter} />
          <CXActionSection actions={filteredCxActions} />
        </section>
      )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ReportContent({
  result,
  activeSection,
  onSelectSection,
}: {
  result: VOCResult;
  activeSection: string | null;
  onSelectSection: (id: string | null) => void;
}) {
  return (
    <div className="space-y-8">
      {/* Hero */}
      <div className="bg-gradient-to-r from-brand-600 to-brand-700 rounded-2xl p-6 text-white">
        <h1 className="text-2xl font-bold mb-1">{result.model}</h1>
        <p className="text-brand-100 text-sm mb-4">{new Date(result.analysis_date).toLocaleDateString()} · {result.total_reviews} reviews</p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            ["Avg Rating", `${result.avg_rating.toFixed(1)} / 5.0`],
            [
              "Total Reviews",
              result.total_reviews_available > result.total_reviews
                ? `${result.total_reviews.toLocaleString()} of ${result.total_reviews_available.toLocaleString()}`
                : result.total_reviews.toLocaleString(),
            ],
            ["Complaint Issues", result.complaints.length.toString()],
            ["Expectation Gaps", result.expectation_gaps.length.toString()],
          ].map(([label, value]) => (
            <div key={label} className="bg-brand-500/30 rounded-xl p-3">
              <p className="text-xs text-brand-200">{label}</p>
              <p className="text-xl font-bold">{value}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Executive Summary always visible as the orienting section */}
      <section>
        <SectionHeader number="1" title="Executive Summary" />
        <ExecutiveSummarySection summary={result.executive_summary} insights={result.key_insights} />
      </section>

      <SectionAccordion
        result={result}
        activeSection={activeSection}
        onToggleSection={(id) => onSelectSection(activeSection === id ? null : id)}
      />
    </div>
  );
}

function ReportPageInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const jobId = searchParams.get("jobId");
  const filename = searchParams.get("filename");
  const activeSection = searchParams.get("section");

  const goToSection = (id: string | null) => {
    const params = new URLSearchParams(searchParams.toString());
    if (id) params.set("section", id);
    else params.delete("section");
    router.push(`${pathname}?${params.toString()}`, { scroll: false });
  };

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
        setResult(sanitizeReport(data));
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
          <div className="w-10 h-10 border-4 border-brand-600 border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-sm text-gray-500">Loading report…</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-lg mx-auto px-4 py-16 text-center">
        <p className="text-red-600 mb-4">{error}</p>
        <Link href="/analysis" className="text-brand-600 hover:underline text-sm">
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
        <Link href="/analysis" className="text-sm bg-brand-600 text-white px-3 py-1.5 rounded-lg hover:bg-brand-700">
          New Analysis
        </Link>
      </div>
      <ReportContent result={result} activeSection={activeSection} onSelectSection={goToSection} />
    </div>
  );
}

export default function ReportPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center min-h-96"><div className="w-10 h-10 border-4 border-brand-600 border-t-transparent rounded-full animate-spin" /></div>}>
      <ReportPageInner />
    </Suspense>
  );
}
