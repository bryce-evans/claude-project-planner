import { useState, useCallback } from "react";
import type { Task } from "./types";
import type { ColorMode, Workstream, Owner } from "./types";
import { parseHours, fmtHours } from "./utils";
import { STATUS_GROUPS, DONE_STATUSES } from "./constants";
import SelectionPanel from "./SelectionPanel";

interface SidebarProps {
  tasks: Task[];
  activeMode: ColorMode;
  workstreams: Workstream[];
  owners: Owner[];
  WS_COLOR: Record<string, string>;
  OWNER_COLOR: Record<string, string>;
  workstreamScopes: Record<string, string>;
  workstreamOwners: Record<string, string>;
  onWsHover: (id: string | null) => void;
  onOwnerHover: (owner: string | null) => void;
  onStatusHover: (groupId: string | null) => void;
  selectedTask: Task | null;
  onUpdateTask: (beadsId: string, field: string, value: string) => void;
}

function ProgressBar({ value, total, color }: { value: number; total: number; color: string }) {
  return (
    <div style={{ height: 4, background: "#1e293b", borderRadius: 2, overflow: "hidden" }}>
      <div style={{ height: "100%", width: `${total ? (value / total) * 100 : 0}%`, background: color, borderRadius: 2, transition: "width 0.3s" }} />
    </div>
  );
}

