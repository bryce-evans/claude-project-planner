import { useMemo, useCallback, useState, useEffect, useRef } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type NodeTypes,
} from "@xyflow/react";
import TaskNode from "./TaskNode";
import GanttView from "./GanttView";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import type { Task, TaskData, ColorMode, ViewMode, Workstream, Owner } from "./types";
import { STATUS_COLOR } from "./utils";
import { COLOR_PALETTE, STATUS_GROUPS, POLL_MS } from "./constants";
import { buildGraph, getTaskColor } from "./graphUtils";

const EMPTY: TaskData = { tasks: [], generatedAt: "", workstreamScopes: {}, workstreamOwners: {}, team: [] };
const nodeTypes: NodeTypes = { taskNode: TaskNode as never };

export default function App() {
  const [data, setData] = useState<TaskData>(EMPTY);
  const [viewMode, setViewMode] = useState<ViewMode>("graph");
  const [colorMode, setColorMode] = useState<ColorMode>("workstream");
  const [previewMode, setPreviewMode] = useState<ColorMode | null>(null);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const activeMode = previewMode ?? colorMode;
  const lastGeneratedAt = useRef("");

  const { tasks, generatedAt, workstreamScopes, workstreamOwners, team } = data;

  const WORKSTREAMS = useMemo<Workstream[]>(() =>
    Array.from(
      new Map(tasks.map((t) => [t.workstream.split("—")[0].trim(), t.workstream])).entries()
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
    const fromTasks = tasks.map((t) => t.assignee).filter(Boolean) as string[];
    const all = Array.from(new Set([...team, ...fromTasks]));
    return Object.fromEntries(all.map((o, i) => [o, COLOR_PALETTE[i % COLOR_PALETTE.length]]));
  }, [tasks, team]);

  const OWNERS = useMemo<Owner[]>(() => {
    const fromTasks = tasks.map((t) => t.assignee).filter(Boolean) as string[];
    const all = Array.from(new Set([...team, ...fromTasks]));
    const assigned = all.map((owner) => ({ id: owner, color: OWNER_COLOR[owner] ?? "#64748b" }));
    return tasks.some((t) => !t.assignee) ? [...assigned, { id: "(unassigned)", color: "#64748b" }] : assigned;
  }, [tasks, team, OWNER_COLOR]);

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch("/tasks.json");
      if (!res.ok) return;
      const json: TaskData = await res.json();
      if (json.generatedAt !== lastGeneratedAt.current) {
        lastGeneratedAt.current = json.generatedAt;
        setData(json);
      }
    } catch { /* network error — keep current data */ }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, POLL_MS);
    return () => clearInterval(interval);
  }, [fetchData]);

  useEffect(() => {
    if (selectedTask) {
      setSelectedTask(tasks.find((t) => t.id === selectedTask.id) ?? null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tasks]);

  const updateTask = useCallback(async (beadsId: string, field: string, value: string) => {
    try {
      const res = await fetch("/task/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ beadsId, field, value }),
      });
      if (res.ok) { lastGeneratedAt.current = ""; setTimeout(fetchData, 600); }
    } catch { /* ignore */ }
  }, [fetchData]);

  const { nodes: initNodes, edges: initEdges } = useMemo(
    () => buildGraph(tasks, colorMode, WS_COLOR, OWNER_COLOR),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [tasks]
  );
  const [nodes, setNodes, onNodesChange] = useNodesState(initNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initEdges);

  useEffect(() => {
    const { nodes: n, edges: e } = buildGraph(tasks, colorMode, WS_COLOR, OWNER_COLOR);
    setNodes(n);
    setEdges(e);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tasks]);

  useEffect(() => {
    setNodes((nds) =>
      nds.map((n) => ({ ...n, data: { ...n.data, wsColor: getTaskColor(n.data as Task, activeMode, WS_COLOR, OWNER_COLOR) } }))
    );
  }, [activeMode, setNodes, WS_COLOR, OWNER_COLOR]);

  const onWsHover = useCallback((wsId: string | null) => {
    setNodes((nds) => nds.map((n) => {
      const task = n.data as Task;
      return { ...n, data: { ...task, dimmed: wsId !== null && task.workstream.split("—")[0].trim() !== wsId } };
    }));
  }, [setNodes]);

  const onOwnerHover = useCallback((owner: string | null) => {
    setNodes((nds) => nds.map((n) => {
      const task = n.data as Task;
      const matches = owner === "(unassigned)" ? !task.assignee : task.assignee === owner;
      return { ...n, data: { ...task, dimmed: owner !== null && !matches } };
    }));
  }, [setNodes]);

  const onStatusHover = useCallback((groupId: string | null) => {
    setNodes((nds) => nds.map((n) => {
      const task = n.data as Task;
      const group = STATUS_GROUPS.find((g) => g.statuses.has(task.status));
      return { ...n, data: { ...task, dimmed: groupId !== null && group?.id !== groupId } };
    }));
  }, [setNodes]);

  if (!tasks.length) {
    return (
      <div style={{ width: "100vw", height: "100vh", background: "#0f172a", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <span style={{ color: "#475569", fontSize: 14 }}>Loading tasks…</span>
      </div>
    );
  }

  return (
    <div style={{ width: "100vw", height: "100vh", background: "#0f172a", display: "flex" }}>
      <Sidebar
        tasks={tasks}
        activeMode={activeMode}
        workstreams={WORKSTREAMS}
        owners={OWNERS}
        WS_COLOR={WS_COLOR}
        OWNER_COLOR={OWNER_COLOR}
        workstreamScopes={workstreamScopes}
        workstreamOwners={workstreamOwners}
        onWsHover={onWsHover}
        onOwnerHover={onOwnerHover}
        onStatusHover={onStatusHover}
        selectedTask={selectedTask}
        onUpdateTask={updateTask}
      />

      <div style={{ flex: 1, position: "relative" }}>
        <TopBar
          tasks={tasks}
          generatedAt={generatedAt}
          viewMode={viewMode}
          colorMode={colorMode}
          onViewChange={setViewMode}
          onColorChange={setColorMode}
          onColorPreview={setPreviewMode}
        />

        {viewMode === "graph" && (
          <>
            <div style={{ position: "absolute", bottom: 16, left: 16, zIndex: 10, background: "rgba(15, 23, 42, 0.88)", border: "1px solid #1e293b", borderRadius: 8, padding: "10px 14px", backdropFilter: "blur(10px)", display: "flex", flexDirection: "column", gap: 5 }}>
              {(["open", "in_progress", "in_review", "blocked", "closed", "deferred"] as const).map((status) => (
                <div key={status} style={{ display: "flex", alignItems: "center", gap: 7 }}>
                  <div style={{ width: 8, height: 8, borderRadius: "50%", background: STATUS_COLOR[status] }} />
                  <span style={{ fontSize: 10, color: "#94a3b8" }}>{{ open: "Open", in_progress: "In Progress", in_review: "In Review", blocked: "Blocked", closed: "Done", deferred: "Deferred" }[status]}</span>
                </div>
              ))}
              <div style={{ borderTop: "1px solid #1e293b", marginTop: 3, paddingTop: 6, display: "flex", alignItems: "center", gap: 7 }}>
                <span style={{ fontSize: 10 }}>⚠️</span>
                <span style={{ fontSize: 10, color: "#94a3b8" }}>Human required</span>
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
              onNodeClick={(_e, node: Node) => setSelectedTask(tasks.find((t) => t.id === node.id) ?? null)}
              onPaneClick={() => setSelectedTask(null)}
            >
              <Background color="#1e293b" gap={24} size={1} />
              <Controls position="bottom-right" style={{ bottom: 168, right: 10 }} />
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
              owners={OWNERS}
              ownerColor={OWNER_COLOR}
              workstreamOwners={workstreamOwners}
              onTaskClick={setSelectedTask}
            />
          </div>
        )}
      </div>
    </div>
  );
}
