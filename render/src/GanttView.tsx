import { useState, useMemo } from "react";
import type { Task } from "./types";
import type { ColorMode, Owner } from "./types";
import { STATUS_COLOR, parseHours } from "./utils";
import { STATUS_GROUPS } from "./constants";

const PX_PER_HR = 32;
const HOURS_PER_DAY = 8;
const LANE_H = 46;
const BAR_H = 30;
const BAR_INSET = (LANE_H - BAR_H) / 2;
const ROW_PAD = 10;
const HEADER_W = 188;
const RULER_H = 38;
const MIN_BAR_W = 36;

// ---------------------------------------------------------------------------
// Topological longest-path: compute start time (hours) per task
// ---------------------------------------------------------------------------

function computeStartTimes(tasks: Task[]): Record<string, { startHr: number; durationHr: number }> {
  const taskMap = new Map(tasks.map((t) => [t.id, t]));
  const dur: Record<string, number> = {};
  for (const t of tasks) dur[t.id] = Math.max(parseHours(t.estimate), 1);

  const children: Record<string, string[]> = Object.fromEntries(tasks.map((t) => [t.id, []]));
  const inDeg: Record<string, number> = Object.fromEntries(tasks.map((t) => [t.id, 0]));
  for (const t of tasks) {
    for (const depId of t.depends) {
      if (taskMap.has(depId)) {
        children[depId].push(t.id);
        inDeg[t.id]++;
      }
    }
  }

  const startHr: Record<string, number> = Object.fromEntries(tasks.map((t) => [t.id, 0]));
  const queue = tasks.filter((t) => inDeg[t.id] === 0).map((t) => t.id);

  while (queue.length > 0) {
    const id = queue.shift()!;
    const endHr = startHr[id] + dur[id];
    for (const childId of children[id]) {
      startHr[childId] = Math.max(startHr[childId], endHr);
      if (--inDeg[childId] === 0) queue.push(childId);
    }
  }

  return Object.fromEntries(
    tasks.map((t) => [t.id, { startHr: startHr[t.id], durationHr: dur[t.id] }])
  );
}

// ---------------------------------------------------------------------------
// Lane packing: greedy interval scheduling within a row
// Returns the lane index (0-based) per task and total lane count for the row.
// ---------------------------------------------------------------------------

function assignLanes(
  rowTasks: Task[],
  layout: Record<string, { startHr: number; durationHr: number }>
): { lanes: Record<string, number>; numLanes: number } {
  const sorted = [...rowTasks].sort(
    (a, b) => (layout[a.id]?.startHr ?? 0) - (layout[b.id]?.startHr ?? 0)
  );

  const laneEnds: number[] = []; // endHr of the last task in each lane
  const lanes: Record<string, number> = {};

  for (const task of sorted) {
    const { startHr, durationHr } = layout[task.id] ?? { startHr: 0, durationHr: 1 };
    let placed = false;
    for (let i = 0; i < laneEnds.length; i++) {
      if (laneEnds[i] <= startHr) {
        lanes[task.id] = i;
        laneEnds[i] = startHr + durationHr;
        placed = true;
        break;
      }
    }
    if (!placed) {
      lanes[task.id] = laneEnds.length;
      laneEnds.push(startHr + durationHr);
    }
  }

  return { lanes, numLanes: Math.max(laneEnds.length, 1) };
}

// ---------------------------------------------------------------------------
// Row grouping
// ---------------------------------------------------------------------------

interface GanttRow {
  id: string;
  label: string;
  sublabel?: string;
  color: string;
  tasks: Task[];
}

function buildRows(
  tasks: Task[],
  colorMode: ColorMode,
  workstreams: { id: string; name: string; color: string }[],
  ownerColor: Record<string, string>,
  owners: { id: string; color: string }[],
): GanttRow[] {
  if (colorMode === "owner") {
    // Seed map from full owners list so team members with no tasks still get a row
    const ownerMap = new Map<string, Task[]>(owners.map((o) => [o.id, []]));
    for (const t of tasks) {
      const key = t.assignee ?? "(unassigned)";
      if (!ownerMap.has(key)) ownerMap.set(key, []);
      ownerMap.get(key)!.push(t);
    }
    return Array.from(ownerMap.entries()).map(([owner, rowTasks]) => ({
      id: owner,
      label: owner,
      color: ownerColor[owner] ?? "#64748b",
      tasks: rowTasks,
    }));
  }

  if (colorMode === "status") {
    return STATUS_GROUPS
      .map((g) => ({ ...g, tasks: tasks.filter((t) => g.statuses.has(t.status)) }))
      .filter((r) => r.tasks.length > 0);
  }

  return workstreams
    .map((ws) => ({
      id: ws.id,
      label: ws.id,
      sublabel: ws.name,
      color: ws.color,
      tasks: tasks.filter((t) => t.workstream.split("—")[0].trim() === ws.id),
    }))
    .filter((r) => r.tasks.length > 0);
}

