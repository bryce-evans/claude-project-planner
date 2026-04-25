"""
Git utilities for planning doc workflow.

Planning docs (PROJECT.md, ARCHITECTURE.md, PLAN.md, TASKS.md, FUTURE_WORK.md)
live on the main branch alongside code and are committed normally.

Personal/local files (ME.md, WORKSTREAM.md, .beads_map.json) are gitignored
on all branches.

Key operations:
  - commit_planning_docs(files) — stage and commit planning docs to current branch
  - ensure_gitignore(dir)       — add personal file entries to .gitignore
"""

import subprocess
from pathlib import Path

# Files that live in the repo alongside code
PLANNING_DOCS = [
    "PROJECT.md",
    "ARCHITECTURE.md",
    "PLAN.md",
    "TASKS.md",
    "FUTURE_WORK.md",
]

# Files that are gitignored on ALL branches (personal / local-only)
ALWAYS_IGNORED = [
    "ME.md",
    "WORKSTREAM.md",
    ".beads_map.json",
    ".beads/",
    "issues.jsonl",
    ".planner_state.json",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _git(*args: str, cwd: Path | None = None, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=check,
    )


def in_git_repo() -> bool:
    return _git("rev-parse", "--git-dir").returncode == 0


def current_branch() -> str:
    r = _git("branch", "--show-current")
    return r.stdout.strip() if r.returncode == 0 else ""


# ---------------------------------------------------------------------------
# Commit planning docs to current branch
# ---------------------------------------------------------------------------

def commit_planning_docs(files: list[Path], message: str = "planning: update docs") -> bool:
    """
    Stage and commit planning doc files to the current branch.
    Returns True if a commit was made or nothing changed, False on error.
    """
    if not in_git_repo():
        return False

    existing = [f for f in files if f.exists()]
    if not existing:
        return False

    _git("add", *[str(f) for f in existing])

    r = _git("diff", "--cached", "--quiet")
    if r.returncode == 0:
        return True  # nothing staged

    r = _git("commit", "-m", message)
    if r.returncode == 0:
        names = ", ".join(f.name for f in existing)
        print(f"  Committed: {names}")
        return True

    print(f"  WARNING: git commit failed — {r.stderr.strip()}")
    return False


# ---------------------------------------------------------------------------
# .gitignore management
# ---------------------------------------------------------------------------

def _gitignore_has(path: Path, entry: str) -> bool:
    if not path.exists():
        return False
    return any(
        line.strip() == entry
        for line in path.read_text().splitlines()
        if not line.startswith("#")
    )


def ensure_gitignore(target_dir: Path = Path(".")) -> None:
    """Ensure the project .gitignore has entries for personal/local files."""
    gitignore = target_dir / ".gitignore"
    missing = [e for e in ALWAYS_IGNORED if not _gitignore_has(gitignore, e)]
    if not missing:
        return

    with gitignore.open("a") as f:
        f.write("\n# claude-project-planner managed entries\n")
        for entry in missing:
            f.write(entry + "\n")

    print(f"  Added to .gitignore: {', '.join(missing)}")
