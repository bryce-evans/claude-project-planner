"""Phase 7: push tasks and metadata to BEADS."""

import json
import subprocess
from pathlib import Path

from git_plan import commit_planning_docs
from ui import hr


BEADS_MAP_FILE = Path(".beads_map.json")


def _estimate_minutes(est: str) -> int | None:
    est = est.lower().strip()
    try:
        if "w" in est:
            return int(float(est.replace("w", "")) * 5 * 8 * 60)
        if "d" in est:
            return int(float(est.replace("d", "")) * 8 * 60)
        if "h" in est:
            return int(float(est.replace("h", "")) * 60)
    except ValueError:
        pass
    return None


def _priority_int(crit: str) -> int:
    return {"P0": 0, "P1": 1, "P2": 2}.get(crit, 2)


def _bd(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["bd", *args], capture_output=True, text=True, check=check)


def push_to_beads(tasks: list[dict], ws_list: list[dict] | None = None) -> None:
    probe = _bd("--version")
    if probe.returncode != 0:
        print("  bd not found — install BEADS: https://github.com/gastownhall/beads")
        print("  Skipping BEADS integration.\n")
        return

    if not Path(".beads").exists():
        print("  Initializing BEADS...\n")
        _bd("init", check=True)

    ws_owners: dict[str, str] = {}
    ws_scopes: dict[str, str] = {}
    if ws_list:
        for w in ws_list:
            ws_owners[w["id"]] = w.get("owner") or ""
            ws_scopes[w["id"]] = w.get("scope") or ""

    print(f"\n  Creating {len(tasks)} task(s) in BEADS...\n")

    id_map: dict[str, str] = {}  # T001 → bd-xxxx

    # Phase A: create all tasks
    for t in tasks:
        tid = t.get("ID", "")
        name = t.get("name", "")
        ws_raw = t.get("workstream", "")
        ws_id = ws_raw.split("—")[0].strip()
        human = t.get("human", "—")
        notes = t.get("notes", "—")
        estimate_str = t.get("estimate", "")
        ws_owner = ws_owners.get(ws_id, "")
        ws_scope = ws_scopes.get(ws_id, "")

        desc_parts = [f"Workstream: {ws_raw}"]
        if human != "—":
            desc_parts.append(f"\nHuman required: {human}")
        if notes != "—":
            desc_parts.append(f"\nNotes: {notes}")

        meta: dict[str, str] = {"task_id": tid, "workstream": ws_raw}
        if estimate_str and estimate_str != "—":
            meta["estimate"] = estimate_str
        if human and human != "—":
            meta["human_required"] = human
        if ws_owner:
            meta["workstream_owner"] = ws_owner
        if ws_scope:
            meta["workstream_scope"] = ws_scope

        cmd = [
            "create", f"{tid} — {name}",
            "-p", str(_priority_int(t.get("criticality", "P1"))),
            "-t", "task",
            "-d", "\n".join(desc_parts),
            "--metadata", json.dumps(meta),
            "--json",
        ]
        mins = _estimate_minutes(estimate_str)
        if mins:
            cmd += ["--estimate", str(mins)]
        if ws_owner:
            cmd += ["--assignee", ws_owner]

        result = _bd(*cmd)
        if result.returncode == 0:
            try:
                bd_id = json.loads(result.stdout).get("id", "")
                id_map[tid] = bd_id
                owner_hint = f"  [{ws_owner}]" if ws_owner else ""
                print(f"  {tid} → {bd_id}  {name}{owner_hint}")
            except (json.JSONDecodeError, AttributeError):
                print(f"  {tid}  WARNING: could not parse bd output")
        else:
            print(f"  {tid}  ERROR: {result.stderr.strip()}")

    # Phase B: link dependencies
    print("\n  Linking dependencies...\n")
    dep_map: dict[str, list[str]] = {}
    for t in tasks:
        tid = t.get("ID", "")
        child_bd = id_map.get(tid)
        if not child_bd:
            continue
        depends_str = t.get("depends", "—")
        if not depends_str or depends_str == "—":
            continue
        dep_bd_ids = []
        for dep_tid in [d.strip() for d in depends_str.split(",") if d.strip()]:
            parent_bd = id_map.get(dep_tid)
            if not parent_bd:
                continue
            r = _bd("dep", "add", child_bd, parent_bd, "--type", "blocks")
            status = "ok" if r.returncode == 0 else f"ERROR: {r.stderr.strip()}"
            print(f"  {dep_tid} blocks {tid}  [{status}]")
            dep_bd_ids.append(parent_bd)
        dep_map[tid] = dep_bd_ids

    # Phase C: write depends metadata (beads IDs, now that all exist)
    print("\n  Writing dependency metadata...\n")
    for tid, dep_bd_ids in dep_map.items():
        if not dep_bd_ids:
            continue
        bd_id = id_map.get(tid)
        if not bd_id:
            continue
        depends_str = ",".join(dep_bd_ids)
        r = _bd("update", bd_id, "--set-metadata", f"depends={depends_str}")
        if r.returncode != 0:
            print(f"  WARNING: could not set depends metadata on {tid}: {r.stderr.strip()}")

    BEADS_MAP_FILE.write_text(json.dumps(id_map, indent=2))
    print(f"\n  ID mapping saved to {BEADS_MAP_FILE}")

    issues_jsonl = Path("issues.jsonl")
    to_commit = [f for f in [BEADS_MAP_FILE, issues_jsonl] if f.exists()]
    if to_commit:
        commit_planning_docs(to_commit, "planning: update BEADS task export")
        print(f"  Committed: {', '.join(f.name for f in to_commit)}\n")


def push_to_beads_phase(tasks: list[dict], ws_list: list[dict] | None = None) -> None:
    print("\n" + hr("="))
    print("  Step 7: Push to BEADS")
    print(hr("="))
    print("\n  Push tasks to BEADS for agent-ready task management?")
    print("  Requires `bd` CLI — https://github.com/gastownhall/beads")
    ans = input("\n  [Y/n]: ").strip().lower()
    if ans == "n":
        print("  Skipped. Run `bd init && python planning/render.py` later to set up.\n")
        return
    push_to_beads(tasks, ws_list)
