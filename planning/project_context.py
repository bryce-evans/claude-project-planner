"""Project definition: PROJECT.md helpers, repo context analysis, project type selection."""

import re
import subprocess
import sys
from pathlib import Path

from git_plan import commit_planning_docs
from claude_runner import call_claude_cli as call_claude
from ui import hr, header, prompt_section


PROJECT_MD = Path("PROJECT.md")
ARCHITECTURE_MD = Path("ARCHITECTURE.md")

SECTIONS = [
    ("motivation",        "Motivation",        "What problem does this project solve? Why does it need to exist?"),
    ("goals",             "Goals",             "What are the high-level goals? What does success look like?"),
    ("success_criteria",  "Success Criteria",  "How will you measure success? List specific, observable outcomes."),
    ("priorities",        "Priorities",        "What matters most? What can be cut if time or resources are tight?"),
    ("resources_allowed", "Resources Allowed", "What tools, APIs, services, and budget are available?"),
    ("resources_off_limits", "Resources Off Limits", "What is explicitly forbidden or unavailable? (type 'none' if nothing)"),
    ("final_result",      "Final Result",      "Describe the end product concretely. What does a user see and do?"),
]

TODO_MARKER = re.compile(r"^_TODO.*_$", re.MULTILINE)


# ---------------------------------------------------------------------------
# PROJECT.md helpers
# ---------------------------------------------------------------------------

def load_project_md() -> dict[str, str]:
    if not PROJECT_MD.exists():
        return {}
    content = PROJECT_MD.read_text()
    sections: dict[str, str] = {}
    for key, title, _ in SECTIONS:
        pattern = rf"## {re.escape(title)}\n([\s\S]*?)(?=\n## |\Z)"
        m = re.search(pattern, content)
        if m:
            value = m.group(1).strip()
            if value and not TODO_MARKER.match(value):
                sections[key] = value
    return sections


def save_project_md(sections: dict[str, str]) -> None:
    lines = ["# Project Definition\n"]
    for key, title, _ in SECTIONS:
        lines.append(f"## {title}\n")
        lines.append((sections.get(key) or "_TODO_") + "\n\n")
    PROJECT_MD.write_text("\n".join(lines))
    commit_planning_docs([PROJECT_MD], "planning: update PROJECT.md")


def _project_summary(sections: dict[str, str], repo_context: str | None = None) -> str:
    lines = [
        f"**{title}:** {sections.get(key, 'N/A')}"
        for key, title, _ in SECTIONS
    ]
    if repo_context:
        lines.append(f"\n**Existing codebase context:**\n{repo_context}")
    return "\n".join(lines)


def _stack_summary(components: list[dict]) -> str:
    return "\n".join(
        f"- **{c['name']}**: {c['tech']} — {c['rationale']}" for c in components
    )


# ---------------------------------------------------------------------------
# Phase 1 — collect project definition
# ---------------------------------------------------------------------------

def collect_project_info() -> dict[str, str]:
    print("\n" + hr("="))
    print("  Claude Project Planner — Step 1: Project Definition")
    print(hr("="))

    existing = load_project_md()
    sections: dict[str, str] = dict(existing)

    filled = len([k for k, _, _ in SECTIONS if k in existing])
    total = len(SECTIONS)
    if filled:
        print(f"\n  Found existing PROJECT.md ({filled}/{total} sections filled).")
        if filled == total:
            print("  All sections complete — skipping to next phase.\n")
            return sections
    else:
        print("\n  No PROJECT.md found — starting fresh.")

    for key, title, question in SECTIONS:
        if key in existing:
            print(f"\n  ✓  {title}: (loaded from PROJECT.md — skipping)")
            continue
        sections[key] = prompt_section(key, title, question, None)
        save_project_md(sections)

    return sections


# ---------------------------------------------------------------------------
# Phase 0 — existing repo context
# ---------------------------------------------------------------------------

REPO_CONTEXT_PROMPT = """\
You are a senior software architect reviewing an existing codebase to inform project planning.

The user is running a planning session on top of an existing repository.

Git log (recent commits):
{git_log}

Directory structure:
{tree}

Key file contents:
{file_contents}

Summarise what you observe in 3-5 bullet points:
- What the codebase does (inferred from structure and commits)
- Tech stack already in use
- Any patterns, conventions, or constraints a planner should know about
- Potential conflicts or considerations for new work being planned on top of this

Then list up to 5 specific questions the user should answer before planning begins, \
to make sure the plan fits the existing code. Format questions as a numbered list.

Keep the whole response under 400 words.
"""

_IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
    ".next", ".nuxt", "coverage", ".pytest_cache", ".mypy_cache",
}
_KEY_FILES = {
    "package.json", "pyproject.toml", "requirements.txt", "Cargo.toml",
    "go.mod", "Makefile", "docker-compose.yml", "README.md", "ARCHITECTURE.md",
}


def _git_log() -> str:
    r = subprocess.run(["git", "log", "--oneline", "-20"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else "(no git history)"


def _dir_tree(max_depth: int = 3) -> str:
    lines: list[str] = []

    def walk(path: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
        except PermissionError:
            return
        for entry in entries:
            if entry.name in _IGNORE_DIRS or entry.name.startswith("."):
                continue
            indent = "  " * depth
            lines.append(f"{indent}{entry.name}{'/' if entry.is_dir() else ''}")
            if entry.is_dir():
                walk(entry, depth + 1)

    walk(Path("."), 0)
    return "\n".join(lines[:120])


def _read_key_files() -> str:
    parts: list[str] = []
    for name in _KEY_FILES:
        p = Path(name)
        if p.exists():
            content = p.read_text()[:1500]
            parts.append(f"--- {name} ---\n{content}")
    return "\n\n".join(parts) or "(none found)"


def existing_repo_context() -> str | None:
    git_log = _git_log()
    is_existing = git_log != "(no git history)" and len(git_log.splitlines()) > 2

    print("\n" + hr("="))
    print("  Step 0: Existing Repo Context")
    print(hr("="))

    if is_existing:
        print(f"\n  Detected existing git history ({len(git_log.splitlines())} commits).")
    else:
        print("\n  No significant git history found.")

    print("  Is this plan for an existing codebase? [Y/n]: ", end="")
    ans = input().strip().lower()
    if ans == "n":
        print("  Starting fresh — skipping repo context.\n")
        return None

    print("\n  Analysing existing codebase...\n")

    prompt = REPO_CONTEXT_PROMPT.format(
        git_log=git_log or "(empty)",
        tree=_dir_tree(),
        file_contents=_read_key_files(),
    )
    context = call_claude(prompt, max_tokens=1024)
    print()

    print("  Answer any of the questions above that are relevant,")
    print("  or press Enter to continue. (These will be added to project context.)\n")
    answers: list[str] = []
    print("  (Blank line to finish)\n")
    while True:
        line = input("  > ")
        if not line:
            break
        answers.append(line)

    if answers:
        context += "\n\nUser clarifications:\n" + "\n".join(f"- {a}" for a in answers)

    return context


# ---------------------------------------------------------------------------
# Phase 0a — project type selection
# ---------------------------------------------------------------------------

_ARCH_TYPE_MARKER = "## Project Type\n"
_INIT_DIR = Path(__file__).parent.parent / "init"


def select_project_type() -> str | None:
    """Present scaffold menu for new projects; record decision in ARCHITECTURE.md."""
    arch = ARCHITECTURE_MD

    if arch.exists() and _ARCH_TYPE_MARKER in arch.read_text():
        text = arch.read_text()
        start = text.index(_ARCH_TYPE_MARKER) + len(_ARCH_TYPE_MARKER)
        end = text.find("\n##", start)
        return text[start:end].strip() if end != -1 else text[start:].strip()

    code_signals = [
        "pyproject.toml", "package.json", "go.mod", "Cargo.toml",
        "app.json", "app.config.ts", "vite.config.ts", "next.config.js",
    ]
    if any(Path(f).exists() for f in code_signals):
        return None

    sys.path.insert(0, str(_INIT_DIR.parent))
    try:
        from init import SCAFFOLDERS
    except ImportError:
        return None

    print("\n" + hr("="))
    print("  Step 0a: Project Type")
    print(hr("="))
    print("\n  What kind of project are you building?\n")
    for i, s in enumerate(SCAFFOLDERS, 1):
        print(f"  {i}. {s.NAME:<34}  {s.DESCRIPTION}")
    print(f"  {len(SCAFFOLDERS) + 1}. Other / not listed\n")

    choice = input("  Choice (Enter to skip): ").strip()
    if not choice.isdigit():
        return None
    idx = int(choice) - 1
    if not (0 <= idx < len(SCAFFOLDERS)):
        return None

    s = SCAFFOLDERS[idx]
    stack_notes = f"**Type:** {s.NAME}\n**Stack:** {s.STACK_NOTES}\n"

    if not arch.exists():
        arch.write_text("# Architecture\n\n_To be filled in during planning._\n")

    existing = arch.read_text().rstrip()
    arch.write_text(existing + f"\n\n{_ARCH_TYPE_MARKER}{stack_notes}")
    print(f"\n  Project type recorded in ARCHITECTURE.md: {s.NAME}\n")
    return stack_notes