export default function Sidebar({ tasks, activeMode, workstreams, owners, WS_COLOR, OWNER_COLOR, workstreamScopes, workstreamOwners, onWsHover, onOwnerHover, onStatusHover, selectedTask, onUpdateTask }: SidebarProps) {
  const [hoveredWs, setHoveredWs] = useState<string | null>(null);
  const [expandedWs, setExpandedWs] = useState<string | null>(null);
  const [expandedOwner, setExpandedOwner] = useState<string | null>(null);

  const wsStats = useCallback((wsId: string) => {
    const wsTasks = tasks.filter((t) => t.workstream.split("—")[0].trim() === wsId);
    const done = wsTasks.filter((t) => DONE_STATUSES.has(t.status));
    const remaining = wsTasks.filter((t) => !DONE_STATUSES.has(t.status));
    return {
      total: wsTasks.length,
      doneCount: done.length,
      hoursCompleted: done.reduce((s, t) => s + parseHours(t.estimate), 0),
      hoursRemaining: remaining.reduce((s, t) => s + parseHours(t.estimate), 0),
      assignees: Array.from(new Set(wsTasks.map((t) => t.assignee).filter(Boolean) as string[])),
    };
  }, [tasks]);

  const ownerStats = useCallback((owner: string) => {
    const ownerTasks = tasks.filter((t) => owner === "(unassigned)" ? !t.assignee : t.assignee === owner);
    const done = ownerTasks.filter((t) => DONE_STATUSES.has(t.status));
    const remaining = ownerTasks.filter((t) => !DONE_STATUSES.has(t.status));
    return {
      total: ownerTasks.length,
      doneCount: done.length,
      hoursCompleted: done.reduce((s, t) => s + parseHours(t.estimate), 0),
      hoursRemaining: remaining.reduce((s, t) => s + parseHours(t.estimate), 0),
      streams: Array.from(new Set(ownerTasks.map((t) => t.workstream.split("—")[0].trim()))),
    };
  }, [tasks]);

  const sectionLabel = activeMode === "owner" ? "Owners" : activeMode === "status" ? "Status" : "Workstreams";

  return (
    <div style={{ width: 200, flexShrink: 0, background: "rgba(15,23,42,0.95)", borderRight: "1px solid #1e293b", display: "flex", flexDirection: "column", zIndex: 20, overflow: "hidden" }}>
      <div style={{ flex: 1, overflowY: "auto", paddingTop: 56 }}>
        <div style={{ padding: "10px 14px 6px", fontSize: 9, color: "#475569", textTransform: "uppercase", letterSpacing: "0.08em" }}>
          {sectionLabel}
        </div>

        {activeMode === "status" && STATUS_GROUPS.filter((g) => tasks.some((t) => g.statuses.has(t.status))).map((g) => {
          const count = tasks.filter((t) => g.statuses.has(t.status)).length;
          const pct = tasks.length ? Math.round((count / tasks.length) * 100) : 0;
          return (
            <div key={g.id} onMouseEnter={() => onStatusHover(g.id)} onMouseLeave={() => onStatusHover(null)} style={{ padding: "9px 14px", cursor: "default", display: "flex", flexDirection: "column", gap: 5 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                <div style={{ width: 8, height: 8, borderRadius: "50%", background: g.color, flexShrink: 0 }} />
                <span style={{ fontSize: 11, fontWeight: 600, color: "#94a3b8", flex: 1 }}>{g.label}</span>
                <span style={{ fontSize: 11, fontWeight: 700, color: g.color }}>{count}</span>
              </div>
              <div style={{ height: 3, background: "#1e293b", borderRadius: 2, overflow: "hidden" }}>
                <div style={{ height: "100%", width: `${pct}%`, background: g.color, borderRadius: 2 }} />
              </div>
            </div>
          );
        })}

        {activeMode === "owner" && owners.map((o) => {
          const isExpanded = expandedOwner === o.id;
          const stats = ownerStats(o.id);
          return (
            <div key={o.id}>
              <div onMouseEnter={() => onOwnerHover(o.id)} onMouseLeave={() => onOwnerHover(null)} onClick={() => setExpandedOwner(isExpanded ? null : o.id)} style={{ padding: "9px 14px", cursor: "pointer", background: isExpanded ? `${o.color}18` : "transparent", borderLeft: `3px solid ${isExpanded ? o.color : "transparent"}`, transition: "background 0.12s, border-color 0.12s", display: "flex", flexDirection: "column", gap: 2 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 11, fontWeight: 600, color: isExpanded ? "#f1f5f9" : "#94a3b8" }}>{o.id}</span>
                  <span style={{ fontSize: 9, color: "#475569", display: "inline-block", transform: isExpanded ? "rotate(90deg)" : "none" }}>▶</span>
                </div>
                <span style={{ fontSize: 9, color: "#475569" }}>{stats.doneCount}/{stats.total} done</span>
              </div>
              {isExpanded && (
                <div style={{ background: `${o.color}0d`, borderLeft: `3px solid ${o.color}44`, padding: "10px 14px 12px", display: "flex", flexDirection: "column", gap: 10 }}>
                  {stats.streams.length > 0 && (
                    <div>
                      <div style={{ fontSize: 8, color: "#475569", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 4 }}>Workstreams</div>
                      {stats.streams.map((ws) => (
                        <div key={ws} style={{ fontSize: 10, color: "#94a3b8", display: "flex", alignItems: "center", gap: 4 }}>
                          <span style={{ color: WS_COLOR[ws] ?? o.color }}>●</span> {ws}
                        </div>
                      ))}
                    </div>
                  )}
                  <div>
                    <div style={{ fontSize: 8, color: "#475569", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Progress</div>
                    <ProgressBar value={stats.doneCount} total={stats.total} color={o.color} />
                    <div style={{ marginTop: 3, fontSize: 9, color: "#475569" }}>{stats.doneCount} of {stats.total} tasks</div>
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                    <div>
                      <div style={{ fontSize: 8, color: "#475569", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 2 }}>Completed</div>
                      <div style={{ fontSize: 13, fontWeight: 700, color: "#22c55e" }}>{fmtHours(stats.hoursCompleted)}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 8, color: "#475569", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 2 }}>Remaining</div>
                      <div style={{ fontSize: 13, fontWeight: 700, color: o.color }}>{fmtHours(stats.hoursRemaining)}</div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}

        {activeMode === "workstream" && workstreams.map((ws) => {
          const isHovered = hoveredWs === ws.id;
          const isExpanded = expandedWs === ws.id;
          const stats = wsStats(ws.id);
          return (
            <div key={ws.id}>
              <div
                onMouseEnter={() => { setHoveredWs(ws.id); onWsHover(ws.id); }}
                onMouseLeave={() => { setHoveredWs(null); onWsHover(null); }}
                onClick={() => setExpandedWs(isExpanded ? null : ws.id)}
                style={{ padding: "9px 14px", cursor: "pointer", background: isHovered || isExpanded ? `${ws.color}18` : "transparent", borderLeft: `3px solid ${isHovered || isExpanded ? ws.color : "transparent"}`, transition: "background 0.12s, border-color 0.12s", display: "flex", flexDirection: "column", gap: 2 }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 9, fontWeight: 700, color: ws.color, letterSpacing: "0.05em" }}>{ws.id}</span>
                  <span style={{ fontSize: 9, color: "#475569", display: "inline-block", transform: isExpanded ? "rotate(90deg)" : "none" }}>▶</span>
                </div>
                <span style={{ fontSize: 11, fontWeight: 600, color: isHovered || isExpanded ? "#f1f5f9" : "#94a3b8" }}>{ws.name}</span>
                <span style={{ fontSize: 9, color: "#475569" }}>{stats.doneCount}/{stats.total} done</span>
              </div>
              {isExpanded && (
                <div style={{ background: `${ws.color}0d`, borderLeft: `3px solid ${ws.color}44`, padding: "10px 14px 12px", display: "flex", flexDirection: "column", gap: 10 }}>
                  {workstreamScopes[ws.id] && <div style={{ fontSize: 9, color: "#64748b", lineHeight: 1.5 }}>{workstreamScopes[ws.id]}</div>}
                  {workstreamOwners[ws.id] && (
                    <div>
                      <div style={{ fontSize: 8, color: "#475569", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 3 }}>Owner</div>
                      <div style={{ fontSize: 10, color: ws.color, fontWeight: 600 }}>{workstreamOwners[ws.id]}</div>
                    </div>
                  )}
                  {stats.assignees.length > 0 && (
                    <div>
                      <div style={{ fontSize: 8, color: "#475569", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 4 }}>On this workstream</div>
                      {stats.assignees.map((a) => (
                        <div key={a} style={{ fontSize: 10, color: "#94a3b8", display: "flex", alignItems: "center", gap: 4 }}>
                          <span style={{ color: OWNER_COLOR[a] ?? ws.color }}>●</span> {a}
                        </div>
                      ))}
                    </div>
                  )}
                  <div>
                    <div style={{ fontSize: 8, color: "#475569", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Progress</div>
                    <ProgressBar value={stats.doneCount} total={stats.total} color={ws.color} />
                    <div style={{ marginTop: 3, fontSize: 9, color: "#475569" }}>{stats.doneCount} of {stats.total} tasks</div>
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                    <div>
                      <div style={{ fontSize: 8, color: "#475569", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 2 }}>Completed</div>
                      <div style={{ fontSize: 13, fontWeight: 700, color: "#22c55e" }}>{fmtHours(stats.hoursCompleted)}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 8, color: "#475569", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 2 }}>Remaining</div>
                      <div style={{ fontSize: 13, fontWeight: 700, color: ws.color }}>{fmtHours(stats.hoursRemaining)}</div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {selectedTask && (
        <SelectionPanel
          task={selectedTask}
          workstreams={workstreams.map((w) => ({ id: w.id, full: w.full }))}
          assignees={owners.filter((o) => o.id !== "(unassigned)").map((o) => o.id)}
          onUpdate={onUpdateTask}
        />
      )}
    </div>
  );
}
