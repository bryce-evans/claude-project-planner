#!/usr/bin/env python3
"""
Generate a live task flowchart and open it in the browser.

Reads all task data from BEADS (bd list + bd show --json).
Workstream scope taglines are still read from PLAN.md if present.
Writes render/src/generated/tasks.ts, then optionally runs the Vite dev server.

Usage (run from your project root):
    python path/to/render.py          # generate + open dev server
    python path/to/render.py --data   # generate data file only, no server
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
PLAN_MD = _PROJECT_ROOT / "PLAN.md"
RENDER_DIR = Path(__file__).parent
GENERATED_DIR = RENDER_DIR / "src" / "generated"
DATA_FILE = GENERATED_DIR / "tasks.ts"


# ---------------------------------------------------------------------------
# PLAN.md workstream scopes (optional supplement)
# ---------------------------------------------------------------------------

def load_workstream_scopes() -> dict[str, str]:
    """Return {WS_ID: scope_description} parsed from PLAN.md Workstreams table."""
    import re
    if not PLAN_MD.exists():
        return {}
    content = PLAN_MD.read_text()
    scopes: dict[str, str] = {}
    for m in re.finditer(r"^\|\s*(WS\d+)\s*\|\s*[^|]+\|\s*([^|]+?)\s*\|", content, re.MULTILINE):
        ws_id = m.group(1).strip()
        scope = m.group(2).strip()
        if scope and scope.lower() not in ("scope", "---", ""):
            scopes[ws_id] = scope
    return scopes


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
            "criticality": criticality,
            "estimate": meta.get("estimate") or "",
            "status": bd.get("status") or "open",
            "depends": depends,
            "unlocks": [],  # filled in below
            "human": meta.get("human_required") or "",
            "assignee": bd.get("owner") or None,
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


def write_data_ts(tasks: list[dict], ws_scopes: dict[str, str] | None = None) -> None:
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

    ws_scopes = load_workstream_scopes()
    if ws_scopes:
        print(f"  {len(ws_scopes)} workstream scope(s) loaded from PLAN.md")

    print("  Loading tasks from BEADS (bd list)...")
    beads_list = load_beads_all()

    if not beads_list:
        print("  ERROR: bd list returned no tasks. Is BEADS set up for this project?\n")
        sys.exit(1)

    print(f"  {len(beads_list)} task(s) found — fetching detail (bd show)...")
    beads_detail = load_beads_detail(beads_list)

    tasks = build_tasks(beads_detail)
    print(f"  {len(tasks)} task(s) built\n")

    write_data_ts(tasks, ws_scopes)

    if data_only:
        print("\n  Done (data only). Open the render app manually.\n")
        return

    if not ensure_deps():
        print("  ERROR: npm install failed. Check your Node.js installation.\n")
        sys.exit(1)

    run_dev_server()


if __name__ == "__main__":
    main()
