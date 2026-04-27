import type { TaskStatus } from "./types";

export const STATUS_COLOR: Record<TaskStatus, string> = {
  todo: "#64748b",
  open: "#64748b",
  "in-progress": "#3b82f6",
  in_progress: "#3b82f6",
  "in-review": "#f59e0b",
  in_review: "#f59e0b",
  blocked: "#ef4444",
  done: "#22c55e",
  closed: "#22c55e",
  deferred: "#a855f7",
  hooked: "#06b6d4",
};

export const STATUS_LABEL: Record<TaskStatus, string> = {
  todo: "Todo",
  open: "Open",
  "in-progress": "In Progress",
  in_progress: "In Progress",
  "in-review": "In Review",
  in_review: "In Review",
  blocked: "Blocked",
  done: "Done",
  closed: "Done",
  deferred: "Deferred",
  hooked: "Claimed",
};

export function relativeTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const m = Math.floor(ms / 60_000);
  const h = Math.floor(ms / 3_600_000);
  const d = Math.floor(ms / 86_400_000);
  if (d > 1) return `${d}d ago`;
  if (h > 0) return `${h}h ago`;
  if (m > 0) return `${m}m ago`;
  return "just now";
}

export function parseHours(est: string): number {
  const s = (est ?? "").toLowerCase().trim();
  if (s.endsWith("w")) return parseFloat(s) * 40;
  if (s.endsWith("d")) return parseFloat(s) * 8;
  if (s.endsWith("h")) return parseFloat(s);
  return 0;
}

export function fmtHours(h: number): string {
  if (h === 0) return "—";
  if (h >= 40 && h % 40 === 0) return `${h / 40}w`;
  if (h >= 8 && h % 8 === 0) return `${h / 8}d`;
  return `${h}h`;
}

export const EVENT_LABEL: Record<string, string> = {
  created: "Created",
  started: "Started",
  in_review: "In review since",
  merged: "Merged",
  closed: "Done",
  blocked: "Blocked since",
};
