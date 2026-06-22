"use client";

import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from "recharts";

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
  return (
    <ResponsiveContainer width="100%" height={240}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          outerRadius={85}
          dataKey="value"
          label={(props) => {
            const name = String(props.name ?? "");
            const label = name.charAt(0).toUpperCase() + name.slice(1);
            return `${label} ${(((props.percent as number | undefined) ?? 0) * 100).toFixed(0)}%`;
          }}
        >
          {data.map((entry, index) => (
            <Cell key={index} fill={COLORS[entry.name] || "#1428a0"} />
          ))}
        </Pie>
        <Tooltip formatter={(value) => [Number(value), "Reviews"]} />
      </PieChart>
    </ResponsiveContainer>
  );
}
