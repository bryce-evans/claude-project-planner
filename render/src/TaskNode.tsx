import { Handle, Position } from "@xyflow/react";
import type { Task } from "./types";
import { STATUS_COLOR, STATUS_LABEL, EVENT_LABEL, relativeTime } from "./utils";

interface Props {
  data: Task;
  selected: boolean;
}

export default function TaskNode({ data, selected }: Props) {
  const color = STATUS_COLOR[data.status];
  const latestEvent = data.events[data.events.length - 1];
  const wsName = data.workstream.includes("—")
    ? data.workstream.split("—")[1].trim()
    : data.workstream;

  const critColor =
    data.criticality === "P0"
      ? "#ef4444"
      : data.criticality === "P1"
      ? "#f59e0b"
      : "#64748b";

  return (
    <div
      style={{
        width: 224,
        background: "#1e293b",
        borderRadius: 8,
        border: `1.5px solid ${selected ? "#e2e8f0" : color}`,
        boxShadow: selected
          ? `0 0 0 3px ${color}55`
          : `0 2px 8px rgba(0,0,0,0.4)`,
        overflow: "hidden",
        fontFamily:
          '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        transition: "box-shadow 0.15s, border-color 0.15s",
      }}
    >
      <Handle
        type="target"
        position={Position.Left}
        style={{ background: color, width: 8, height: 8, border: "none" }}
      />

      {/* Header */}
      <div
        style={{
          background: `${color}1a`,
          borderBottom: `1px solid ${color}33`,
          padding: "5px 10px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 6,
        }}
      >
        <span
          style={{
            fontSize: 10,
            fontWeight: 700,
            color,
            letterSpacing: "0.06em",
          }}
        >
          {data.id}
        </span>
        <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
          {data.humanRequired && (
            <span title={data.humanRequired} style={{ fontSize: 10 }}>
              ⚠️
            </span>
          )}
          <span
            style={{
              fontSize: 9,
              fontWeight: 700,
              color: critColor,
              background: `${critColor}22`,
              borderRadius: 3,
              padding: "1px 5px",
            }}
          >
            {data.criticality}
          </span>
        </div>
      </div>

      {/* Body */}
      <div style={{ padding: "8px 10px", display: "flex", flexDirection: "column", gap: 5 }}>
        {/* Title */}
        <div
          style={{
            fontSize: 12,
            fontWeight: 600,
            color: "#f1f5f9",
            lineHeight: 1.35,
          }}
        >
          {data.title}
        </div>

        {/* Workstream */}
        <div style={{ fontSize: 10, color: "#64748b" }}>{wsName}</div>

        {/* Status row */}
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <span
            style={{
              fontSize: 9,
              fontWeight: 600,
              color,
              background: `${color}22`,
              borderRadius: 3,
              padding: "2px 6px",
            }}
          >
            {STATUS_LABEL[data.status]}
          </span>
          <span style={{ fontSize: 9, color: "#94a3b8" }}>{data.estimate}</span>
          {data.assignee && (
            <span
              style={{
                marginLeft: "auto",
                fontSize: 9,
                color: "#94a3b8",
                maxWidth: 80,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              👤 {data.assignee}
            </span>
          )}
        </div>

        {/* Latest event */}
        {latestEvent && (
          <div style={{ fontSize: 9, color: "#475569" }}>
            {EVENT_LABEL[latestEvent.type] ?? latestEvent.type}{" "}
            {relativeTime(latestEvent.at)}
          </div>
        )}

        {/* Human required callout */}
        {data.humanRequired && (
          <div
            style={{
              fontSize: 9,
              color: "#f59e0b",
              background: "#f59e0b11",
              borderRadius: 3,
              padding: "3px 6px",
              borderLeft: "2px solid #f59e0b",
              lineHeight: 1.4,
            }}
          >
            {data.humanRequired.length > 80
              ? data.humanRequired.slice(0, 77) + "…"
              : data.humanRequired}
          </div>
        )}
      </div>

      <Handle
        type="source"
        position={Position.Right}
        style={{ background: color, width: 8, height: 8, border: "none" }}
      />
    </div>
  );
}
