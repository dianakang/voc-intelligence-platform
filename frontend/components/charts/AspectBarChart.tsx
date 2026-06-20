"use client";

import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";

interface Props {
  data: { aspect: string; positive: number; negative: number; neutral: number }[];
}

export function AspectBarChart({ data }: Props) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} layout="vertical" margin={{ left: 10 }}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis type="number" tick={{ fontSize: 11 }} />
        <YAxis dataKey="aspect" type="category" tick={{ fontSize: 11 }} width={100} />
        <Tooltip />
        <Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} />
        <Bar dataKey="positive" stackId="a" fill="#1428a0" name="Positive" />
        <Bar dataKey="neutral" stackId="a" fill="#b3bdeb" name="Neutral" />
        <Bar dataKey="negative" stackId="a" fill="#5567c8" name="Negative" />
      </BarChart>
    </ResponsiveContainer>
  );
}
