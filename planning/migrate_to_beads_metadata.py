#!/usr/bin/env python3
"""
One-time migration: copy TASKS.md metadata into BEADS issue metadata.

Sets task_id, workstream, depends (beads IDs), and human_required on every
task that has a .beads_map.json entry.

Run from the project root:
    python3 planning/migrate_to_beads_metadata.py
"""

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
TASKS_MD = PROJECT_ROOT / "TASKS.md"
BEADS_MAP_FILE = PROJECT_ROOT / ".beads_map.json"


def run(cmd: list[str]) -> tuple[int, str, str]:
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


# ---------------------------------------------------------------------------
# Parse TASKS.md (copied from render.py — no shared dep)
# ---------------------------------------------------------------------------

import re

_FIELDS = [
    ("workstream",  "Workstream"),
    ("criticality", "Criticality"),
    ("estimate",    "Estimate"),
    ("status",      "Status"),
    ("depends",     "Depends on"),
    ("unlocks",     "Unlocks"),
    ("human",       "Human required"),
]


def _val(block: str, label: str) -> str:
    m = re.search(rf"(?:> )?\*\*{re.escape(label)}:\*\*[ \t]*(.+)", block)
    if m:
        return m.group(1).strip().rstrip("  ")
    return ""


def _parse_ids(s: str) -> list[str]:
    if not s or s == "—":
        return []
    return [x.strip() for x in s.split(",") if re.match(r"T\d+", x.strip())]


def load_tasks_md() -> dict[str, dict]:
    """Return {T001: task_dict} parsed from TASKS.md."""
    if not TASKS_MD.exists():
        return {}
    content = TASKS_MD.read_text()
    tasks: dict[str, dict] = {}
    blocks = re.split(r"(?=^### T\d+)", content, flags=re.MULTILINE)
    for block in blocks:
        m = re.match(r"### (T\d+) · (.+)", block.strip())
        if not m:
            continue
        tid, name = m.group(1), m.group(2).strip()
        task: dict = {"id": tid, "title": name}
        for key, label in _FIELDS:
            raw = _val(block, label)
            if key in ("depends", "unlocks"):
                task[key] = _parse_ids(raw)
            else:
                task[key] = raw if raw and raw != "—" else ""
        tasks[tid] = task
    return tasks


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not BEADS_MAP_FILE.exists():
        print("ERROR: .beads_map.json not found. Run plan.py + beads setup first.")
        sys.exit(1)

    id_map: dict[str, str] = json.loads(BEADS_MAP_FILE.read_text())
    inverted = {v: k for k, v in id_map.items()}  # beads_id -> T-id

    tasks_md = load_tasks_md()
    if not tasks_md:
        print("ERROR: No tasks found in TASKS.md.")
        sys.exit(1)

    print(f"\n  Migrating {len(id_map)} tasks to BEADS metadata...\n")

    ok = 0
    for t_id, bd_id in sorted(id_map.items()):
        task = tasks_md.get(t_id, {})

        # Resolve depends T-ids -> beads IDs
        dep_beads_ids = [id_map[d] for d in task.get("depends", []) if d in id_map]
        depends_str = ",".join(dep_beads_ids)

        workstream_raw = task.get("workstream", "")
        # Store just the WS-id (e.g. "WS1") — name comes from PLAN.md
        ws_id = workstream_raw.split("—")[0].strip() if workstream_raw else ""

        human = task.get("human", "").strip()

        estimate = task.get("estimate", "").strip()

        args = [
            "bd", "update", bd_id,
            "--set-metadata", f"task_id={t_id}",
            "--set-metadata", f"workstream={workstream_raw}",
        ]
        if depends_str:
            args += ["--set-metadata", f"depends={depends_str}"]
        if human:
            args += ["--set-metadata", f"human_required={human}"]
        if estimate:
            args += ["--set-metadata", f"estimate={estimate}"]

        rc, out, err = run(args)
        if rc == 0:
            print(f"  ✓ {t_id} ({bd_id})")
            ok += 1
        else:
            print(f"  ✗ {t_id} ({bd_id}): {err.strip()}")

    print(f"\n  Done: {ok}/{len(id_map)} tasks updated.\n")


if __name__ == "__main__":
    main()
