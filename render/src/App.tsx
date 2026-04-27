import { useMemo, useCallback, useState, useEffect, useRef } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeTypes,
} from "@xyflow/react";
import Dagre from "@dagrejs/dagre";
import TaskNode from "./TaskNode";
import GanttView from "./GanttView";
import type { Task, TaskStatus } from "./types";
import { STATUS_COLOR, relativeTime, parseHours } from "./utils";

const NODE_W = 224;
const NODE_H = 148;
const POLL_MS = 30_000;

interface TaskData {
  tasks: Task[];
  generatedAt: string;
  workstreamScopes: Record<string, string>;
  workstreamOwners: Record<string, string>;
}

const EMPTY: TaskData = { tasks: [], generatedAt: "", workstreamScopes: {}, workstreamOwners: {} };

function buildGraph(tasks: Task[], mode: ColorMode, wsColor: Record<string, string>, ownerColor: Record<string, string>): { nodes: Node[]; edges: Edge[] } {
  const g = new Dagre.graphlib.Graph();
  g.setGraph({ rankdir: "LR", nodesep: 48, ranksep: 96, marginx: 40, marginy: 40 });
  g.setDefaultEdgeLabel(() => ({}));

  const taskIds = new Set(tasks.map((t) => t.id));

  tasks.forEach((t) => {
    g.setNode(t.id, { width: NODE_W, height: NODE_H });
  });

  tasks.forEach((t) => {
    t.depends.forEach((depId) => {
      if (taskIds.has(depId)) {
        g.setEdge(depId, t.id);
      }
    });
  });

  Dagre.layout(g);

  const nodes: Node[] = tasks.map((t) => {
    const pos = g.node(t.id);
    return {
      id: t.id,
      type: "taskNode",
      position: { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 },
      data: { ...t, wsColor: getTaskColor(t, mode, wsColor, ownerColor) },
    };
  });

  const edges: Edge[] = tasks.flatMap((t) =>
    t.depends
      .filter((depId) => taskIds.has(depId))
      .map((depId) => {
        const sourceTask = tasks.find((x) => x.id === depId);
        const isActive = t.status === "in_progress" || t.status === "in_review";
        const isBlocked = t.status === "blocked";
        const color = isBlocked ? "#ef4444" : isActive ? STATUS_COLOR[t.status] : "#334155";
        return {
          id: `${depId}→${t.id}`,
          source: depId,
          target: t.id,
          animated: isActive && sourceTask?.status === "closed",
          style: { stroke: color, strokeWidth: isBlocked ? 2 : 1.5 },
          labelStyle: { fill: "#94a3b8", fontSize: 9 },
        };
      })
  );

  return { nodes, edges };
}

const nodeTypes: NodeTypes = { taskNode: TaskNode as never };

function fmtHours(h: number): string {
  if (h === 0) return "—";
  if (h >= 40 && h % 40 === 0) return `${h / 40}w`;
  if (h >= 8 && h % 8 === 0) return `${h / 8}d`;
  return `${h}h`;
}

const DONE_STATUSES = new Set(["done", "closed"]);
const COLOR_PALETTE = ["#6366f1", "#f59e0b", "#10b981", "#3b82f6", "#a855f7", "#ef4444"];

type ColorMode = "workstream" | "owner";
type ViewMode = "graph" | "gantt";

function getTaskColor(task: Task, mode: ColorMode, wsColor: Record<string, string>, ownerColor: Record<string, string>): string {
  if (mode === "owner") {
    return task.assignee ? (ownerColor[task.assignee] ?? "#334155") : "#334155";
  }
  const wsId = task.workstream.split("—")[0].trim();
  return wsColor[wsId] ?? "#334155";
}

function StatPill({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
      <span style={{ fontSize: 9, color: "#475569", textTransform: "uppercase", letterSpacing: "0.07em" }}>
        {label}
      </span>
      <span style={{ fontSize: 13, fontWeight: 700, color: color ?? "#e2e8f0" }}>{value}</span>
    </div>
  );
}

