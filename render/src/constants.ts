export const COLOR_PALETTE = ["#6366f1", "#f59e0b", "#10b981", "#3b82f6", "#a855f7", "#ef4444"];
export const NODE_W = 224;
export const NODE_H = 148;
export const POLL_MS = 30_000;
export const DONE_STATUSES = new Set(["done", "closed"]);

export const STATUS_GROUPS = [
  { id: "open",        label: "Open",        statuses: new Set(["open", "todo"]),                          color: "#64748b" },
  { id: "in_progress", label: "In Progress",  statuses: new Set(["in_progress", "in-progress", "hooked"]), color: "#3b82f6" },
  { id: "in_review",   label: "In Review",    statuses: new Set(["in_review", "in-review"]),               color: "#f59e0b" },
  { id: "blocked",     label: "Blocked",      statuses: new Set(["blocked"]),                              color: "#ef4444" },
  { id: "done",        label: "Done",         statuses: new Set(["closed", "done"]),                       color: "#22c55e" },
  { id: "deferred",    label: "Deferred",     statuses: new Set(["deferred"]),                             color: "#a855f7" },
] as const;

export const STATUS_OPTIONS = [
  { value: "open",        label: "Open" },
  { value: "in_progress", label: "In Progress" },
  { value: "in_review",   label: "In Review" },
  { value: "blocked",     label: "Blocked" },
  { value: "closed",      label: "Done" },
  { value: "deferred",    label: "Deferred" },
] as const;