// ---------------------------------------------------------------------------
// Tooltip
// ---------------------------------------------------------------------------

function Tooltip({ task, x, y }: { task: Task; x: number; y: number }) {
  return (
    <div
      style={{
        position: "fixed",
        left: x + 14,
        top: y - 10,
        zIndex: 200,
        background: "#1e293b",
        border: "1px solid #334155",
        borderRadius: 8,
        padding: "10px 14px",
        maxWidth: 280,
        pointerEvents: "none",
        boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
      }}
    >
      <div style={{ fontSize: 12, fontWeight: 700, color: "#f1f5f9", marginBottom: 6 }}>
        {task.id} · {task.title ?? task.id}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
        {task.estimate && <TRow label="Estimate" value={task.estimate} />}
        {task.assignee && <TRow label="Assignee" value={task.assignee} />}
        <TRow label="Status" value={task.status} color={STATUS_COLOR[task.status]} />
        {task.depends.length > 0 && <TRow label="Depends" value={task.depends.join(", ")} />}
        {task.humanRequired && <TRow label="⚠ Human" value={task.humanRequired} color="#f59e0b" />}
      </div>
    </div>
  );
}

function TRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ display: "flex", gap: 6, fontSize: 10 }}>
      <span style={{ color: "#64748b", minWidth: 54 }}>{label}</span>
      <span style={{ color: color ?? "#94a3b8" }}>{value}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface GanttViewProps {
  tasks: Task[];
  colorMode: ColorMode;
  workstreams: { id: string; name: string; color: string }[];
  owners: Owner[];
  ownerColor: Record<string, string>;
  workstreamOwners: Record<string, string>;
  onTaskClick?: (task: Task) => void;
}

