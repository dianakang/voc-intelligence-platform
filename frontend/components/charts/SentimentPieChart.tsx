"use client";

import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from "recharts";

const COLORS: Record<string, string> = {
  Positive: "#1428a0",
  Negative: "#5567c8",
  Neutral: "#b3bdeb",
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
            <Cell key={index} fill={COLORS[entry.name] || "#1428a0"} />
          ))}
        </Pie>
        <Tooltip formatter={(value) => [Number(value), "Reviews"]} />
      </PieChart>
    </ResponsiveContainer>
  );
}
