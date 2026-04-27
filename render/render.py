#!/usr/bin/env python3
"""
Generate a live task flowchart and open it in the browser.

Reads ALL data from BEADS (bd list + bd show --json). No other files are read.
Task metadata (workstream, workstream_scope, workstream_owner, depends, estimate,
human_required) must be set on BEADS issues before running render.

Usage (run from your project root):
    python path/to/render.py          # generate + open dev server
    python path/to/render.py --data   # generate data file only, no server
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

RENDER_DIR = Path(__file__).parent
GENERATED_DIR = RENDER_DIR / "src" / "generated"
DATA_FILE = GENERATED_DIR / "tasks.ts"
PUBLIC_DIR = RENDER_DIR / "public"
JSON_FILE = PUBLIC_DIR / "tasks.json"


# ---------------------------------------------------------------------------
# BEADS
# ---------------------------------------------------------------------------

def _bd_show(bd_id: str) -> dict | None:
    result = subprocess.run(
        ["bd", "show", bd_id, "--json"], capture_output=True, text=True
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        data = json.loads(result.stdout)
        return data[0] if isinstance(data, list) else data
    except json.JSONDecodeError:
        return None


def load_beads_all() -> list[dict]:
    """Load all tasks from BEADS (all statuses) via bd list --json."""
    result = subprocess.run(
        ["bd", "list", "--status", "open,in_progress,blocked,closed", "--json"],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []
    try:
        data = json.loads(result.stdout)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def load_beads_detail(beads_list: list[dict]) -> list[dict]:
    """Fetch full detail (metadata, timestamps) for each task via bd show."""
    detailed: list[dict] = []
    for t in beads_list:
        detail = _bd_show(t["id"])
        detailed.append(detail if detail else t)
    return detailed


def _events_from_beads(data: dict) -> list[dict]:
    events: list[dict] = []
    if data.get("created_at"):
        events.append({"type": "created", "at": data["created_at"]})
    if data.get("started_at"):
        events.append({"type": "started", "at": data["started_at"]})
    if data.get("closed_at"):
        events.append({"type": "closed", "at": data["closed_at"]})
    status = data.get("status", "open")
    if status == "blocked" and data.get("updated_at"):
        events.append({"type": "blocked", "at": data["updated_at"]})
    return events


def build_tasks(beads_detail: list[dict]) -> list[dict]:
    """Build merged task list from BEADS detail records (metadata-first)."""
    # First pass: build beads_id -> task_id map from metadata
    bd_to_tid: dict[str, str] = {}
    for bd in beads_detail:
        meta = bd.get("metadata") or {}
        t_id = meta.get("task_id") or bd["id"]
        bd_to_tid[bd["id"]] = t_id

    # Second pass: build task dicts
    tasks: list[dict] = []
    for bd in beads_detail:
        meta = bd.get("metadata") or {}
        bd_id = bd["id"]
        t_id = bd_to_tid[bd_id]

        # Resolve depends: stored as comma-separated beads IDs -> task_ids
        raw_depends = meta.get("depends", "")
        depends: list[str] = []
        if raw_depends:
            for dep_bd_id in raw_depends.split(","):
                dep_bd_id = dep_bd_id.strip()
                if dep_bd_id in bd_to_tid:
                    depends.append(bd_to_tid[dep_bd_id])

        priority = bd.get("priority", 1)
        criticality = f"P{priority}" if isinstance(priority, int) else str(priority)

        tasks.append({
            "id": t_id,
            "beads_id": bd_id,
            "title": bd.get("title") or t_id,
            "workstream": meta.get("workstream") or "",
            "workstream_scope": meta.get("workstream_scope") or "",
            "workstream_owner": meta.get("workstream_owner") or "",
            "criticality": criticality,
            "estimate": meta.get("estimate") or "",
            "status": bd.get("status") or "open",
            "depends": depends,
            "unlocks": [],  # filled in below
            "human": meta.get("human_required") or "",
            "assignee": bd.get("assignee") or None,
            "events": _events_from_beads(bd),
        })

    # Third pass: compute unlocks (inverse of depends)
    unlocks: dict[str, list[str]] = {t["id"]: [] for t in tasks}
    for t in tasks:
        for dep_tid in t["depends"]:
            if dep_tid in unlocks:
                unlocks[dep_tid].append(t["id"])
    for t in tasks:
        t["unlocks"] = unlocks[t["id"]]

    return tasks


# ---------------------------------------------------------------------------
# Derive workstream maps from task metadata
# ---------------------------------------------------------------------------

def extract_workstream_meta(tasks: list[dict]) -> tuple[dict[str, str], dict[str, str]]:
    """Return ({WS_ID: scope}, {WS_ID: owner}) derived from task metadata."""
    scopes: dict[str, str] = {}
    owners: dict[str, str] = {}
    for t in tasks:
        ws_raw = t.get("workstream") or ""
        ws_id = ws_raw.split("—")[0].strip()
        if not ws_id:
            continue
        scope = t.get("workstream_scope") or ""
        owner = t.get("workstream_owner") or ""
        if scope and ws_id not in scopes:
            scopes[ws_id] = scope
        if owner and ws_id not in owners:
            owners[ws_id] = owner
    return scopes, owners


# ---------------------------------------------------------------------------
# Write tasks.ts
# ---------------------------------------------------------------------------

def _ts_string(v: str | None) -> str:
    if v is None:
        return "null"
    escaped = v.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
    return f"`{escaped}`"


def _ts_str_list(lst: list[str]) -> str:
    return "[" + ", ".join(f'"{x}"' for x in lst) + "]"


def _ts_events(events: list[dict]) -> str:
    if not events:
        return "[]"
    items = [f'{{ type: "{e["type"]}", at: "{e["at"]}" }}' for e in events]
    return "[\n    " + ",\n    ".join(items) + "\n  ]"


def write_data_ts(
    tasks: list[dict],
    ws_scopes: dict[str, str] | None = None,
    ws_owners: dict[str, str] | None = None,
) -> None:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    lines = [
        "// Generated by render.py — do not edit manually",
        f'// Updated: {now}',
        "",
        'import type { Task } from "../types"',
        "",
        f'export const generatedAt = "{now}"',
        "",
    ]

    if ws_scopes:
        scope_entries = ", ".join(f'"{k}": {_ts_string(v)}' for k, v in ws_scopes.items())
        lines.append(f'export const workstreamScopes: Record<string, string> = {{ {scope_entries} }}')
    else:
        lines.append('export const workstreamScopes: Record<string, string> = {}')

    if ws_owners:
        owner_entries = ", ".join(f'"{k}": {_ts_string(v)}' for k, v in ws_owners.items())
        lines.append(f'export const workstreamOwners: Record<string, string> = {{ {owner_entries} }}')
    else:
        lines.append('export const workstreamOwners: Record<string, string> = {}')
    lines.append("")

    lines.append("export const tasks: Task[] = [")

    for t in tasks:
        lines.append("  {")
        lines.append(f'    id: "{t["id"]}",')
        lines.append(f'    beadsId: "{t["beads_id"]}",')
        lines.append(f'    title: {_ts_string(t.get("title"))},')
        lines.append(f'    workstream: {_ts_string(t.get("workstream"))},')
        lines.append(f'    criticality: "{t.get("criticality", "P1")}",')
        lines.append(f'    estimate: "{t.get("estimate", "")}",')
        lines.append(f'    status: "{t.get("status", "open")}",')
        lines.append(f'    depends: {_ts_str_list(t.get("depends") or [])},')
        lines.append(f'    unlocks: {_ts_str_list(t.get("unlocks") or [])},')
        lines.append(f'    humanRequired: {_ts_string(t.get("human"))},')
        lines.append(f'    assignee: {_ts_string(t.get("assignee"))},')
        lines.append(f'    events: {_ts_events(t.get("events") or [])},')
        lines.append("  },")

    lines += ["]", ""]
    DATA_FILE.write_text("\n".join(lines))
    print(f"  Written to {DATA_FILE}")


def write_data_json(
    tasks: list[dict],
    ws_scopes: dict[str, str] | None = None,
    ws_owners: dict[str, str] | None = None,
) -> None:
    """Write tasks.json to public/ for runtime fetch by the served app."""
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    payload = {
        "generatedAt": now,
        "workstreamScopes": ws_scopes or {},
        "workstreamOwners": ws_owners or {},
        "tasks": [
            {
                "id": t["id"],
                "beadsId": t["beads_id"],
                "title": t.get("title"),
                "workstream": t.get("workstream") or "",
                "criticality": t.get("criticality", "P1"),
                "estimate": t.get("estimate", ""),
                "status": t.get("status", "open"),
                "depends": t.get("depends") or [],
                "unlocks": t.get("unlocks") or [],
                "humanRequired": t.get("human"),
                "assignee": t.get("assignee"),
                "events": t.get("events") or [],
            }
            for t in tasks
        ],
    }
    JSON_FILE.write_text(json.dumps(payload, indent=2))
    print(f"  Written to {JSON_FILE}")


# ---------------------------------------------------------------------------
# Dev server
# ---------------------------------------------------------------------------

def ensure_deps() -> bool:
    node_modules = RENDER_DIR / "node_modules"
    if not node_modules.exists():
        print("  Installing render dependencies (npm install)...")
        result = subprocess.run(["npm", "install"], cwd=RENDER_DIR)
        return result.returncode == 0
    return True


def run_dev_server() -> None:
    print(f"\n  Starting Vite dev server at http://localhost:5173\n")
    subprocess.run(["npm", "run", "dev"], cwd=RENDER_DIR)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    data_only = "--data" in sys.argv

    print("\n  Render — loading task data...\n")

    print("  Loading tasks from BEADS (bd list)...")
    beads_list = load_beads_all()

    if not beads_list:
        print("  ERROR: bd list returned no tasks. Is BEADS set up for this project?\n")
        sys.exit(1)

    print(f"  {len(beads_list)} task(s) found — fetching detail (bd show)...")
    beads_detail = load_beads_detail(beads_list)

    tasks = build_tasks(beads_detail)
    ws_scopes, ws_owners = extract_workstream_meta(tasks)
    print(f"  {len(tasks)} task(s) built\n")

    write_data_ts(tasks, ws_scopes, ws_owners)
    write_data_json(tasks, ws_scopes, ws_owners)

    if data_only:
        print("\n  Done (data only). Open the render app manually.\n")
        return

    if not ensure_deps():
        print("  ERROR: npm install failed. Check your Node.js installation.\n")
        sys.exit(1)

    run_dev_server()


if __name__ == "__main__":
    main()
