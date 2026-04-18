#!/usr/bin/env python3
"""
Orchestrate the full claude-project-planner workflow.

Usage (from anywhere):
    python path/to/planning/run.py [target_dir]        # auto-detects new vs existing
    python path/to/planning/run.py -f <stage>          # force-restart from stage
    python path/to/planning/run.py ~/my-project -f plan

Stages (in order):
    setup   — copy boilerplate files (CLAUDE.md, PLAN.md, TASKS.md, slash commands, …)
    plan    — define project, generate workstreams and task manifest
    start   — identify yourself and claim one of the defined workstreams
"""

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

PLANNER_DIR = Path(__file__).parent.resolve()
REPO_DIR    = PLANNER_DIR.parent
INIT_DIR    = REPO_DIR / "init"


# ---------------------------------------------------------------------------
# Dependency bootstrap
# ---------------------------------------------------------------------------

def _ensure_deps() -> None:
    """
    Ensure the planner's Python deps are installed in the venv.
    Prefers uv sync; falls back to pip. run.py itself doesn't need
    these imports — the scripts it spawns use _python() (the venv interpreter).
    """
    venv_python = REPO_DIR / ".venv" / "bin" / "python"
    if venv_python.exists():
        return  # venv already set up

    print("  Setting up planner environment...\n")
    has_uv = subprocess.run(["uv", "--version"], capture_output=True).returncode == 0

    if has_uv and (REPO_DIR / "pyproject.toml").exists():
        r = subprocess.run(["uv", "sync"], cwd=REPO_DIR)
        if r.returncode == 0:
            print()
            return
        print("  uv sync failed — falling back to pip.\n")

    # pip fallback: install into current interpreter
    req = PLANNER_DIR / "requirements.txt"
    cmd = [sys.executable, "-m", "pip", "install", "-q"]
    cmd += ["-r", str(req)] if req.exists() else ["anthropic>=0.40.0", "pyyaml>=6.0"]
    subprocess.run(cmd, check=True)

# ---------------------------------------------------------------------------
# API key check
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# New vs existing detection
# ---------------------------------------------------------------------------

# Files whose presence means the project already has real source code
_CODE_SIGNALS = [
    "pyproject.toml", "setup.py", "setup.cfg",   # Python
    "package.json",                                # Node / Web
    "go.mod",                                      # Go
    "Cargo.toml",                                  # Rust
    "pom.xml", "build.gradle", "build.gradle.kts", # JVM
    "*.csproj", "*.sln",                           # .NET
    "Gemfile",                                     # Ruby
    "composer.json",                               # PHP
    "mix.exs",                                     # Elixir
]


def _has_code(target: Path) -> bool:
    for signal in _CODE_SIGNALS:
        if "*" in signal:
            if list(target.glob(signal)):
                return True
        elif (target / signal).exists():
            return True
    return False


def _git_commit_count(target: Path) -> int:
    r = subprocess.run(
        ["git", "log", "--oneline"],
        capture_output=True, text=True, cwd=target,
    )
    if r.returncode != 0:
        return 0
    return len([l for l in r.stdout.strip().splitlines() if l.strip()])


def is_new_repo(target: Path) -> bool:
    """
    True when the target looks like a brand-new repo with no real source yet:
    at most one git commit (the empty init commit) and no language config files.
    """
    return _git_commit_count(target) <= 1 and not _has_code(target)


# ---------------------------------------------------------------------------
# Stage definition
# ---------------------------------------------------------------------------

@dataclass
class Stage:
    id: str
    label: str
    check: Callable[[Path], bool]
    script: Path | None = None         # None for stages handled inline (init)
    invoke: str = "cwd"                # "cwd" | "target_arg"


# ---------------------------------------------------------------------------
# Stage: setup / start / plan  (subprocess-based)
# ---------------------------------------------------------------------------

def _check_setup(target: Path) -> bool:
    required = ["CLAUDE.md", "PLAN.md", "TASKS.md", "ARCHITECTURE.md", "PROJECT.md"]
    return (
        all((target / f).exists() for f in required)
        and (target / ".claude" / "commands").is_dir()
    )


def _check_start(target: Path) -> bool:
    me = target / "ME.md"
    ws = target / "WORKSTREAM.md"
    if not me.exists() or not ws.exists():
        return False
    if "_TODO_" in me.read_text():
        return False
    m = re.search(r"\*\*Workstream:\*\*\s*(.+)", ws.read_text())
    if not m:
        return False
    value = m.group(1).strip()
    return bool(value) and value != "—"


