export type TaskStatus =
  | "todo"
  | "open"
  | "in-progress"
  | "in_progress"
  | "in-review"
  | "in_review"
  | "blocked"
  | "done"
  | "closed"
  | "deferred"
  | "hooked";

export type EventType =
  | "created"
  | "started"
  | "in_review"
  | "merged"
  | "closed"
  | "blocked";

export interface TaskEvent {
  type: EventType;
  at: string; // ISO 8601
}

export interface Task extends Record<string, unknown> {
  id: string;           // T001
  beadsId: string;      // bd-a1b2
  title: string;
  workstream: string;
  criticality: "P0" | "P1" | "P2";
  estimate: string;
  status: TaskStatus;
  depends: string[];    // T-IDs this task waits on
  unlocks: string[];    // T-IDs this task unblocks
  humanRequired: string | null;
  assignee: string | null;
  events: TaskEvent[];
}
