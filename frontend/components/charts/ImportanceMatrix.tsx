"use client";

import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts";
import { ImportanceItem } from "@/lib/api";

interface Props {
  data: ImportanceItem[];
}

const CATEGORY_COLORS: Record<string, string> = {
  high_freq_high_impact: "#ef4444",
  low_freq_high_impact: "#f97316",
  high_freq_low_impact: "#eab308",
  low_freq_low_impact: "#94a3b8",
};

const ISSUE_TYPE_LABEL: Record<string, string> = {
  product_defect: "Product defect (engineering/QA)",
  purchase_experience: "Purchase experience (CX/ops/marketing)",
};

export function ImportanceMatrix({ data }: Props) {
  // Deterministic placement within each impact band so dots don't jump around on every
  // re-render, and each dot is labeled with its priority_rank so it can be matched to the
  // ranked list below — a plain Math.random() jitter made the two impossible to correlate.
  const bandCounts: Record<string, number> = {};
  const scatterData = data.map((item) => {
    const bandKey = item.impact === "high" ? "high" : "low";
    const slot = bandCounts[bandKey] || 0;
    bandCounts[bandKey] = slot + 1;
    const y = item.impact === "high" ? 8 + (slot % 3) * 0.7 : 2 + (slot % 4) * 1.1;
    return {
      x: item.frequency_pct,
      y,
      name: item.issue,
      category: item.category,
      recommended_action: item.recommended_action,
      has_link: Boolean(item.linked_expectation_gap || item.linked_cx_action),
      rank: item.priority_rank || 0,
      fill: CATEGORY_COLORS[item.category] || "#1428a0",
    };
  });

  const ranked = [...data]
    .filter((item) => item.recommended_action || item.linked_expectation_gap || item.linked_cx_action)
    .sort((a, b) => (a.priority_rank || 999) - (b.priority_rank || 999));

  return (
    <div>
      <div className="flex flex-wrap gap-3 mb-4 text-xs">
        {Object.entries(CATEGORY_COLORS).map(([cat, color]) => (
          <div key={cat} className="flex items-center gap-1">
            <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
            <span className="text-gray-600">{cat.replace(/_/g, " ")}</span>
          </div>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={280}>
        <ScatterChart>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            type="number"
            dataKey="x"
            name="Frequency %"
            unit="%"
            domain={[0, "dataMax"]}
            tick={{ fontSize: 11 }}
            label={{ value: "Frequency", position: "insideBottom", offset: -5, fontSize: 11 }}
          />
          <YAxis
            type="number"
            dataKey="y"
            name="Impact"
            domain={[0, 12]}
            tick={{ fontSize: 11 }}
            label={{ value: "Business Impact", angle: -90, position: "insideLeft", fontSize: 11 }}
          />
          <Tooltip
            cursor={{ strokeDasharray: "3 3" }}
            content={({ active, payload }) => {
              if (active && payload && payload.length) {
                const d = payload[0].payload;
                return (
                  <div className="bg-white border border-gray-200 rounded-lg p-2 shadow text-xs max-w-64">
                    <p className="font-semibold">{d.name}</p>
                    <p className="text-gray-500 mb-1">{d.category.replace(/_/g, " ")}</p>
                    {d.has_link ? (
                      <p className="text-gray-400 italic">Fix detailed in the priority list below</p>
                    ) : d.recommended_action ? (
                      <p className="text-brand-700 leading-snug">{d.recommended_action}</p>
                    ) : null}
                  </div>
                );
              }
              return null;
            }}
          />
          <ReferenceLine x={5} stroke="#1428a0" strokeDasharray="4 4" label={{ value: "Freq threshold", fontSize: 9 }} />
          <ReferenceLine y={5} stroke="#1428a0" strokeDasharray="4 4" label={{ value: "Impact threshold", fontSize: 9 }} />
          <Scatter
            data={scatterData}
            shape={(props: any) => {
              const { cx, cy, payload } = props;
              return (
                <g>
                  <circle cx={cx} cy={cy} r={9} fill={payload.fill} />
                  {payload.rank > 0 && (
                    <text x={cx} y={cy} textAnchor="middle" dominantBaseline="central" fontSize={9} fontWeight={700} fill="#fff">
                      {payload.rank}
                    </text>
                  )}
                </g>
              );
            }}
          />
        </ScatterChart>
      </ResponsiveContainer>

      {ranked.length > 0 && (
        <div className="mt-6 border-t border-gray-100 pt-5">
          <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-3">
            Priority order
          </p>
          <ol className="space-y-3">
            {ranked.map((item, i) => {
              const hasLink = Boolean(item.linked_expectation_gap || item.linked_cx_action);
              return (
                <li key={i} className="flex gap-3 p-3 bg-gray-50 rounded-lg border border-gray-100">
                  <span className="flex-shrink-0 w-6 h-6 rounded-full bg-brand-600 text-white text-xs font-semibold flex items-center justify-center">
                    {item.priority_rank || i + 1}
                  </span>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-sm text-gray-900">{item.issue}</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-200 text-gray-600">
                        {ISSUE_TYPE_LABEL[item.issue_type] || item.issue_type}
                      </span>
                    </div>
                    <p className="text-xs text-gray-500 mt-1">{item.business_risk}</p>
                    {hasLink ? (
                      <div className="flex gap-2 flex-wrap mt-2">
                        {item.linked_expectation_gap && (
                          <a
                            href="#expectation-gaps"
                            className="text-[11px] px-2 py-1 rounded bg-blue-50 text-blue-600 border border-blue-100 hover:bg-blue-100"
                          >
                            → Fix detailed under Expectation Gaps: {item.linked_expectation_gap}
                          </a>
                        )}
                        {item.linked_cx_action && (
                          <a
                            href="#cx-actions"
                            className="text-[11px] px-2 py-1 rounded bg-green-50 text-green-600 border border-green-100 hover:bg-green-100"
                          >
                            → Fix detailed under CX Actions: {item.linked_cx_action}
                          </a>
                        )}
                      </div>
                    ) : (
                      <p className="text-sm text-brand-800 mt-1.5 leading-relaxed">{item.recommended_action}</p>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        </div>
      )}
    </div>
  );
}
