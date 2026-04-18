#!/usr/bin/env python3
"""
Orchestrate the full claude-project-planner workflow.

Usage (from anywhere):
    python path/to/planning/run.py [target_dir]     # defaults to cwd
    python path/to/planning/run.py -f <stage>       # force-restart from stage
    python path/to/planning/run.py ~/my-project -f plan

Stages (in order):
    setup   — copy boilerplate files into the target project
    start   — identify yourself, claim a workstream (writes ME.md, WORKSTREAM.md)
    plan    — define the project and generate task manifest (writes PROJECT.md,
              ARCHITECTURE.md, PLAN.md, TASKS.md)
"""

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

PLANNER_DIR = Path(__file__).parent.resolve()

# ---------------------------------------------------------------------------
# Stage definitions
# ---------------------------------------------------------------------------

@dataclass
class Stage:
    id: str
    label: str
    script: Path
    check: Callable[[Path], bool]   # returns True if stage appears complete
    # How to invoke: "target_arg" passes target as positional arg,
    #                "cwd" runs the script with cwd=target
    invoke: str = "cwd"


def _check_setup(target: Path) -> bool:
    required = ["CLAUDE.md", "PLAN.md", "TASKS.md", "ARCHITECTURE.md", "PROJECT.md"]
    files_present = all((target / f).exists() for f in required)
    commands_present = (target / ".claude" / "commands").is_dir()
    return files_present and commands_present


def _check_start(target: Path) -> bool:
    me = target / "ME.md"
    ws = target / "WORKSTREAM.md"
    if not me.exists() or not ws.exists():
        return False
    if "_TODO_" in me.read_text():
        return False
    ws_text = ws.read_text()
    # WORKSTREAM.md written by start.py always has **Workstream:** line
    import re
    m = re.search(r"\*\*Workstream:\*\*\s*(.+)", ws_text)
    if not m:
        return False
    value = m.group(1).strip()
    return bool(value) and value != "—"


def _check_plan(target: Path) -> bool:
    tasks = target / "TASKS.md"
    plan = target / "PLAN.md"
    if not tasks.exists() or not plan.exists():
        return False
    # TASKS.md has actual task rows (lines starting with | T0)
    has_tasks = any(
        line.strip().startswith("| T0") or line.strip().startswith("| T1")
        for line in tasks.read_text().splitlines()
    )
    # PLAN.md has a workstream table row (| WS)
    has_workstreams = any(
        line.strip().startswith("| WS")
        for line in plan.read_text().splitlines()
    )
    return has_tasks and has_workstreams


STAGES: list[Stage] = [
    Stage(
        id="setup",
        label="Setup       — copy boilerplate into project",
        script=PLANNER_DIR / "setup.py",
        check=_check_setup,
        invoke="target_arg",   # setup.py takes target as positional arg
    ),
    Stage(
        id="start",
        label="Start       — identify yourself, claim a workstream",
        script=PLANNER_DIR / "start.py",
        check=_check_start,
        invoke="cwd",
    ),
    Stage(
        id="plan",
        label="Plan        — define project, generate task manifest",
        script=PLANNER_DIR / "plan.py",
        check=_check_plan,
        invoke="cwd",
    ),
]

STAGE_IDS = [s.id for s in STAGES]


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def _status_line(stage: Stage, target: Path, forced_from: str | None, current_id: str | None) -> str:
    done = stage.check(target)
    if done:
        marker = "✓"
    elif stage.id == current_id:
        marker = "▶"
    else:
        marker = "○"

    forced_note = " (forced)" if stage.id == forced_from else ""
    return f"  {marker}  {stage.label}{forced_note}"


def _print_stages(target: Path, forced_from: str | None, current_id: str | None) -> None:
    print(f"\n  Project: {target}")
    print()
    for stage in STAGES:
        print(_status_line(stage, target, forced_from, current_id))
    print()


# ---------------------------------------------------------------------------
# Run a single stage
# ---------------------------------------------------------------------------

def _run_stage(stage: Stage, target: Path) -> int:
    cmd = [sys.executable, str(stage.script)]
    if stage.invoke == "target_arg":
        cmd.append(str(target))
        cwd = PLANNER_DIR
    else:
        cwd = target

    result = subprocess.run(cmd, cwd=cwd)
    return result.returncode


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _parse_args() -> tuple[Path, str | None]:
    parser = argparse.ArgumentParser(
        description="Run the claude-project-planner workflow.",
        add_help=True,
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="Target project directory (default: current directory)",
    )
    parser.add_argument(
        "-f", "--force",
        metavar="STAGE",
        choices=STAGE_IDS,
        default=None,
        help=f"Force-restart from this stage. Choices: {', '.join(STAGE_IDS)}",
    )
    args = parser.parse_args()
    target = Path(args.target).resolve() if args.target else Path.cwd()
    return target, args.force


def main() -> None:
    target, force_from = _parse_args()

    sep = "═" * 60
    print(f"\n{sep}")
    print("  Claude Project Planner")
    print(sep)

    # Determine which stage to start from
    force_index = STAGE_IDS.index(force_from) if force_from else None

    while True:
        # Find the first stage to run
        start_index: int | None = None
        for i, stage in enumerate(STAGES):
            if force_index is not None and i < force_index:
                continue  # skip stages before the forced start
            if force_index is not None and i == force_index:
                start_index = i
                force_index = None  # only force once; subsequent stages run normally
                break
            if not stage.check(target):
                start_index = i
                break

        current_id = STAGES[start_index].id if start_index is not None else None
        _print_stages(target, force_from if start_index is not None and STAGES[start_index].id == force_from else None, current_id)

        if start_index is None:
            print(f"  All stages complete. Your project is ready at:\n  {target}\n")
            break

        stage = STAGES[start_index]
        print(f"{sep}")
        print(f"  Running: {stage.id}")
        print(f"{sep}\n")

        returncode = _run_stage(stage, target)

        if returncode != 0:
            print(f"\n  ✗ Stage '{stage.id}' exited with code {returncode}.")
            print(f"  Fix the issue and re-run, or use -f {stage.id} to retry.\n")
            sys.exit(returncode)

        # After a stage completes, verify it actually finished
        if not stage.check(target):
            print(f"\n  ⚠  Stage '{stage.id}' ran but does not appear complete.")
            print(f"  Re-run to try again, or use -f {stage.id} to force-restart.\n")
            sys.exit(1)

        # Loop — will pick up the next incomplete stage automatically


if __name__ == "__main__":
    main()
