"use client";

import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from "recharts";

const COLORS: Record<string, string> = {
  Positive: "#22c55e",
  Negative: "#ef4444",
  Neutral: "#94a3b8",
};

interface Props {
  data: { name: string; value: number }[];
}

export function SentimentPieChart({ data }: Props) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <PieChart>
        <Pie data={data} cx="50%" cy="50%" outerRadius={85} dataKey="value" label={(props) => `${props.name ?? ""} ${(((props.percent as number | undefined) ?? 0) * 100).toFixed(0)}%`}>
          {data.map((entry, index) => (
            <Cell key={index} fill={COLORS[entry.name] || "#6366f1"} />
          ))}
        </Pie>
        <Tooltip formatter={(value) => [Number(value), "Reviews"]} />
      </PieChart>
    </ResponsiveContainer>
  );
}
