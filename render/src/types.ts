export type TaskStatus =
  | "open"
  | "in_progress"
  | "in_review"
  | "blocked"
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

export interface Task {
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
