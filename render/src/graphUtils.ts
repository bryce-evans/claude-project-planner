import Dagre from "@dagrejs/dagre";
import type { Node, Edge } from "@xyflow/react";
import type { Task } from "./types";
import type { ColorMode } from "./types";
import { STATUS_GROUPS, NODE_W, NODE_H } from "./constants";
import { STATUS_COLOR } from "./utils";

export function getTaskColor(
  task: Task,
  mode: ColorMode,
  wsColor: Record<string, string>,
  ownerColor: Record<string, string>,
): string {
  if (mode === "status") return STATUS_GROUPS.find((g) => g.statuses.has(task.status))?.color ?? "#334155";
  if (mode === "owner") return task.assignee ? (ownerColor[task.assignee] ?? "#334155") : "#334155";
  return wsColor[task.workstream.split("—")[0].trim()] ?? "#334155";
}

export function buildGraph(
  tasks: Task[],
  mode: ColorMode,
  wsColor: Record<string, string>,
  ownerColor: Record<string, string>,
): { nodes: Node[]; edges: Edge[] } {
  const g = new Dagre.graphlib.Graph();
  g.setGraph({ rankdir: "LR", nodesep: 48, ranksep: 96, marginx: 40, marginy: 40 });
  g.setDefaultEdgeLabel(() => ({}));

  const taskIds = new Set(tasks.map((t) => t.id));
  const taskMap = new Map(tasks.map((t) => [t.id, t]));

  tasks.forEach((t) => g.setNode(t.id, { width: NODE_W, height: NODE_H }));
  tasks.forEach((t) => {
    t.depends.forEach((depId) => {
      if (taskIds.has(depId)) g.setEdge(depId, t.id);
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
        const sourceTask = taskMap.get(depId);
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
