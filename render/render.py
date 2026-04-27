#!/usr/bin/env python3
"""
Generate a live task flowchart and open it in the browser.

Reads live status from BEADS (bd show --json) + task metadata from TASKS.md.
Writes render/src/generated/tasks.ts, then optionally runs the Vite dev server.

Usage (run from your project root):
    python path/to/render.py          # generate + open dev server
    python path/to/render.py --data   # generate data file only, no server
"""

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
TASKS_MD = _PROJECT_ROOT / "TASKS.md"
PLAN_MD = _PROJECT_ROOT / "PLAN.md"

# Field definitions inlined from planning/task_fields.yaml so render.py has no
# external dependencies beyond the Python standard library.
# Each entry: (key, label, default)
_FIELDS = [
    ("workstream",  "Workstream",            ""),
    ("criticality", "Criticality",           "P1"),
    ("estimate",    "Estimate",              ""),
    ("status",      "Status",               "todo"),
    ("depends",     "Depends on",           ""),
    ("unlocks",     "Unlocks",              ""),
    ("human",       "Human required",       ""),
    ("acceptance",  "Acceptance criteria",  ""),
    ("verification","Verification steps",   ""),
    ("tricky",      "Verification tricky spots", ""),
    ("notes",       "Notes",                ""),
    ("assignee",    "Assignee",             ""),
]

def _enforce_defaults(task: dict) -> dict:
    for key, _, default in _FIELDS:
        if task.get(key) is None:
            task[key] = default
    return task
BEADS_MAP_FILE = _PROJECT_ROOT / ".beads_map.json"
RENDER_DIR = Path(__file__).parent
GENERATED_DIR = RENDER_DIR / "src" / "generated"
DATA_FILE = GENERATED_DIR / "tasks.ts"


# ---------------------------------------------------------------------------
# Parse TASKS.md for static metadata
# ---------------------------------------------------------------------------

def _val(block: str, label: str) -> str:
    """Extract a field value by its label from a task card block."""
    # Use [ \t]* (not \s*) so we never consume a newline into the next field.
    # Matches both "**Label:** value" and "> **Label:** value" (human required blockquote).
    m = re.search(rf"(?:> )?\*\*{re.escape(label)}:\*\*[ \t]*(.+)", block)
    if m:
        return m.group(1).strip().rstrip("  ")
    return "—"


def _parse_ids(s: str) -> list[str]:
    if not s or s == "—":
        return []
    return [x.strip() for x in s.split(",") if re.match(r"T\d+", x.strip())]


def load_tasks_md() -> list[dict]:
    if not TASKS_MD.exists():
        return []

    content = TASKS_MD.read_text()
    tasks = []

    blocks = re.split(r"(?=^### T\d+)", content, flags=re.MULTILINE)
    for block in blocks:
        m = re.match(r"### (T\d+) · (.+)", block.strip())
        if not m:
            continue
        tid, name = m.group(1), m.group(2).strip()

        task: dict = {"id": tid, "title": name}

        for key, label, _ in _FIELDS:
            raw = _val(block, label)
            if key in ("depends", "unlocks"):
                task[key] = _parse_ids(raw)
            else:
                task[key] = raw if raw != "—" else None

        tasks.append(_enforce_defaults(task))

    return tasks


def load_workstream_scopes() -> dict[str, str]:
    """Return {WS_ID: scope_description} parsed from PLAN.md Workstreams table."""
    if not PLAN_MD.exists():
        return {}

    content = PLAN_MD.read_text()
    scopes: dict[str, str] = {}

    # Match table rows: | WS1 | Name | Scope text | Status |
    for m in re.finditer(r"^\|\s*(WS\d+)\s*\|\s*[^|]+\|\s*([^|]+?)\s*\|", content, re.MULTILINE):
        ws_id = m.group(1).strip()
        scope = m.group(2).strip()
        if scope and scope.lower() not in ("scope", "---", ""):
            scopes[ws_id] = scope

    return scopes


# ---------------------------------------------------------------------------
# Query BEADS for live status + timestamps
# ---------------------------------------------------------------------------

