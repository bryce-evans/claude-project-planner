import { useState, useRef } from "react";
import type { Task } from "./types";
import { STATUS_COLOR, parseHours } from "./utils";

const PX_PER_HR = 32;
const HOURS_PER_DAY = 8;
const ROW_H = 60;
const BAR_H = 34;
const BAR_TOP = (ROW_H - BAR_H) / 2;
const HEADER_W = 188;
const RULER_H = 38;
const MIN_BAR_W = 36;

type ColorMode = "workstream" | "owner";

interface Row {
  id: string;
  label: string;
  sublabel?: string;
  color: string;
  tasks: Task[];
}

interface LayoutTask {
  task: Task;
  startHr: number;
  durationHr: number;
}

// ---------------------------------------------------------------------------
// Layout: topological longest-path to compute start times
// ---------------------------------------------------------------------------

function computeLayout(tasks: Task[]): Record<string, { startHr: number; durationHr: number }> {
  const taskMap: Record<string, Task> = Object.fromEntries(tasks.map((t) => [t.id, t]));

  const dur: Record<string, number> = {};
  for (const t of tasks) dur[t.id] = Math.max(parseHours(t.estimate), 1);

  // children[dep] = list of tasks that depend on dep
  const children: Record<string, string[]> = Object.fromEntries(tasks.map((t) => [t.id, []]));
  const inDeg: Record<string, number> = Object.fromEntries(tasks.map((t) => [t.id, 0]));
  for (const t of tasks) {
    for (const depId of t.depends) {
      if (taskMap[depId]) {
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

  return Object.fromEntries(tasks.map((t) => [t.id, { startHr: startHr[t.id], durationHr: dur[t.id] }]));
}

// ---------------------------------------------------------------------------
// Row grouping
// ---------------------------------------------------------------------------

function buildRows(
  tasks: Task[],
  colorMode: ColorMode,
  workstreams: { id: string; name: string; color: string }[],
  ownerColor: Record<string, string>,
  workstreamOwners: Record<string, string>,
): Row[] {
  if (colorMode === "owner") {
    const ownerMap = new Map<string, Task[]>();
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

  // workstream grouping
  return workstreams.map((ws) => ({
    id: ws.id,
    label: ws.id,
    sublabel: ws.name,
    color: ws.color,
    tasks: tasks.filter((t) => t.workstream.split("—")[0].trim() === ws.id),
  })).filter((r) => r.tasks.length > 0);
}

// ---------------------------------------------------------------------------
// Tooltip
// ---------------------------------------------------------------------------

interface TooltipProps {
  task: Task;
  x: number;
  y: number;
}

function Tooltip({ task, x, y }: TooltipProps) {
  return (
    <div
      style={{
        position: "fixed",
        left: x + 12,
        top: y - 8,
        zIndex: 100,
        background: "#1e293b",
        border: "1px solid #334155",
        borderRadius: 8,
        padding: "10px 14px",
        maxWidth: 280,
        pointerEvents: "none",
        boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
      }}
    >
      <div style={{ fontSize: 12, fontWeight: 700, color: "#f1f5f9", marginBottom: 6 }}>
        {task.id} · {task.title ?? task.id}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
        {task.estimate && (
          <Row label="Estimate" value={task.estimate} />
        )}
        {task.assignee && (
          <Row label="Assignee" value={task.assignee} />
        )}
        <Row label="Status" value={task.status} color={STATUS_COLOR[task.status]} />
        {task.depends.length > 0 && (
          <Row label="Depends" value={task.depends.join(", ")} />
        )}
        {task.humanRequired && (
          <Row label="⚠ Human" value={task.humanRequired} color="#f59e0b" />
        )}
      </div>
    </div>
  );
}

function Row({ label, value, color }: { label: string; value: string; color?: string }) {
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
  ownerColor: Record<string, string>;
  workstreamOwners: Record<string, string>;
}

export default function GanttView({
  tasks,
  colorMode,
  workstreams,
  ownerColor,
  workstreamOwners,
}: GanttViewProps) {
  const [tooltip, setTooltip] = useState<{ task: Task; x: number; y: number } | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const layout = computeLayout(tasks);
  const rows = buildRows(tasks, colorMode, workstreams, ownerColor, workstreamOwners);

  // Total chart width
  const maxEndHr = Math.max(
    0,
    ...tasks.map((t) => (layout[t.id]?.startHr ?? 0) + (layout[t.id]?.durationHr ?? 0))
  );
  const totalHours = maxEndHr + HOURS_PER_DAY; // padding
  const totalWidth = Math.max(totalHours * PX_PER_HR, 800);

  // Ruler: one tick per day
  const dayCount = Math.ceil(totalHours / HOURS_PER_DAY) + 1;
  const days = Array.from({ length: dayCount }, (_, i) => i);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      {/* Scrollable body */}
      <div ref={scrollRef} style={{ flex: 1, overflow: "auto", position: "relative" }}>
        {/* Sticky top-left corner + ruler */}
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
          {/* Corner cell */}
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

          {/* Day ticks */}
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
        {rows.map((row, rowIdx) => (
          <div
            key={row.id}
            style={{
              display: "flex",
              height: ROW_H,
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
                gap: 1,
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
                const left = startHr * PX_PER_HR;
                const width = Math.max(durationHr * PX_PER_HR, MIN_BAR_W);
                const isDone = task.status === "closed" || task.status === "done";
                const isBlocked = task.status === "blocked";
                const isActive = task.status === "in_progress" || task.status === "in_review";

                return (
                  <div
                    key={task.id}
                    onMouseEnter={(e) => setTooltip({ task, x: e.clientX, y: e.clientY })}
                    onMouseMove={(e) => setTooltip({ task, x: e.clientX, y: e.clientY })}
                    onMouseLeave={() => setTooltip(null)}
                    style={{
                      position: "absolute",
                      left,
                      top: BAR_TOP,
                      width,
                      height: BAR_H,
                      borderRadius: 5,
                      background: isDone
                        ? `${row.color}55`
                        : isBlocked
                        ? "#ef444433"
                        : `${row.color}33`,
                      border: `1.5px solid ${isBlocked ? "#ef4444" : isActive ? row.color : `${row.color}88`}`,
                      display: "flex",
                      alignItems: "center",
                      paddingLeft: 7,
                      paddingRight: 5,
                      cursor: "default",
                      overflow: "hidden",
                      boxSizing: "border-box",
                      opacity: isDone ? 0.65 : 1,
                      transition: "opacity 0.1s",
                    }}
                  >
                    {task.humanRequired && (
                      <span style={{ fontSize: 10, marginRight: 3, flexShrink: 0 }}>⚠️</span>
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
                      <span style={{ fontSize: 10, marginLeft: "auto", flexShrink: 0, paddingRight: 2, color: "#22c55e" }}>✓</span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {tooltip && <Tooltip task={tooltip.task} x={tooltip.x} y={tooltip.y} />}
    </div>
  );
}