export default function App() {
  const [data, setData] = useState<TaskData>(EMPTY);
  const [viewMode, setViewMode] = useState<ViewMode>("graph");
  const [colorMode, setColorMode] = useState<ColorMode>("workstream");
  const [previewMode, setPreviewMode] = useState<ColorMode | null>(null);
  const activeMode = previewMode ?? colorMode;
  const lastGeneratedAt = useRef("");

  // Derived from tasks
  const { tasks, generatedAt, workstreamScopes, workstreamOwners } = data;

  const WORKSTREAMS = useMemo(() =>
    Array.from(
      new Map(tasks.map((t) => [t.workstream.split("—")[0].trim(), t.workstream])).entries() as Iterable<[string, string]>
    ).map(([id, full], i) => ({
      id,
      full,
      name: full.includes("—") ? full.split("—")[1].trim() : full,
      color: COLOR_PALETTE[i % COLOR_PALETTE.length],
    })),
    [tasks]
  );

  const WS_COLOR = useMemo(() =>
    Object.fromEntries(WORKSTREAMS.map((w) => [w.id, w.color])),
    [WORKSTREAMS]
  );

  const OWNER_COLOR = useMemo(() => {
    const owners = Array.from(new Set(tasks.map((t) => t.assignee).filter(Boolean) as string[]));
    return Object.fromEntries(owners.map((o, i) => [o, COLOR_PALETTE[i % COLOR_PALETTE.length]]));
  }, [tasks]);

  // Fetch and poll
  useEffect(() => {
    async function fetchData() {
      try {
        const res = await fetch("/tasks.json");
        if (!res.ok) return;
        const json: TaskData = await res.json();
        if (json.generatedAt !== lastGeneratedAt.current) {
          lastGeneratedAt.current = json.generatedAt;
          setData(json);
        }
      } catch {
        // network error — keep current data
      }
    }

    fetchData();
    const interval = setInterval(fetchData, POLL_MS);
    return () => clearInterval(interval);
  }, []);

  const { nodes: initNodes, edges: initEdges } = useMemo(
    () => buildGraph(tasks, colorMode, WS_COLOR, OWNER_COLOR),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [tasks]
  );
  const [nodes, setNodes, onNodesChange] = useNodesState(initNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initEdges);

  // Sync graph when tasks load
  useEffect(() => {
    const { nodes: newNodes, edges: newEdges } = buildGraph(tasks, colorMode, WS_COLOR, OWNER_COLOR);
    setNodes(newNodes);
    setEdges(newEdges);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tasks]);

  const [hoveredWs, setHoveredWs] = useState<string | null>(null);
  const [expandedWs, setExpandedWs] = useState<string | null>(null);
  const [expandedOwner, setExpandedOwner] = useState<string | null>(null);

  const OWNERS = useMemo(() =>
    Array.from(new Set(tasks.map((t) => t.assignee).filter(Boolean) as string[])).map((owner, i) => ({
      id: owner,
      color: OWNER_COLOR[owner] ?? COLOR_PALETTE[i % COLOR_PALETTE.length],
    })),
    [tasks, OWNER_COLOR]
  );

  // Recolor nodes when color mode changes
  useEffect(() => {
    setNodes((nds) =>
      nds.map((n) => ({
        ...n,
        data: { ...n.data, wsColor: getTaskColor(n.data as Task, activeMode, WS_COLOR, OWNER_COLOR) },
      }))
    );
  }, [activeMode, setNodes, WS_COLOR, OWNER_COLOR]);

  const wsStats = useCallback((wsId: string) => {
    const wsTasks = tasks.filter((t) => t.workstream.split("—")[0].trim() === wsId);
    const done = wsTasks.filter((t) => DONE_STATUSES.has(t.status));
    const remaining = wsTasks.filter((t) => !DONE_STATUSES.has(t.status));
    const assignees = Array.from(new Set(wsTasks.map((t) => t.assignee).filter(Boolean) as string[]));
    return {
      total: wsTasks.length,
      doneCount: done.length,
      hoursCompleted: done.reduce((s, t) => s + parseHours(t.estimate), 0),
      hoursRemaining: remaining.reduce((s, t) => s + parseHours(t.estimate), 0),
      assignees,
    };
  }, [tasks]);

  const ownerStats = useCallback((owner: string) => {
    const ownerTasks = tasks.filter((t) => t.assignee === owner);
    const done = ownerTasks.filter((t) => DONE_STATUSES.has(t.status));
    const remaining = ownerTasks.filter((t) => !DONE_STATUSES.has(t.status));
    const streams = Array.from(new Set(ownerTasks.map((t) => t.workstream.split("—")[0].trim())));
    return {
      total: ownerTasks.length,
      doneCount: done.length,
      hoursCompleted: done.reduce((s, t) => s + parseHours(t.estimate), 0),
      hoursRemaining: remaining.reduce((s, t) => s + parseHours(t.estimate), 0),
      streams,
    };
  }, [tasks]);

  const byStatus = useCallback(
    (s: TaskStatus) => tasks.filter((t) => t.status === s).length,
    [tasks]
  );

  const done = byStatus("closed") + byStatus("done");
  const inProgress = byStatus("in_progress") + byStatus("in-progress") + byStatus("in_review") + byStatus("in-review") + byStatus("hooked");
  const blocked = byStatus("blocked");
  const p0 = tasks.filter((t) => t.criticality === "P0").length;
  const humanSteps = tasks.filter((t) => t.humanRequired).length;

  const handleWsHover = useCallback(
    (wsId: string | null) => {
      setHoveredWs(wsId);
      setNodes((nds) =>
        nds.map((n) => {
          const task = n.data as Task;
          const taskWsId = task.workstream.split("—")[0].trim();
          const dimmed = wsId !== null && taskWsId !== wsId;
          return { ...n, data: { ...task, dimmed } };
        })
      );
    },
    [setNodes]
  );

  const handleOwnerHover = useCallback(
    (owner: string | null) => {
      setNodes((nds) =>
        nds.map((n) => {
          const task = n.data as Task;
          const dimmed = owner !== null && task.assignee !== owner;
          return { ...n, data: { ...task, dimmed } };
        })
      );
    },
    [setNodes]
  );

  if (!tasks.length) {
    return (
      <div style={{ width: "100vw", height: "100vh", background: "#0f172a", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <span style={{ color: "#475569", fontSize: 14 }}>Loading tasks…</span>
      </div>
    );
  }

  return (
    <div style={{ width: "100vw", height: "100vh", background: "#0f172a", display: "flex" }}>
      {/* Sidebar — workstreams or owners depending on color mode */}
      <div
        style={{
          width: 200,
          flexShrink: 0,
          background: "rgba(15,23,42,0.95)",
          borderRight: "1px solid #1e293b",
          display: "flex",
          flexDirection: "column",
          paddingTop: 56,
          zIndex: 20,
          overflowY: "auto",
        }}
      >
        <div style={{ padding: "10px 14px 6px", fontSize: 9, color: "#475569", textTransform: "uppercase", letterSpacing: "0.08em" }}>
          {activeMode === "owner" ? "Owners" : "Workstreams"}
        </div>

        {activeMode === "owner" ? (
          /* ── Owner list ── */
          OWNERS.map((o) => {
            const isExpanded = expandedOwner === o.id;
            const stats = ownerStats(o.id);
            return (
              <div key={o.id}>
                <div
                  onMouseEnter={() => handleOwnerHover(o.id)}
                  onMouseLeave={() => handleOwnerHover(null)}
                  onClick={() => setExpandedOwner(isExpanded ? null : o.id)}
                  style={{
                    padding: "9px 14px",
                    cursor: "pointer",
                    background: isExpanded ? `${o.color}18` : "transparent",
                    borderLeft: `3px solid ${isExpanded ? o.color : "transparent"}`,
                    transition: "background 0.12s, border-color 0.12s",
                    display: "flex",
                    flexDirection: "column",
                    gap: 2,
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: 11, fontWeight: 600, color: isExpanded ? "#f1f5f9" : "#94a3b8" }}>
                      {o.id}
                    </span>
                    <span style={{ fontSize: 9, color: "#475569", transition: "transform 0.15s", display: "inline-block", transform: isExpanded ? "rotate(90deg)" : "none" }}>
                      ▶
                    </span>
                  </div>
                  <span style={{ fontSize: 9, color: "#475569" }}>
                    {stats.doneCount}/{stats.total} done
                  </span>
                </div>

                {isExpanded && (
                  <div
                    style={{
                      background: `${o.color}0d`,
                      borderLeft: `3px solid ${o.color}44`,
                      padding: "10px 14px 12px",
                      display: "flex",
                      flexDirection: "column",
                      gap: 10,
                    }}
                  >
                    {stats.streams.length > 0 && (
                      <div>
                        <div style={{ fontSize: 8, color: "#475569", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 4 }}>
                          Workstreams
                        </div>
                        {stats.streams.map((ws) => (
                          <div key={ws} style={{ fontSize: 10, color: "#94a3b8", display: "flex", alignItems: "center", gap: 4 }}>
                            <span style={{ color: WS_COLOR[ws] ?? o.color }}>●</span> {ws}
                          </div>
                        ))}
                      </div>
                    )}

                    <div>
                      <div style={{ fontSize: 8, color: "#475569", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>
                        Progress
                      </div>
                      <div style={{ height: 4, background: "#1e293b", borderRadius: 2, overflow: "hidden" }}>
                        <div style={{
                          height: "100%",
                          width: `${stats.total ? (stats.doneCount / stats.total) * 100 : 0}%`,
                          background: o.color,
                          borderRadius: 2,
                          transition: "width 0.3s",
                        }} />
                      </div>
                      <div style={{ marginTop: 3, fontSize: 9, color: "#475569" }}>
                        {stats.doneCount} of {stats.total} tasks
                      </div>
                    </div>

                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                      <div>
                        <div style={{ fontSize: 8, color: "#475569", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 2 }}>
                          Completed
                        </div>
                        <div style={{ fontSize: 13, fontWeight: 700, color: "#22c55e" }}>
                          {fmtHours(stats.hoursCompleted)}
                        </div>
                      </div>
                      <div>
                        <div style={{ fontSize: 8, color: "#475569", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 2 }}>
                          Remaining
                        </div>
                        <div style={{ fontSize: 13, fontWeight: 700, color: o.color }}>
                          {fmtHours(stats.hoursRemaining)}
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })
        ) : (
          /* ── Workstream list ── */
          WORKSTREAMS.map((ws) => {
            const isHovered = hoveredWs === ws.id;
            const isExpanded = expandedWs === ws.id;
            const stats = wsStats(ws.id);

            return (
              <div key={ws.id}>
                <div
                  onMouseEnter={() => handleWsHover(ws.id)}
                  onMouseLeave={() => handleWsHover(null)}
                  onClick={() => setExpandedWs(isExpanded ? null : ws.id)}
                  style={{
                    padding: "9px 14px",
                    cursor: "pointer",
                    background: isHovered || isExpanded ? `${ws.color}18` : "transparent",
                    borderLeft: `3px solid ${isHovered || isExpanded ? ws.color : "transparent"}`,
                    transition: "background 0.12s, border-color 0.12s",
                    display: "flex",
                    flexDirection: "column",
                    gap: 2,
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: 9, fontWeight: 700, color: ws.color, letterSpacing: "0.05em" }}>
                      {ws.id}
                    </span>
                    <span style={{ fontSize: 9, color: "#475569", transition: "transform 0.15s", display: "inline-block", transform: isExpanded ? "rotate(90deg)" : "none" }}>
                      ▶
                    </span>
                  </div>
                  <span style={{ fontSize: 11, fontWeight: 600, color: isHovered || isExpanded ? "#f1f5f9" : "#94a3b8" }}>
                    {ws.name}
                  </span>
                  <span style={{ fontSize: 9, color: "#475569" }}>
                    {stats.doneCount}/{stats.total} done
                  </span>
                </div>

                {isExpanded && (
                  <div
                    style={{
                      background: `${ws.color}0d`,
                      borderLeft: `3px solid ${ws.color}44`,
                      padding: "10px 14px 12px",
                      display: "flex",
                      flexDirection: "column",
                      gap: 10,
                    }}
                  >
                    {workstreamScopes[ws.id] && (
                      <div style={{ fontSize: 9, color: "#64748b", lineHeight: 1.5 }}>
                        {workstreamScopes[ws.id]}
                      </div>
                    )}

                    {workstreamOwners[ws.id] && (
                      <div>
                        <div style={{ fontSize: 8, color: "#475569", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 3 }}>
                          Owner
                        </div>
                        <div style={{ fontSize: 10, color: ws.color, fontWeight: 600 }}>
                          {workstreamOwners[ws.id]}
                        </div>
                      </div>
                    )}

                    {stats.assignees.length > 0 && (
                      <div>
                        <div style={{ fontSize: 8, color: "#475569", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 4 }}>
                          On this workstream
                        </div>
                        {stats.assignees.map((a) => (
                          <div key={a} style={{ fontSize: 10, color: "#94a3b8", display: "flex", alignItems: "center", gap: 4 }}>
                            <span style={{ color: OWNER_COLOR[a] ?? ws.color }}>●</span> {a}
                          </div>
                        ))}
                      </div>
                    )}

                    <div>
                      <div style={{ fontSize: 8, color: "#475569", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>
                        Progress
                      </div>
                      <div style={{ height: 4, background: "#1e293b", borderRadius: 2, overflow: "hidden" }}>
                        <div style={{
                          height: "100%",
                          width: `${stats.total ? (stats.doneCount / stats.total) * 100 : 0}%`,
                          background: ws.color,
                          borderRadius: 2,
                          transition: "width 0.3s",
                        }} />
                      </div>
                      <div style={{ marginTop: 3, fontSize: 9, color: "#475569" }}>
                        {stats.doneCount} of {stats.total} tasks
                      </div>
                    </div>

                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                      <div>
                        <div style={{ fontSize: 8, color: "#475569", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 2 }}>
                          Completed
                        </div>
                        <div style={{ fontSize: 13, fontWeight: 700, color: "#22c55e" }}>
                          {fmtHours(stats.hoursCompleted)}
                        </div>
                      </div>
                      <div>
                        <div style={{ fontSize: 8, color: "#475569", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 2 }}>
                          Remaining
                        </div>
                        <div style={{ fontSize: 13, fontWeight: 700, color: ws.color }}>
                          {fmtHours(stats.hoursRemaining)}
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Main canvas */}
      <div style={{ flex: 1, position: "relative" }}>
        {/* Top bar */}
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            zIndex: 10,
            padding: "10px 20px",
            background: "rgba(15, 23, 42, 0.88)",
            borderBottom: "1px solid #1e293b",
            backdropFilter: "blur(10px)",
            display: "flex",
            alignItems: "center",
            gap: 28,
          }}
        >
          <span style={{ fontWeight: 800, fontSize: 14, color: "#f1f5f9", letterSpacing: "-0.01em" }}>
            Project Flow
          </span>

          <div style={{ width: 1, height: 20, background: "#1e293b" }} />

          <StatPill label="Total" value={tasks.length} />
          <StatPill label="P0" value={p0} color="#ef4444" />
          <StatPill label="Done" value={`${done} / ${tasks.length}`} color="#22c55e" />
          <StatPill label="Active" value={inProgress} color="#3b82f6" />
          <StatPill label="Blocked" value={blocked} color={blocked > 0 ? "#ef4444" : "#64748b"} />
          <StatPill label="Human steps" value={humanSteps} color="#f59e0b" />

          {/* Right-side controls */}
          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 16 }}>
            {/* View toggle */}
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 9, color: "#475569", textTransform: "uppercase", letterSpacing: "0.07em" }}>
                View
              </span>
              <div style={{ display: "flex", gap: 2, background: "#1e293b", borderRadius: 6, padding: 3 }}>
                {(["graph", "gantt"] as const).map((v) => (
                  <button
                    key={v}
                    onClick={() => setViewMode(v)}
                    style={{
                      padding: "3px 10px",
                      borderRadius: 4,
                      border: "none",
                      cursor: "pointer",
                      fontSize: 10,
                      fontWeight: 600,
                      transition: "background 0.12s, color 0.12s",
                      background: viewMode === v ? "#334155" : "transparent",
                      color: viewMode === v ? "#f1f5f9" : "#64748b",
                    }}
                  >
                    {v === "graph" ? "Graph" : "Gantt"}
                  </button>
                ))}
              </div>
            </div>

            <div style={{ width: 1, height: 16, background: "#1e293b" }} />

            {/* Color mode toggle */}
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 9, color: "#475569", textTransform: "uppercase", letterSpacing: "0.07em" }}>
                Color by
              </span>
              <div style={{ display: "flex", gap: 2, background: "#1e293b", borderRadius: 6, padding: 3 }}>
                {(["workstream", "owner"] as const).map((mode) => (
                  <button
                    key={mode}
                    onMouseEnter={() => setPreviewMode(mode)}
                    onMouseLeave={() => setPreviewMode(null)}
                    onClick={() => setColorMode(mode)}
                    style={{
                      padding: "3px 10px",
                      borderRadius: 4,
                      border: "none",
                      cursor: "pointer",
                      fontSize: 10,
                      fontWeight: 600,
                      transition: "background 0.12s, color 0.12s",
                      background: colorMode === mode ? "#334155" : "transparent",
                      color: colorMode === mode ? "#f1f5f9" : "#64748b",
                    }}
                  >
                    {mode === "workstream" ? "Workstream" : "Owner"}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {generatedAt && (
            <span style={{ fontSize: 10, color: "#334155" }}>
              {relativeTime(generatedAt)}
            </span>
          )}
        </div>

        {viewMode === "graph" && (
          <>
            {/* Legend */}
            <div
              style={{
                position: "absolute",
                bottom: 16,
                left: 16,
                zIndex: 10,
                background: "rgba(15, 23, 42, 0.88)",
                border: "1px solid #1e293b",
                borderRadius: 8,
                padding: "10px 14px",
                backdropFilter: "blur(10px)",
                display: "flex",
                flexDirection: "column",
                gap: 5,
              }}
            >
              {(
                [
                  ["open", "Open"],
                  ["in_progress", "In Progress"],
                  ["in_review", "In Review"],
                  ["blocked", "Blocked"],
                  ["closed", "Done"],
                  ["deferred", "Deferred"],
                ] as [TaskStatus, string][]
              ).map(([status, label]) => (
                <div key={status} style={{ display: "flex", alignItems: "center", gap: 7 }}>
                  <div style={{ width: 8, height: 8, borderRadius: "50%", background: STATUS_COLOR[status] }} />
                  <span style={{ fontSize: 10, color: "#94a3b8" }}>{label}</span>
                </div>
              ))}
              <div style={{ borderTop: "1px solid #1e293b", marginTop: 3, paddingTop: 6 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                  <span style={{ fontSize: 10 }}>⚠️</span>
                  <span style={{ fontSize: 10, color: "#94a3b8" }}>Human required</span>
                </div>
              </div>
            </div>

            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              nodeTypes={nodeTypes}
              fitView
              fitViewOptions={{ padding: 0.15 }}
              minZoom={0.2}
              maxZoom={2}
              style={{ background: "#0f172a", width: "100%", height: "100%" }}
            >
              <Background color="#1e293b" gap={24} size={1} />
              <Controls style={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8 }} />
              <MiniMap
                style={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8 }}
                nodeColor={(node) => STATUS_COLOR[(node.data as Task).status] ?? "#64748b"}
                maskColor="rgba(15, 23, 42, 0.7)"
                zoomable
                pannable
              />
            </ReactFlow>
          </>
        )}

        {viewMode === "gantt" && (
          <div style={{ position: "absolute", inset: 0, paddingTop: 44, boxSizing: "border-box" }}>
            <GanttView
              tasks={tasks}
              colorMode={activeMode}
              workstreams={WORKSTREAMS}
              ownerColor={OWNER_COLOR}
              workstreamOwners={workstreamOwners}
            />
          </div>
        )}
      </div>
    </div>
  );
}