export default function GanttView({ tasks, colorMode, workstreams, owners, ownerColor, onTaskClick }: GanttViewProps) {
  const [tooltip, setTooltip] = useState<{ task: Task; x: number; y: number } | null>(null);

  const layout = useMemo(() => computeStartTimes(tasks), [tasks]);
  const rows = useMemo(() => buildRows(tasks, colorMode, workstreams, ownerColor, owners), [tasks, colorMode, workstreams, ownerColor, owners]);

  const maxEndHr = Math.max(
    0,
    ...tasks.map((t) => (layout[t.id]?.startHr ?? 0) + (layout[t.id]?.durationHr ?? 0))
  );
  const totalHours = maxEndHr + HOURS_PER_DAY;
  const totalWidth = Math.max(totalHours * PX_PER_HR, 800);
  const dayCount = Math.ceil(totalHours / HOURS_PER_DAY) + 1;
  const days = Array.from({ length: dayCount }, (_, i) => i);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <div style={{ flex: 1, overflow: "auto", position: "relative" }}>

        {/* Sticky ruler */}
        <div
          style={{
            display: "flex",
            position: "sticky",
            top: 0,
            zIndex: 30,
            height: RULER_H,
            background: "#0f172a",
            borderBottom: "1px solid #1e293b",
          }}
        >
          <div
            style={{
              width: HEADER_W,
              flexShrink: 0,
              position: "sticky",
              left: 0,
              zIndex: 31,
              background: "#0f172a",
              borderRight: "1px solid #1e293b",
              display: "flex",
              alignItems: "center",
              paddingLeft: 16,
            }}
          >
            <span style={{ fontSize: 9, color: "#475569", textTransform: "uppercase", letterSpacing: "0.08em" }}>
              {colorMode === "owner" ? "Owner" : "Workstream"}
            </span>
          </div>
          <div style={{ position: "relative", width: totalWidth, flexShrink: 0 }}>
            {days.map((d) => (
              <div
                key={d}
                style={{
                  position: "absolute",
                  left: d * HOURS_PER_DAY * PX_PER_HR,
                  top: 0,
                  height: "100%",
                  display: "flex",
                  alignItems: "center",
                  paddingLeft: 6,
                  borderLeft: d === 0 ? "none" : "1px solid #1e293b",
                }}
              >
                <span style={{ fontSize: 9, color: d === 0 ? "#475569" : "#334155", whiteSpace: "nowrap" }}>
                  {d === 0 ? "Start" : `Day ${d + 1}`}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Rows */}
        {rows.map((row, rowIdx) => {
          const { lanes, numLanes } = assignLanes(row.tasks, layout);
          const rowH = numLanes * LANE_H + ROW_PAD * 2;

          return (
            <div
              key={row.id}
              style={{
                display: "flex",
                height: rowH,
                borderBottom: "1px solid #1e293b",
                background: rowIdx % 2 === 0 ? "transparent" : "rgba(255,255,255,0.012)",
              }}
            >
              {/* Sticky row header */}
              <div
                style={{
                  width: HEADER_W,
                  flexShrink: 0,
                  position: "sticky",
                  left: 0,
                  zIndex: 10,
                  background: rowIdx % 2 === 0 ? "#0f172a" : "#0f1726",
                  borderRight: "1px solid #1e293b",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "center",
                  paddingLeft: 16,
                  paddingRight: 10,
                  gap: 2,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <div style={{ width: 6, height: 6, borderRadius: "50%", background: row.color, flexShrink: 0 }} />
                  <span style={{ fontSize: 10, fontWeight: 700, color: row.color }}>{row.label}</span>
                </div>
                {row.sublabel && (
                  <span style={{ fontSize: 10, color: "#64748b", paddingLeft: 12 }}>{row.sublabel}</span>
                )}
                <span style={{ fontSize: 9, color: "#334155", paddingLeft: 12 }}>
                  {row.tasks.length} task{row.tasks.length !== 1 ? "s" : ""}
                  {numLanes > 1 && <span style={{ color: "#475569" }}> · {numLanes} parallel</span>}
                </span>
              </div>

              {/* Task bars */}
              <div style={{ position: "relative", width: totalWidth, flexShrink: 0 }}>
                {/* Day grid lines */}
                {days.map((d) => d > 0 && (
                  <div
                    key={d}
                    style={{
                      position: "absolute",
                      left: d * HOURS_PER_DAY * PX_PER_HR,
                      top: 0,
                      bottom: 0,
                      width: 1,
                      background: "#1e293b",
                    }}
                  />
                ))}

                {row.tasks.map((task) => {
                  const { startHr, durationHr } = layout[task.id] ?? { startHr: 0, durationHr: 1 };
                  const lane = lanes[task.id] ?? 0;
                  const left = startHr * PX_PER_HR;
                  const width = Math.max(durationHr * PX_PER_HR, MIN_BAR_W);
                  const top = ROW_PAD + lane * LANE_H + BAR_INSET;

                  const isDone = task.status === "closed" || task.status === "done";
                  const isBlocked = task.status === "blocked";
                  const isActive = task.status === "in_progress" || task.status === "in_review";

                  return (
                    <div
                      key={task.id}
                      onMouseEnter={(e) => setTooltip({ task, x: e.clientX, y: e.clientY })}
                      onMouseMove={(e) => setTooltip({ task, x: e.clientX, y: e.clientY })}
                      onMouseLeave={() => setTooltip(null)}
                      onClick={() => onTaskClick?.(task)}
                      style={{
                        position: "absolute",
                        left,
                        top,
                        width,
                        height: BAR_H,
                        borderRadius: 5,
                        background: isDone
                          ? `${row.color}44`
                          : isBlocked
                          ? "#ef444422"
                          : `${row.color}33`,
                        border: `1.5px solid ${isBlocked ? "#ef4444" : isActive ? row.color : `${row.color}88`}`,
                        display: "flex",
                        alignItems: "center",
                        paddingLeft: 7,
                        paddingRight: 5,
                        cursor: "pointer",
                        overflow: "hidden",
                        boxSizing: "border-box",
                        opacity: isDone ? 0.6 : 1,
                      }}
                    >
                      {task.humanRequired && (
                        <span style={{ fontSize: 9, marginRight: 3, flexShrink: 0 }}>⚠️</span>
                      )}
                      <span
                        style={{
                          fontSize: 10,
                          fontWeight: 600,
                          color: isDone ? "#64748b" : isBlocked ? "#ef4444" : "#cbd5e1",
                          whiteSpace: "nowrap",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                        }}
                      >
                        {task.id}
                        {width > 80 && ` · ${task.title ?? ""}`}
                      </span>
                      {isDone && (
                        <span style={{ fontSize: 9, marginLeft: "auto", flexShrink: 0, paddingRight: 2, color: "#22c55e" }}>✓</span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      {tooltip && <Tooltip task={tooltip.task} x={tooltip.x} y={tooltip.y} />}
    </div>
  );
}
