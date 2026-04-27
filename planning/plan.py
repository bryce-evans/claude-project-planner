#!/usr/bin/env python3
"""
Interactive project planner.

Usage (run from your project root):
    python path/to/planning/plan.py

Flow:
    1. Walk user through PROJECT.md sections
    2. Identify components and recommend a tech stack
    3. User confirms / overrides each recommendation
    4. Write ARCHITECTURE.md with agreed stack
    5. Re-iterate: surface gaps, alternatives, and clarifying questions
    6. Define workstreams (count, names, scopes)
    7. Break tasks across workstreams and write PLAN.md
    8. Generate full task manifest with dependency graph → TASKS.md
    9. Push tasks to BEADS (optional) → .beads_map.json
"""

import json
import subprocess
import sys
from pathlib import Path

from git_plan import ensure_gitignore
from project_context import (
    SECTIONS, ARCHITECTURE_MD,
    load_project_md, select_project_type, existing_repo_context, collect_project_info,
)
from stack import stream_recommendations, confirm_tech_stack, write_architecture, review_interfaces
from review import reiterate
from workstreams import plan_workstreams
from task_manifest import generate_task_manifest
from beads_push import push_to_beads_phase
from ui import hr


# ---------------------------------------------------------------------------
# Checkpoint state (session resume across interruptions)
# ---------------------------------------------------------------------------

_STATE_FILE = Path(".planner_state.json")


def _load_state() -> dict:
    if _STATE_FILE.exists():
        try:
            return json.loads(_STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_state(state: dict) -> None:
    _STATE_FILE.write_text(json.dumps(state, indent=2))


def _print_resume_history(state: dict) -> None:
    """Print everything completed so far as if it had just run live."""
    print("\n" + hr("="))
    print("  Claude Project Planner — Resuming from saved progress")
    print(hr("="))

    existing = load_project_md()
    if existing:
        print("\n" + hr("="))
        print("  Step 1: Project Definition  (loaded)")
        print(hr("="))
        for key, title, _ in SECTIONS:
            value = existing.get(key, "")
            if not value:
                continue
            print(f"\n  {hr('·')}")
            print(f"  {title}")
            print(f"  {hr('·')}")
            for line in value.splitlines():
                print(f"    {line}")

    confirmed = state.get("confirmed_components")
    if confirmed:
        print("\n" + hr("="))
        print("  Step 2: Tech Stack  (loaded)")
        print(hr("="))
        print()
        for c in confirmed:
            alt_hint = f"  (alt: {c['alt']})" if c.get("alt") else ""
            print(f"  {c['name']}: {c['tech']}{alt_hint}")
            print(f"    {c['rationale']}")

    if state.get("architecture_done"):
        print("\n" + hr("="))
        print("  Step 3: ARCHITECTURE.md  (generated)")
        print(hr("="))
        arch = ""
        if ARCHITECTURE_MD.exists():
            arch = ARCHITECTURE_MD.read_text()
        else:
            r = subprocess.run(["git", "show", "plan:ARCHITECTURE.md"],
                               capture_output=True, text=True)
            if r.returncode == 0:
                arch = r.stdout
        if arch:
            lines = arch.splitlines()
            for line in lines[:40]:
                print(f"  {line}")
            if len(lines) > 40:
                print(f"  ... ({len(lines) - 40} more lines in ARCHITECTURE.md)")

    if state.get("interface_review_done"):
        print("\n" + hr("="))
        print("  Step 3b: Interface Review  (accepted)")
        print(hr("="))

    if state.get("reiterate_done"):
        print("\n" + hr("="))
        print("  Step 4: Re-iterate / Validation  (complete)")
        print(hr("="))

    ws_list: list[dict] = state.get("ws_list", [])
    if ws_list:
        print("\n" + hr("="))
        print("  Step 5: Workstreams  (loaded)")
        print(hr("="))
        print()
        for w in ws_list:
            print(f"  {w['id']} — {w['name']}")
            print(f"    {w['scope']}")
            for t in w.get("tasks", []):
                print(f"      [{t.get('priority', '?')}] {t['name']} ({t.get('estimate', '?')})")

    if state.get("tasks_done"):
        print("\n" + hr("="))
        print("  Step 6: Task Manifest  (complete — see TASKS.md)")
        print(hr("="))

    print()
    print(hr("·"))
    print("  History shown above. Continuing from next incomplete step...")
    print(hr("·"))
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        ensure_gitignore()

        state = _load_state()

        if not state:
            print("\n" + hr("="))
            print("  Claude Project Planner")
            print(hr("="))
            print()
            print("  This full planning session takes 40–60 minutes.")
            print("  Progress is saved after each step — you can Ctrl-C and resume any time.")
            print()
            input("  Press Enter to begin.")
        else:
            _print_resume_history(state)

        project_type = select_project_type()
        if "repo_context" in state:
            repo_context: str | None = state["repo_context"]
        else:
            repo_context = existing_repo_context()
            state["repo_context"] = repo_context
            _save_state(state)

        if project_type:
            repo_context = f"Project type decision:\n{project_type}\n\n{repo_context or ''}".strip() or None

        sections = collect_project_info()

        if "confirmed_components" in state:
            confirmed: list[dict] | None = state["confirmed_components"]
        else:
            raw_recs = stream_recommendations(sections, repo_context)
            confirmed = confirm_tech_stack(raw_recs)
            state["confirmed_components"] = confirmed
            _save_state(state)

        if not confirmed:
            print("  Skipping ARCHITECTURE.md generation.\n")
        else:
            if not state.get("architecture_done"):
                write_architecture(sections, confirmed, repo_context)
                state["architecture_done"] = True
                _save_state(state)

            if not state.get("interface_review_done"):
                review_interfaces()
                state["interface_review_done"] = True
                _save_state(state)

            if not state.get("reiterate_done"):
                reiterate(sections, confirmed)
                state["reiterate_done"] = True
                _save_state(state)

            if state.get("workstreams_done"):
                ws_list: list[dict] = state.get("ws_list", [])
            else:
                ws_list = plan_workstreams(sections, confirmed, repo_context)
                state["workstreams_done"] = True
                state["ws_list"] = ws_list
                _save_state(state)

            if ws_list and not state.get("tasks_done"):
                tasks = generate_task_manifest(sections, confirmed, ws_list, repo_context)
                if tasks:
                    state["tasks_done"] = True
                    _save_state(state)
                    push_to_beads_phase(tasks, ws_list)

        if _STATE_FILE.exists():
            _STATE_FILE.unlink()

        print(hr("="))
        print("  Done! Next steps:")
        print("  1. Review PROJECT.md, ARCHITECTURE.md, PLAN.md, and TASKS.md")
        print("  2. Run start.py to claim a workstream")
        print("  3. Pick your first P0 task from TASKS.md — update status in BEADS as you go")
        print("  4. Run render.py to open the live flowchart in the browser")
        print(hr("=") + "\n")

    except KeyboardInterrupt:
        print("\n\n  Interrupted. Progress saved — re-run plan.py to resume.\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
