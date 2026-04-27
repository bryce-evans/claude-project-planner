#!/usr/bin/env python3
"""
Copy boilerplate files into a new or existing project directory.

Usage:
    python path/to/planning/setup.py [target_dir]

    target_dir defaults to the current directory.
"""

import shutil
import sys
from pathlib import Path
import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent))
from git_plan import ensure_gitignore

BOILERPLATE_DIR = Path(__file__).parent.parent / "boilerplate"
RENDER_SRC_DIR = Path(__file__).parent.parent / "render"
RENDER_PY_SRC = Path(__file__).parent.parent / "render" / "render.py"

# Files that get special merge handling instead of copy/overwrite
_MERGE_GITIGNORE = ".gitignore"
# ME.md is never overwritten — it is personal and untracked
_NEVER_OVERWRITE = {"ME.md"}


def _merge_gitignore(src: Path, dst: Path) -> None:
    """Add any missing entries from boilerplate .gitignore into the project's existing one."""
    boilerplate_lines = set(src.read_text().splitlines())
    existing_lines = set(dst.read_text().splitlines()) if dst.exists() else set()
    new_entries = [
        line for line in src.read_text().splitlines()
        if line and not line.startswith("#") and line not in existing_lines
    ]
    if new_entries:
        with dst.open("a") as f:
            f.write("\n# Added by claude-project-planner setup\n")
            f.write("\n".join(new_entries) + "\n")
        print(f"  ~ .gitignore (merged {len(new_entries)} new entr{'y' if len(new_entries)==1 else 'ies'})")
    else:
        print(f"  ~ .gitignore (already up to date)")


def main() -> None:
    target = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    target.mkdir(parents=True, exist_ok=True)

    print(f"\n  Setup — copying boilerplate into: {target}\n")

    if not BOILERPLATE_DIR.exists():
        print(f"  ERROR: boilerplate directory not found at {BOILERPLATE_DIR}")
        sys.exit(1)

    # Copy .claude/commands/ directory (Claude slash commands)
    commands_src = BOILERPLATE_DIR / ".claude" / "commands"
    if commands_src.exists():
        commands_dst = target / ".claude" / "commands"
        commands_dst.mkdir(parents=True, exist_ok=True)
        for cmd_src in sorted(commands_src.iterdir()):
            cmd_dst = commands_dst / cmd_src.name
            if not cmd_dst.exists():
                shutil.copy2(cmd_src, cmd_dst)
                print(f"  + .claude/commands/{cmd_src.name}")
            else:
                print(f"  ~ .claude/commands/{cmd_src.name} (kept existing)")

    sources = sorted(BOILERPLATE_DIR.iterdir())
    copied, skipped = [], []

    for src in sources:
        if not src.is_file():
            continue

        dst = target / src.name

        # Special case: .gitignore — always merge, never overwrite blindly
        if src.name == _MERGE_GITIGNORE:
            _merge_gitignore(src, dst)
            continue

        # Special case: ME.md — never overwrite an existing one
        if src.name in _NEVER_OVERWRITE:
            if dst.exists():
                print(f"  ~ {src.name} (kept existing — personal file)")
                skipped.append(src.name)
                continue
            else:
                shutil.copy2(src, dst)
                copied.append(src.name)
                print(f"  + {src.name}  ← fill this in with start.py")
                continue

        # All other files: prompt before overwriting
        if dst.exists():
            ans = input(f"  {src.name} already exists. Overwrite? [y/N]: ").strip().lower()
            if ans != "y":
                skipped.append(src.name)
                print(f"    skipped")
                continue

        shutil.copy2(src, dst)
        copied.append(src.name)
        print(f"  + {src.name}")

    print()
    print(f"  Copied {len(copied)} file(s).", end="")
    if skipped:
        print(f" Kept existing: {', '.join(skipped)}.", end="")
    print("\n")

    # render.py is included inside render/ via the copytree below

    # Copy render app (task visualiser) — skip node_modules, dist, and generated data
    render_dst = target / "render"
    if RENDER_SRC_DIR.exists() and not render_dst.exists():
        ignore = shutil.ignore_patterns("node_modules", "dist", "tasks.ts")
        shutil.copytree(RENDER_SRC_DIR, render_dst, ignore=ignore)
        print(f"  + render/  (task visualiser)")
    elif render_dst.exists():
        print(f"  ~ render/  (kept existing)")

    # Git setup — must run with cwd=target so git operates on the right repo
    import os
    orig_cwd = Path.cwd()
    os.chdir(target)
    print("  Configuring git...\n")
    ensure_gitignore(target)
    os.chdir(orig_cwd)

    planner = Path(__file__).parent.resolve()
    print("  Next steps (run these from your project directory):")
    print(f"  1. cd {target}")
    print(f"  2. python {planner}/start.py   — identify yourself and claim a workstream")
    print(f"  3. python {planner}/plan.py    — define the project and generate a plan\n")


if __name__ == "__main__":
    main()
