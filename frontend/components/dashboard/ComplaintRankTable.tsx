import { Complaint } from "@/lib/api";

interface Props { complaints: Complaint[] }

export function ComplaintRankTable({ complaints }: Props) {
  return (
    <div className="space-y-3">
      {complaints.map((c) => (
        <div key={c.rank} className="flex items-start gap-3">
          <div className="w-6 h-6 rounded-full bg-brand-100 text-brand-700 text-xs font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
            {c.rank}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span
                className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                  c.issue_type === "purchase_experience" ? "bg-gray-400" : "bg-red-500"
                }`}
                title={c.issue_type === "purchase_experience" ? "Purchase experience issue" : "Product issue"}
              />
              <span className="text-sm font-medium text-gray-900">{c.category}</span>
              <span className="text-xs text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded">
                {Math.round(c.frequency_pct)}%
              </span>
            </div>
            <p className="text-xs text-gray-500 mt-0.5 truncate">{c.root_cause}</p>
          </div>
        </div>
      ))}
      {complaints.length === 0 && (
        <p className="text-sm text-gray-400 text-center py-4">No complaints data</p>
      )}
    </div>
  );
}
