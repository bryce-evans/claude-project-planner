import type { Task } from "./types";
import type { ColorMode, ViewMode } from "./types";
import { relativeTime } from "./utils";
import { DONE_STATUSES, STATUS_GROUPS } from "./constants";

function StatPill({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
      <span style={{ fontSize: 9, color: "#475569", textTransform: "uppercase", letterSpacing: "0.07em" }}>{label}</span>
      <span style={{ fontSize: 13, fontWeight: 700, color: color ?? "#e2e8f0" }}>{value}</span>
    </div>
  );
}

interface TopBarProps {
  tasks: Task[];
  generatedAt: string;
  viewMode: ViewMode;
  colorMode: ColorMode;
  onViewChange: (v: ViewMode) => void;
  onColorChange: (m: ColorMode) => void;
  onColorPreview: (m: ColorMode | null) => void;
}

export default function TopBar({ tasks, generatedAt, viewMode, colorMode, onViewChange, onColorChange, onColorPreview }: TopBarProps) {
  const done = tasks.filter((t) => DONE_STATUSES.has(t.status)).length;
  const inProgress = tasks.filter((t) => STATUS_GROUPS.find(g => g.id === "in_progress")?.statuses.has(t.status)).length;
  const blocked = tasks.filter((t) => t.status === "blocked").length;
  const p0 = tasks.filter((t) => t.criticality === "P0").length;
  const humanSteps = tasks.filter((t) => t.humanRequired).length;

  const btnStyle = (active: boolean) => ({
    padding: "3px 10px",
    borderRadius: 4,
    border: "none",
    cursor: "pointer" as const,
    fontSize: 10,
    fontWeight: 600,
    transition: "background 0.12s, color 0.12s",
    background: active ? "#334155" : "transparent",
    color: active ? "#f1f5f9" : "#64748b",
  });

  return (
    <div style={{ position: "absolute", top: 0, left: 0, right: 0, zIndex: 10, padding: "10px 20px", background: "rgba(15, 23, 42, 0.88)", borderBottom: "1px solid #1e293b", backdropFilter: "blur(10px)", display: "flex", alignItems: "center", gap: 28 }}>
      <span style={{ fontWeight: 800, fontSize: 14, color: "#f1f5f9", letterSpacing: "-0.01em" }}>Project Flow</span>
      <div style={{ width: 1, height: 20, background: "#1e293b" }} />
      <StatPill label="Total" value={tasks.length} />
      <StatPill label="P0" value={p0} color="#ef4444" />
      <StatPill label="Done" value={`${done} / ${tasks.length}`} color="#22c55e" />
      <StatPill label="Active" value={inProgress} color="#3b82f6" />
      <StatPill label="Blocked" value={blocked} color={blocked > 0 ? "#ef4444" : "#64748b"} />
      <StatPill label="Human steps" value={humanSteps} color="#f59e0b" />

      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 9, color: "#475569", textTransform: "uppercase", letterSpacing: "0.07em" }}>View</span>
          <div style={{ display: "flex", gap: 2, background: "#1e293b", borderRadius: 6, padding: 3 }}>
            {(["graph", "gantt"] as const).map((v) => (
              <button key={v} onClick={() => onViewChange(v)} style={btnStyle(viewMode === v)}>
                {v === "graph" ? "Graph" : "Gantt"}
              </button>
            ))}
          </div>
        </div>
        <div style={{ width: 1, height: 16, background: "#1e293b" }} />
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 9, color: "#475569", textTransform: "uppercase", letterSpacing: "0.07em" }}>Color by</span>
          <div style={{ display: "flex", gap: 2, background: "#1e293b", borderRadius: 6, padding: 3 }}>
            {(["workstream", "owner", "status"] as const).map((mode) => (
              <button key={mode} onMouseEnter={() => onColorPreview(mode)} onMouseLeave={() => onColorPreview(null)} onClick={() => onColorChange(mode)} style={btnStyle(colorMode === mode)}>
                {mode === "workstream" ? "Workstream" : mode === "owner" ? "Owner" : "Status"}
              </button>
            ))}
          </div>
        </div>
      </div>

      {generatedAt && <span style={{ fontSize: 10, color: "#334155" }}>{relativeTime(generatedAt)}</span>}
    </div>
  );
}
