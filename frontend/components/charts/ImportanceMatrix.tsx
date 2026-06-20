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

export function ImportanceMatrix({ data }: Props) {
  const scatterData = data.map((item) => ({
    x: item.frequency_pct,
    y: item.impact === "high" ? 8 + Math.random() * 2 : 2 + Math.random() * 3,
    name: item.issue,
    category: item.category,
    fill: CATEGORY_COLORS[item.category] || "#1428a0",
  }));

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
          <XAxis dataKey="x" name="Frequency %" unit="%" tick={{ fontSize: 11 }} label={{ value: "Frequency", position: "insideBottom", offset: -5, fontSize: 11 }} />
          <YAxis dataKey="y" name="Impact" tick={{ fontSize: 11 }} label={{ value: "Business Impact", angle: -90, position: "insideLeft", fontSize: 11 }} />
          <Tooltip
            cursor={{ strokeDasharray: "3 3" }}
            content={({ active, payload }) => {
              if (active && payload && payload.length) {
                const d = payload[0].payload;
                return (
                  <div className="bg-white border border-gray-200 rounded-lg p-2 shadow text-xs max-w-48">
                    <p className="font-semibold">{d.name}</p>
                    <p className="text-gray-500">{d.category.replace(/_/g, " ")}</p>
                  </div>
                );
              }
              return null;
            }}
          />
          <ReferenceLine x={5} stroke="#1428a0" strokeDasharray="4 4" label={{ value: "Freq threshold", fontSize: 9 }} />
          <ReferenceLine y={5} stroke="#1428a0" strokeDasharray="4 4" label={{ value: "Impact threshold", fontSize: 9 }} />
          {scatterData.map((d, i) => (
            <Scatter key={i} data={[d]} fill={d.fill} />
          ))}
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
