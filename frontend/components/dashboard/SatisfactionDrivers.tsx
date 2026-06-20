import { SatisfactionDriver } from "@/lib/api";

interface Props { drivers: SatisfactionDriver[] }

export function SatisfactionDrivers({ drivers }: Props) {
  return (
    <div className="space-y-3">
      {drivers.map((d) => (
        <div key={d.rank}>
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm font-medium text-gray-900">{d.factor}</span>
            <span className="text-xs font-semibold text-brand-700">{Math.round(d.positive_rate)}%</span>
          </div>
          <div className="w-full bg-gray-100 rounded-full h-2">
            <div
              className="bg-brand-500 h-2 rounded-full"
              style={{ width: `${Math.min(d.positive_rate, 100)}%` }}
            />
          </div>
          <p className="text-xs text-gray-400 mt-0.5">{d.mention_count} mentions</p>
        </div>
      ))}
      {drivers.length === 0 && (
        <p className="text-sm text-gray-400 text-center py-4">No data</p>
      )}
    </div>
  );
}