def _bd_json(*args: str) -> dict | None:
    result = subprocess.run(
        ["bd", *args, "--json"], capture_output=True, text=True
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        data = json.loads(result.stdout)
        # bd show returns a list — unwrap to single dict
        if isinstance(data, list):
            return data[0] if data else None
        return data
    except json.JSONDecodeError:
        return None


def load_beads_all() -> list[dict]:
    """Load all tasks from BEADS via bd list --json (primary source)."""
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


def load_beads_state(id_map: dict[str, str]) -> dict[str, dict]:
    """Return {T001: beads_data} for all tasks that have a BEADS ID."""
    state: dict[str, dict] = {}
    for tid, bd_id in id_map.items():
        data = _bd_json("show", bd_id)
        if data:
            state[tid] = data
    return state


def merge_beads_with_md(
    beads_tasks: list[dict],
    inverted_map: dict[str, str],
    tasks_md: dict[str, dict],
) -> tuple[list[dict], dict[str, str]]:
    """Merge bd list output with TASKS.md metadata.

    Returns (merged_task_list, effective_id_map) where effective_id_map
    maps T-id -> beads_id for the event-timestamp fetch pass.
    """
    tasks: list[dict] = []
    id_map_out: dict[str, str] = {}
    seen: set[str] = set()

    for bd in beads_tasks:
        bd_id = bd["id"]
        t_id = inverted_map.get(bd_id, bd_id)  # fall back to beads_id if unmapped

        if t_id in seen:
            continue
        seen.add(t_id)

        md = tasks_md.get(t_id, {})

        priority = bd.get("priority", 1)
        criticality = md.get("criticality") or (f"P{priority}" if isinstance(priority, int) else str(priority))

        task: dict = {
            "id": t_id,
            "title": bd.get("title") or md.get("title") or bd_id,
            "workstream": md.get("workstream") or "",
            "criticality": criticality,
            "estimate": md.get("estimate") or "",
            "status": bd.get("status") or "open",
            "depends": md.get("depends") or [],
            "unlocks": md.get("unlocks") or [],
            "human": md.get("human") or "",
            "assignee": bd.get("owner") or md.get("assignee") or None,
        }
        tasks.append(task)
        id_map_out[t_id] = bd_id

    return tasks, id_map_out


def _events_from_beads(data: dict) -> list[dict]:
    events: list[dict] = []
    if data.get("created_at"):
        events.append({"type": "created", "at": data["created_at"]})
    if data.get("started_at"):
        events.append({"type": "started", "at": data["started_at"]})
    status = data.get("status", "open")
    if status == "in_review" and data.get("updated_at"):
        events.append({"type": "in_review", "at": data["updated_at"]})
    if data.get("closed_at"):
        events.append({"type": "closed", "at": data["closed_at"]})
    if status == "blocked" and data.get("updated_at"):
        events.append({"type": "blocked", "at": data["updated_at"]})
    return events


# ---------------------------------------------------------------------------
# Merge and write tasks.ts
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
    items = [
        f'{{ type: "{e["type"]}", at: "{e["at"]}" }}'
        for e in events
    ]
    return "[\n    " + ",\n    ".join(items) + "\n  ]"


def write_data_ts(tasks: list[dict], beads_state: dict[str, dict], ws_scopes: dict[str, str] | None = None) -> None:
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

    # Emit workstream scope map
    if ws_scopes:
        scope_entries = ", ".join(
            f'"{k}": {_ts_string(v)}' for k, v in ws_scopes.items()
        )
        lines.append(f'export const workstreamScopes: Record<string, string> = {{ {scope_entries} }}')
    else:
        lines.append('export const workstreamScopes: Record<string, string> = {}')
    lines.append("")

    lines.append("export const tasks: Task[] = [")

    for t in tasks:
        bd = beads_state.get(t["id"], {})
        # BEADS status takes precedence; fall back to TASKS.md status
        status = bd.get("status", t.get("status") or "open") if bd else (t.get("status") or "open")
        assignee = bd.get("assignee") or t.get("assignee") or None
        events = _events_from_beads(bd) if bd else []

        # Normalise list fields
        depends = t.get("depends") or []
        unlocks = t.get("unlocks") or []
        if isinstance(depends, str):
            depends = [x.strip() for x in depends.split(",") if x.strip()]
        if isinstance(unlocks, str):
            unlocks = [x.strip() for x in unlocks.split(",") if x.strip()]

        lines.append("  {")
        lines.append(f'    id: "{t["id"]}",')
        lines.append(f'    beadsId: "{bd.get("id", "")}",')
        lines.append(f'    title: {_ts_string(t.get("title") or t.get("name"))},')
        lines.append(f'    workstream: {_ts_string(t.get("workstream"))},')
        lines.append(f'    criticality: "{t.get("criticality", "P1")}",')
        lines.append(f'    estimate: "{t.get("estimate", "—")}",')
        lines.append(f'    status: "{status}",')
        lines.append(f'    depends: {_ts_str_list(depends)},')
        lines.append(f'    unlocks: {_ts_str_list(unlocks)},')
        lines.append(f'    humanRequired: {_ts_string(t.get("human"))},')
        lines.append(f'    assignee: {_ts_string(assignee)},')
        lines.append(f'    events: {_ts_events(events)},')
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

    beads_state: dict[str, dict] = {}

    if BEADS_MAP_FILE.exists():
        id_map_file: dict[str, str] = json.loads(BEADS_MAP_FILE.read_text())
        inverted = {v: k for k, v in id_map_file.items()}

        print("  Loading all tasks from BEADS (bd list)...")
        beads_all = load_beads_all()

        if beads_all:
            tasks_md = {t["id"]: t for t in load_tasks_md()}
            tasks, effective_id_map = merge_beads_with_md(beads_all, inverted, tasks_md)
            print(f"  {len(tasks)} task(s) from BEADS")
            print(f"  Fetching detailed event timestamps (bd show)...")
            beads_state = load_beads_state(effective_id_map)
            live = sum(1 for v in beads_state.values() if v)
            print(f"  {live}/{len(tasks)} BEADS task(s) fetched\n")
        else:
            print("  bd list returned no tasks — falling back to TASKS.md\n")
            tasks = load_tasks_md()
            if not tasks:
                print(f"  ERROR: No tasks found in {TASKS_MD}. Run plan.py first.\n")
                sys.exit(1)
    else:
        print("  No .beads_map.json — loading tasks from TASKS.md\n")
        tasks = load_tasks_md()
        if not tasks:
            print(f"  ERROR: No tasks found in {TASKS_MD}. Run plan.py first.\n")
            sys.exit(1)
        print(f"  {len(tasks)} task(s) loaded from TASKS.md\n")

    write_data_ts(tasks, beads_state, ws_scopes)

    if data_only:
        print("\n  Done (data only). Open the render app manually.\n")
        return

    if not ensure_deps():
        print("  ERROR: npm install failed. Check your Node.js installation.\n")
        sys.exit(1)

    run_dev_server()


if __name__ == "__main__":
    main()
