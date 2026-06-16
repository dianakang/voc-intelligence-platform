import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatPct(value: number) {
  return `${Math.round(value)}%`;
}

export function severityColor(severity: string) {
  switch (severity) {
    case "high": return "text-red-600 bg-red-50 border-red-200";
    case "medium": return "text-yellow-600 bg-yellow-50 border-yellow-200";
    case "low": return "text-green-600 bg-green-50 border-green-200";
    default: return "text-gray-600 bg-gray-50 border-gray-200";
  }
}

export function priorityColor(priority: string) {
  switch (priority?.toLowerCase()) {
    case "high": return "bg-red-100 text-red-800";
    case "medium": return "bg-yellow-100 text-yellow-800";
    case "low": return "bg-green-100 text-green-800";
    default: return "bg-gray-100 text-gray-800";
  }
}

export function agentStatusColor(status: string) {
  switch (status) {
    case "done": return "text-green-600";
    case "running": return "text-blue-600";
    case "error": return "text-red-600";
    default: return "text-gray-400";
  }
}

export function agentStatusIcon(status: string) {
  switch (status) {
    case "done": return "✓";
    case "running": return "⟳";
    case "error": return "✗";
    default: return "○";
  }
}

export function sentimentColor(sentiment: string) {
  switch (sentiment) {
    case "positive": return "#22c55e";
    case "negative": return "#ef4444";
    case "neutral": return "#94a3b8";
    default: return "#94a3b8";
  }
}
