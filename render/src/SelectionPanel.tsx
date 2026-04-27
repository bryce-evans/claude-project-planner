import { useState, useEffect, type CSSProperties } from "react";
import type { Task } from "./types";
import { STATUS_OPTIONS } from "./constants";

const CTRL_STYLE: CSSProperties = {
  width: "100%",
  background: "#1e293b",
  border: "1px solid #334155",
  borderRadius: 4,
  color: "#94a3b8",
  fontSize: 10,
  padding: "3px 6px",
  outline: "none",
  fontFamily: "inherit",
  boxSizing: "border-box",
};

function SField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <span style={{ fontSize: 8, color: "#475569", textTransform: "uppercase", letterSpacing: "0.07em" }}>
        {label}
      </span>
      {children}
    </div>
  );
}

function validateEstimate(s: string): boolean {
  const t = s.trim().toLowerCase();
  return t === "" || /^\d+(\.\d+)?[hdw]$/.test(t);
}

interface SelectionPanelProps {
  task: Task;
  workstreams: { id: string; full: string }[];
  assignees: string[];
  onUpdate: (beadsId: string, field: string, value: string) => void;
}

export default function SelectionPanel({ task, workstreams, assignees, onUpdate }: SelectionPanelProps) {
  const [estimateInput, setEstimateInput] = useState(task.estimate);
  const [estimateError, setEstimateError] = useState(false);

  useEffect(() => {
    setEstimateInput(task.estimate);
    setEstimateError(false);
  }, [task.estimate]);

  const canonicalStatus = STATUS_OPTIONS.find((o) => {
    if (task.status === "done" || task.status === "closed") return o.value === "closed";
    if (task.status === "in-progress") return o.value === "in_progress";
    if (task.status === "in-review") return o.value === "in_review";
    return o.value === task.status;
  })?.value ?? task.status;

  return (
    <div style={{ borderTop: "1px solid #1e293b", padding: "12px 14px 14px", display: "flex", flexDirection: "column", gap: 10, background: "#0a1120", flexShrink: 0 }}>
      <div style={{ fontSize: 9, color: "#475569", textTransform: "uppercase", letterSpacing: "0.08em" }}>
        Selection
      </div>
      <div>
        <div style={{ fontSize: 11, fontWeight: 700, color: "#f1f5f9" }}>{task.id}</div>
        {task.title && <div style={{ fontSize: 9, color: "#64748b", marginTop: 2, lineHeight: 1.4 }}>{task.title}</div>}
      </div>

      <SField label="Status">
        <select value={canonicalStatus} onChange={(e) => onUpdate(task.beadsId, "status", e.target.value)} style={{ ...CTRL_STYLE, cursor: "pointer" }}>
          {STATUS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </SField>

      <SField label="Assignee">
        <select value={task.assignee ?? ""} onChange={(e) => onUpdate(task.beadsId, "assignee", e.target.value)} style={{ ...CTRL_STYLE, cursor: "pointer" }}>
          <option value="">(none)</option>
          {assignees.map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
      </SField>

      <SField label="Estimate">
        <input
          value={estimateInput}
          onChange={(e) => { setEstimateInput(e.target.value); setEstimateError(false); }}
          onBlur={() => {
            if (!validateEstimate(estimateInput)) { setEstimateError(true); return; }
            if (estimateInput !== task.estimate) onUpdate(task.beadsId, "estimate", estimateInput);
          }}
          onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
          placeholder="2h, 1d, 1w"
          style={{ ...CTRL_STYLE, borderColor: estimateError ? "#ef4444" : "#334155" }}
        />
        {estimateError && <span style={{ fontSize: 9, color: "#ef4444" }}>Use h, d, or w — e.g. 2h, 1d, 1w</span>}
      </SField>

      <SField label="Workstream">
        <select value={task.workstream} onChange={(e) => onUpdate(task.beadsId, "workstream", e.target.value)} style={{ ...CTRL_STYLE, cursor: "pointer" }}>
          {workstreams.map((w) => <option key={w.id} value={w.full}>{w.id}</option>)}
        </select>
      </SField>
    </div>
  );
}
