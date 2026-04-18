import type { TaskStatus } from "./types";

export const STATUS_COLOR: Record<TaskStatus, string> = {
  open: "#64748b",
  in_progress: "#3b82f6",
  in_review: "#f59e0b",
  blocked: "#ef4444",
  closed: "#22c55e",
  deferred: "#a855f7",
  hooked: "#06b6d4",
};

export const STATUS_LABEL: Record<TaskStatus, string> = {
  open: "Open",
  in_progress: "In Progress",
  in_review: "In Review",
  blocked: "Blocked",
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

export const EVENT_LABEL: Record<string, string> = {
  created: "Created",
  started: "Started",
  in_review: "In review since",
  merged: "Merged",
  closed: "Done",
  blocked: "Blocked since",
};