def _check_plan(target: Path) -> bool:
    tasks = target / "TASKS.md"
    plan  = target / "PLAN.md"
    if not tasks.exists() or not plan.exists():
        return False
    has_tasks = any(
        re.match(r"\|\s*T\d+", line)
        for line in tasks.read_text().splitlines()
    )
    has_ws = any(
        re.match(r"\|\s*WS\d+", line)
        for line in plan.read_text().splitlines()
    )
    return has_tasks and has_ws


def _python() -> str:
    """Return the python executable to use — venv if available, else current."""
    venv = REPO_DIR / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


def _run_script(stage: Stage, target: Path) -> int:
    assert stage.script is not None
    cmd = [_python(), str(stage.script)]
    if stage.invoke == "target_arg":
        cmd.append(str(target))
        cwd = PLANNER_DIR
    else:
        cwd = target
    return subprocess.run(cmd, cwd=cwd).returncode


# ---------------------------------------------------------------------------
# Build stage list based on repo type
# ---------------------------------------------------------------------------

_STAGE_SETUP = Stage(
    id="setup",
    label="Setup       — copy boilerplate, slash commands, plan branch",
    check=_check_setup,
    script=PLANNER_DIR / "setup.py",
    invoke="target_arg",
)

_STAGE_PLAN = Stage(
    id="plan",
    label="Plan        — define project, generate task manifest",
    check=_check_plan,
    script=PLANNER_DIR / "plan.py",
)

_STAGE_START = Stage(
    id="start",
    label="Start       — identify yourself, claim a workstream",
    check=_check_start,
    script=PLANNER_DIR / "start.py",
)


def build_stages(target: Path, force_from: str | None) -> list[Stage]:
    return [_STAGE_SETUP, _STAGE_PLAN, _STAGE_START]


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def _print_stages(stages: list[Stage], target: Path, current_id: str | None) -> None:
    print(f"\n  Project: {target}")
    print(f"  Mode:    {'new repo' if is_new_repo(target) else 'existing repo'}\n")
    for stage in stages:
        done = stage.check(target)
        if done:
            marker = "✓"
        elif stage.id == current_id:
            marker = "▶"
        else:
            marker = "○"
        print(f"  {marker}  {stage.label}")
    print()


# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------

_ALL_STAGE_IDS = ["setup", "plan", "start"]


def _parse_args() -> tuple[Path, str | None]:
    parser = argparse.ArgumentParser(
        description="Run the claude-project-planner workflow.",
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
        choices=_ALL_STAGE_IDS,
        default=None,
        help=f"Force-restart from this stage. Choices: {', '.join(_ALL_STAGE_IDS)}",
    )
    args = parser.parse_args()
    target = Path(args.target).resolve() if args.target else Path.cwd()
    target.mkdir(parents=True, exist_ok=True)
    return target, args.force


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    target, force_from = _parse_args()

    sep = "═" * 60
    print(f"\n{sep}")
    print("  Claude Project Planner")
    print(sep)

    _ensure_deps()

    stages = build_stages(target, force_from)
    stage_ids = [s.id for s in stages]

    force_index = stage_ids.index(force_from) if force_from and force_from in stage_ids else None

    while True:
        # Find the first stage to run
        start_index: int | None = None
        for i, stage in enumerate(stages):
            if force_index is not None:
                if i < force_index:
                    continue
                if i == force_index:
                    start_index = i
                    force_index = None
                    break
            if not stage.check(target):
                start_index = i
                break

        current_id = stages[start_index].id if start_index is not None else None
        _print_stages(stages, target, current_id)

        if start_index is None:
            print(f"  All stages complete. Your project is ready at:\n  {target}\n")
            break

        stage = stages[start_index]
        print(f"{sep}")
        print(f"  Running: {stage.id}")
        print(f"{sep}\n")

        returncode = _run_script(stage, target)

        if returncode != 0:
            print(f"\n  ✗ Stage '{stage.id}' exited with code {returncode}.")
            print(f"  Fix the issue and re-run, or use -f {stage.id} to retry.\n")
            sys.exit(returncode)

        if not stage.check(target):
            print(f"\n  ⚠  Stage '{stage.id}' ran but does not appear complete.")
            print(f"  Re-run to try again, or use -f {stage.id} to force-restart.\n")
            sys.exit(1)

        # Re-evaluate stage list in case init changed what's needed
        stages = build_stages(target, None)
        stage_ids = [s.id for s in stages]


if __name__ == "__main__":
    main()
