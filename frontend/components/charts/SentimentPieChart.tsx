"use client";

import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";

// Matches AspectBarChart's positive/negative/neutral palette exactly, so the same sentiment
// category reads as the same color across both charts in this section.
// Keys are lowercase to match result.sentiment_distribution's actual keys (positive/negative/neutral) —
// a prior capitalized-key version silently never matched, so every slice rendered as the same fallback color.
const COLORS: Record<string, string> = {
  positive: "#1428a0",
  negative: "#5567c8",
  neutral: "#b3bdeb",
};

interface Props {
  data: { name: string; value: number }[];
}

export function SentimentPieChart({ data }: Props) {
  const total = data.reduce((sum, d) => sum + d.value, 0);
  return (
    <div>
      <ResponsiveContainer width="100%" height={200}>
        <PieChart>
          <Pie data={data} cx="50%" cy="50%" outerRadius={75} dataKey="value">
            {data.map((entry, index) => (
              <Cell key={index} fill={COLORS[entry.name] || "#1428a0"} />
            ))}
          </Pie>
          <Tooltip formatter={(value) => [Number(value), "Reviews"]} />
        </PieChart>
      </ResponsiveContainer>
      {/* Plain HTML legend instead of Recharts' leader-line labels, which clip
          inside this card's fixed width once the slice text gets long. */}
      <div className="flex flex-wrap justify-center gap-4 mt-2">
        {data.map((d) => (
          <span key={d.name} className="flex items-center gap-1.5 text-xs text-gray-700">
            <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: COLORS[d.name] || "#1428a0" }} />
            {d.name.charAt(0).toUpperCase() + d.name.slice(1)} {total === 0 ? 0 : Math.round((d.value / total) * 100)}%
          </span>
        ))}
      </div>
    </div>
  );
}
