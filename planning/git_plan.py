"""
Git utilities for the plan branch workflow.

Strategy:
  - `plan` branch: holds all planning docs (PROJECT.md, ARCHITECTURE.md, PLAN.md, TASKS.md)
  - main / workstream branches: have planning doc filenames in .gitignore — only code
  - ME.md, WORKSTREAM.md, .beads_map.json: gitignored on ALL branches (personal/local)

Key operations:
  - ensure_plan_branch()   — create plan branch if it doesn't exist
  - commit_to_plan(files)  — commit files to plan branch without switching branches
  - sync_from_plan(files)  — pull latest planning docs from plan branch into working dir
  - plan_branch_exists()   — check
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

PLAN_BRANCH = "plan"

# Files that live on the plan branch only
PLANNING_DOCS = [
    "PROJECT.md",
    "ARCHITECTURE.md",
    "PLAN.md",
    "TASKS.md",
]

# Files that are gitignored on ALL branches (personal / local-only)
ALWAYS_IGNORED = [
    "ME.md",
    "WORKSTREAM.md",
    ".beads_map.json",
    ".beads/",            # local embedded Dolt database
    "issues.jsonl",       # BEADS export — only tracked on the plan branch
    ".planner_state.json", # local checkpoint for plan.py resume
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


def plan_branch_exists() -> bool:
    r = _git("rev-parse", "--verify", PLAN_BRANCH)
    return r.returncode == 0


# ---------------------------------------------------------------------------
# Branch setup
# ---------------------------------------------------------------------------

def ensure_plan_branch() -> bool:
    """
    Create the plan branch if it doesn't exist.
    Returns True if the branch is now ready, False if git is not available.
    """
    if not in_git_repo():
        return False

    if plan_branch_exists():
        return True

    # Create plan as an orphan branch so it has its own history
    branch = current_branch() or "main"
    print(f"  Creating `{PLAN_BRANCH}` branch for planning docs...")

    # Use a worktree to create the orphan branch without switching
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create orphan branch in a temp worktree
        r = _git("worktree", "add", "--orphan", "-b", PLAN_BRANCH, tmpdir)
        if r.returncode != 0:
            # Fallback: branch from current HEAD (not orphan)
            _git("branch", PLAN_BRANCH)
            print(f"  Created `{PLAN_BRANCH}` branch (from current HEAD).")
            return True

        # Add a .gitignore on the plan branch that only ignores personal files
        gitignore_path = Path(tmpdir) / ".gitignore"
        gitignore_path.write_text(
            "# Personal files — never committed\n"
            + "\n".join(ALWAYS_IGNORED)
            + "\n"
        )
        _git("add", ".gitignore", cwd=Path(tmpdir))
        _git(
            "commit", "-m",
            "chore: initialise plan branch for planning docs",
            cwd=Path(tmpdir),
        )
        _git("worktree", "remove", "--force", tmpdir)

    print(f"  `{PLAN_BRANCH}` branch ready.")
    return True


# ---------------------------------------------------------------------------
# Write to plan branch
# ---------------------------------------------------------------------------

def commit_to_plan(files: list[Path], message: str = "Update planning docs") -> bool:
    """
    Copy files into the plan branch and commit — without switching branches.
    Uses git worktree so the working directory is not disturbed.
    Returns True on success.
    """
    if not in_git_repo() or not plan_branch_exists():
        return False

    existing = [f for f in files if f.exists()]
    if not existing:
        return False

    with tempfile.TemporaryDirectory() as tmpdir:
        wt = Path(tmpdir) / "plan-wt"
        r = _git("worktree", "add", str(wt), PLAN_BRANCH)
        if r.returncode != 0:
            print(f"  WARNING: could not create worktree — {r.stderr.strip()}")
            return False

        try:
            for f in existing:
                shutil.copy2(f, wt / f.name)

            names = [f.name for f in existing]
            _git("add", *names, cwd=wt)

            r = _git("diff", "--cached", "--quiet", cwd=wt)
            if r.returncode == 0:
                return True  # nothing changed

            _git("commit", "-m", message, cwd=wt)
            print(f"  Committed to `{PLAN_BRANCH}`: {', '.join(names)}")
            return True
        finally:
            _git("worktree", "remove", "--force", str(wt))


# ---------------------------------------------------------------------------
# Read from plan branch
# ---------------------------------------------------------------------------

def sync_from_plan(files: list[str] | None = None, quiet: bool = False) -> list[str]:
    """
    Pull the latest version of planning docs from the plan branch into the
    current working directory. Returns list of files that were updated.
    """
    if not in_git_repo() or not plan_branch_exists():
        return []

    targets = files or PLANNING_DOCS
    updated: list[str] = []

    for name in targets:
        r = _git("show", f"{PLAN_BRANCH}:{name}")
        if r.returncode != 0:
            continue
        path = Path(name)
        existing = path.read_text() if path.exists() else None
        if existing != r.stdout:
            path.write_text(r.stdout)
            updated.append(name)
            if not quiet:
                print(f"  Synced {name} from `{PLAN_BRANCH}`")

    return updated


# ---------------------------------------------------------------------------
# Pull — sync from main, current branch, and plan branch
# ---------------------------------------------------------------------------

def pull_all(verbose: bool = True) -> dict[str, bool]:
    """
    Bring the working directory fully up to date:
      1. Fetch origin
      2. Merge origin/main (fast-forward only, so it never clobbers local work)
      3. Pull the current workstream branch from origin
      4. Sync planning docs from the plan branch into the working directory

    Returns a dict of {operation: success}.
    """
    results: dict[str, bool] = {}

    if not in_git_repo():
        return results

    branch = current_branch()

    def _run(label: str, *args: str) -> bool:
        r = _git(*args)
        ok = r.returncode == 0
        if verbose:
            icon = "✓" if ok else "✗"
            detail = r.stderr.strip() or r.stdout.strip()
            msg = detail.splitlines()[0] if detail else ""
            print(f"  {icon} {label}" + (f"  ({msg})" if msg and not ok else ""))
        results[label] = ok
        return ok

    # 1. Fetch everything
    _run("fetch origin", "fetch", "origin", "--prune")

    # 2. Fast-forward merge from origin/main (never rebases your work)
    r = _git("rev-parse", "--verify", "origin/main")
    if r.returncode == 0:
        _run("merge origin/main (ff-only)", "merge", "--ff-only", "origin/main")

    # 3. Pull current workstream branch
    if branch and branch not in ("main", PLAN_BRANCH):
        r = _git("rev-parse", "--verify", f"origin/{branch}")
        if r.returncode == 0:
            _run(f"pull origin/{branch}", "pull", "--ff-only", "origin", branch)

    # 4. Sync planning docs from plan branch
    if plan_branch_exists():
        updated = sync_from_plan(quiet=not verbose)
        results["sync plan docs"] = True
        if verbose and not updated:
            print("  ✓ plan docs  (already up to date)")

    return results


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
    """
    Ensure the project .gitignore has the right entries for the current branch.
    On main/workstream branches: ignore personal files AND planning docs.
    """
    gitignore = target_dir / ".gitignore"
    branch = current_branch()

    # Personal files ignored everywhere
    to_add = list(ALWAYS_IGNORED)

    # Planning docs ignored on all branches except plan itself
    if branch != PLAN_BRANCH:
        to_add.extend(PLANNING_DOCS)

    missing = [e for e in to_add if not _gitignore_has(gitignore, e)]
    if not missing:
        return

    with gitignore.open("a") as f:
        f.write("\n# claude-project-planner managed entries\n")
        for entry in missing:
            f.write(entry + "\n")

    print(f"  Added to .gitignore: {', '.join(missing)}")
