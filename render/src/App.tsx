import { useMemo, useCallback, useState } from "react";
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
import { tasks, generatedAt } from "./generated/tasks";
import TaskNode from "./TaskNode";
import type { Task, TaskStatus } from "./types";
import { STATUS_COLOR, relativeTime } from "./utils";

const NODE_W = 224;
const NODE_H = 148;

function buildGraph(tasks: Task[]): { nodes: Node[]; edges: Edge[] } {
  const g = new Dagre.graphlib.Graph();
  g.setGraph({ rankdir: "LR", nodesep: 48, ranksep: 96, marginx: 40, marginy: 40 });
  g.setDefaultEdgeLabel(() => ({}));

  const taskIds = new Set(tasks.map((t) => t.id));

  tasks.forEach((t) => {
    g.setNode(t.id, { width: NODE_W, height: NODE_H });
  });

  // Edges go from dependency → dependent (direction of work flow)
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
      data: t,
    };
  });

  const edges: Edge[] = tasks.flatMap((t) =>
    t.depends
      .filter((depId) => taskIds.has(depId))
      .map((depId) => {
        const sourceTask = tasks.find((x) => x.id === depId);
        const isActive =
          t.status === "in_progress" || t.status === "in_review";
        const isBlocked = t.status === "blocked";
        const color = isBlocked
          ? "#ef4444"
          : isActive
          ? STATUS_COLOR[t.status]
          : "#334155";
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

// ---------------------------------------------------------------------------
// Estimate parsing
// ---------------------------------------------------------------------------

function parseHours(est: string): number {
  const s = est.toLowerCase().trim();
  if (s.endsWith("w")) return parseFloat(s) * 40;
  if (s.endsWith("d")) return parseFloat(s) * 8;
  if (s.endsWith("h")) return parseFloat(s);
  return 0;
}

function fmtHours(h: number): string {
  if (h === 0) return "—";
  if (h >= 40 && h % 40 === 0) return `${h / 40}w`;
  if (h >= 8 && h % 8 === 0) return `${h / 8}d`;
  return `${h}h`;
}

const DONE_STATUSES = new Set(["done", "closed"]);
const ACTIVE_STATUSES = new Set(["in_progress", "in-progress", "in_review", "in-review", "hooked"]);

// ---------------------------------------------------------------------------
// Per-workstream stats
// ---------------------------------------------------------------------------

function wsStats(wsId: string) {
  const wsTasks = tasks.filter((t) => t.workstream.split("—")[0].trim() === wsId);
  const done = wsTasks.filter((t) => DONE_STATUSES.has(t.status));
  const remaining = wsTasks.filter((t) => !DONE_STATUSES.has(t.status));
  const assignees = Array.from(
    new Set(wsTasks.map((t) => t.assignee).filter(Boolean) as string[])
  );
  return {
    total: wsTasks.length,
    doneCount: done.length,
    hoursCompleted: done.reduce((s, t) => s + parseHours(t.estimate), 0),
    hoursRemaining: remaining.reduce((s, t) => s + parseHours(t.estimate), 0),
    assignees,
  };
}

function StatPill({
  label,
  value,
  color,
}: {
  label: string;
  value: string | number;
  color?: string;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
      <span
        style={{
          fontSize: 9,
          color: "#475569",
          textTransform: "uppercase",
          letterSpacing: "0.07em",
        }}
      >
        {label}
      </span>
      <span style={{ fontSize: 13, fontWeight: 700, color: color ?? "#e2e8f0" }}>
        {value}
      </span>
    </div>
  );
}

// Derive unique workstreams in order of first appearance
const WORKSTREAMS = Array.from(
  new Map(tasks.map((t) => [t.workstream.split("—")[0].trim(), t.workstream])).entries()
).map(([id, full]) => ({
  id,
  full,
  name: full.includes("—") ? full.split("—")[1].trim() : full,
  color: ["#6366f1", "#f59e0b", "#10b981", "#3b82f6", "#a855f7", "#ef4444"][
    Array.from(new Map(tasks.map((t) => [t.workstream.split("—")[0].trim(), t.workstream])).keys()).indexOf(id) % 6
  ],
}));

const WS_COLOR = Object.fromEntries(WORKSTREAMS.map((w) => [w.id, w.color]));

export default function App() {
  const { nodes: initNodes, edges: initEdges } = useMemo(
    () => buildGraph(tasks),
    []
  );
  const [nodes, setNodes, onNodesChange] = useNodesState(initNodes);
  const [edges, , onEdgesChange] = useEdgesState(initEdges);
  const [hoveredWs, setHoveredWs] = useState<string | null>(null);
  const [expandedWs, setExpandedWs] = useState<string | null>(null);

  const byStatus = useCallback(
    (s: TaskStatus) => tasks.filter((t) => t.status === s).length,
    []
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

  return (
    <div style={{ width: "100vw", height: "100vh", background: "#0f172a", display: "flex" }}>
      {/* Workstream sidebar */}
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
          Workstreams
        </div>
        {WORKSTREAMS.map((ws) => {
          const isHovered = hoveredWs === ws.id;
          const isExpanded = expandedWs === ws.id;
          const stats = wsStats(ws.id);

          return (
            <div key={ws.id}>
              {/* Row */}
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

              {/* Expanded detail panel */}
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
                  {/* Assignees */}
                  <div>
                    <div style={{ fontSize: 8, color: "#475569", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 4 }}>
                      Assigned to
                    </div>
                    {stats.assignees.length > 0 ? (
                      stats.assignees.map((a) => (
                        <div key={a} style={{ fontSize: 10, color: "#94a3b8", display: "flex", alignItems: "center", gap: 4 }}>
                          <span>👤</span> {a}
                        </div>
                      ))
                    ) : (
                      <div style={{ fontSize: 10, color: "#334155", fontStyle: "italic" }}>Unassigned</div>
                    )}
                  </div>

                  {/* Progress bar */}
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

                  {/* Hours */}
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
        })}
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
        <StatPill
          label="Done"
          value={`${done} / ${tasks.length}`}
          color="#22c55e"
        />
        <StatPill label="Active" value={inProgress} color="#3b82f6" />
        <StatPill label="Blocked" value={blocked} color={blocked > 0 ? "#ef4444" : "#64748b"} />
        <StatPill label="Human steps" value={humanSteps} color="#f59e0b" />

        {generatedAt && (
          <span style={{ marginLeft: "auto", fontSize: 10, color: "#334155" }}>
            Last updated {relativeTime(generatedAt)}
          </span>
        )}
      </div>

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
          <div
            key={status}
            style={{ display: "flex", alignItems: "center", gap: 7 }}
          >
            <div
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: STATUS_COLOR[status],
              }}
            />
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
        <Controls
          style={{
            background: "#1e293b",
            border: "1px solid #334155",
            borderRadius: 8,
          }}
        />
        <MiniMap
          style={{
            background: "#1e293b",
            border: "1px solid #334155",
            borderRadius: 8,
          }}
          nodeColor={(node) =>
            STATUS_COLOR[(node.data as Task).status] ?? "#64748b"
          }
          maskColor="rgba(15, 23, 42, 0.7)"
          zoomable
          pannable
        />
      </ReactFlow>
      </div>
    </div>
  );
}
