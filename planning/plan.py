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
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from schema import (
    TASK_FIELDS, field_descriptions, prompt_example,
    enforce_defaults, validate_all,
)
from git_plan import ensure_plan_branch, commit_to_plan, ensure_gitignore
from claude_runner import call_claude_cli as call_claude


PROJECT_MD = Path("PROJECT.md")
ARCHITECTURE_MD = Path("ARCHITECTURE.md")

SECTIONS = [
    (
        "motivation",
        "Motivation",
        "What problem does this project solve? Why does it need to exist?",
    ),
    (
        "goals",
        "Goals",
        "What are the high-level goals? What does success look like?",
    ),
    (
        "success_criteria",
        "Success Criteria",
        "How will you measure success? List specific, observable outcomes.",
    ),
    (
        "priorities",
        "Priorities",
        "What matters most? What can be cut if time or resources are tight?",
    ),
    (
        "resources_allowed",
        "Resources Allowed",
        "What tools, APIs, services, and budget are available?",
    ),
    (
        "resources_off_limits",
        "Resources Off Limits",
        "What is explicitly forbidden or unavailable? (type 'none' if nothing)",
    ),
    (
        "final_result",
        "Final Result",
        "Describe the end product concretely. What does a user see and do?",
    ),
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
    commit_to_plan([PROJECT_MD], "planning: update PROJECT.md")


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def hr(char: str = "─", width: int = 60) -> str:
    return char * width


def header(title: str) -> None:
    print(f"\n{hr()}")
    print(f"  {title}")
    print(hr())


def prompt_section(key: str, title: str, question: str, existing: str | None) -> str:
    header(title)
    print(f"\n  {question}")

    if existing:
        print(f"\n  Current answer:\n")
        for line in existing.splitlines():
            print(f"    {line}")
        print()
        keep = input("  Keep this? [Y/n]: ").strip().lower()
        if keep != "n":
            return existing

    print()
    lines: list[str] = []
    print("  (Enter your answer. Blank line to finish.)\n")
    while True:
        line = input("  > ")
        if line == "":
            break
        lines.append(line)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 0 — existing repo context (runs before project definition)
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
    r = subprocess.run(
        ["git", "log", "--oneline", "-20"], capture_output=True, text=True
    )
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
    return "\n".join(lines[:120])  # cap at 120 lines


def _read_key_files() -> str:
    parts: list[str] = []
    for name in _KEY_FILES:
        p = Path(name)
        if p.exists():
            content = p.read_text()[:1500]
            parts.append(f"--- {name} ---\n{content}")
    return "\n\n".join(parts) or "(none found)"


_ARCH_TYPE_MARKER = "## Project Type\n"
_INIT_DIR = Path(__file__).parent.parent / "init"


def select_project_type() -> str | None:
    """
    For new projects: present the scaffold menu and record the decision in
    ARCHITECTURE.md. No commands are run — just writes the decision text.
    Skipped if ARCHITECTURE.md already has a Project Type section.
    Returns the STACK_NOTES string for inclusion in subsequent Claude prompts,
    or None if skipped/existing.
    """
    arch = Path("ARCHITECTURE.md")

    # Already decided
    if arch.exists() and _ARCH_TYPE_MARKER in arch.read_text():
        # Extract and return existing notes
        text = arch.read_text()
        start = text.index(_ARCH_TYPE_MARKER) + len(_ARCH_TYPE_MARKER)
        end = text.find("\n##", start)
        return text[start:end].strip() if end != -1 else text[start:].strip()

    # Only ask for genuinely new repos (no language config files present)
    code_signals = [
        "pyproject.toml", "package.json", "go.mod", "Cargo.toml",
        "app.json", "app.config.ts", "vite.config.ts", "next.config.js",
    ]
    if any(Path(f).exists() for f in code_signals):
        return None

    # Load scaffolders
    import sys as _sys
    _sys.path.insert(0, str(_INIT_DIR.parent))
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

    # Append to ARCHITECTURE.md (create minimal placeholder if missing)
    if not arch.exists():
        arch.write_text("# Architecture\n\n_To be filled in during planning._\n")

    existing = arch.read_text().rstrip()
    arch.write_text(existing + f"\n\n{_ARCH_TYPE_MARKER}{stack_notes}")
    print(f"\n  Project type recorded in ARCHITECTURE.md: {s.NAME}\n")
    return stack_notes


def existing_repo_context() -> str | None:
    """
    Detect if we're in an existing repo with history.
    If yes, analyse it with Claude and return a context summary string.
    Returns None if the user skips or there's no meaningful existing code.
    """
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

    # Let user answer any questions Claude raised before continuing
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
# Phase 2 — tech stack recommendations
# ---------------------------------------------------------------------------

def _project_summary(sections: dict[str, str], repo_context: str | None = None) -> str:
    lines = [
        f"**{title}:** {sections.get(key, 'N/A')}"
        for key, title, _ in SECTIONS
    ]
    if repo_context:
        lines.append(f"\n**Existing codebase context:**\n{repo_context}")
    return "\n".join(lines)


TECH_STACK_PROMPT = """\
You are a senior software architect helping a developer choose a tech stack.

Here is their project definition:

{summary}

Your job:
1. Identify the distinct components this project likely needs \
(e.g. CLI, frontend, backend API, database, auth, background jobs, deployment, etc.).
2. For each component, recommend one specific technology or framework.
3. Give a single-sentence rationale for each choice.
4. Flag any components where the choice is particularly opinionated or has a meaningful \
alternative — mark those with "(alt: X)" after the rationale.

Prefer boring, proven choices. Only recommend something newer/exotic if the project \
clearly benefits from it.

Format exactly like this (one component per line, no extra text before or after):

1. **Component Name**: Technology — rationale. (alt: Alternative) [optional]
2. **Component Name**: Technology — rationale.
...
"""


def stream_recommendations(sections: dict[str, str], repo_context: str | None = None) -> str:
    summary = _project_summary(sections, repo_context)

    print("\n" + hr("="))
    print("  Step 2: Tech Stack Recommendations")
    print(hr("="))
    print("\n  Analyzing your project...\n")
    return call_claude(TECH_STACK_PROMPT.format(summary=summary), max_tokens=1024)


def parse_components(raw: str) -> list[dict]:
    """Parse numbered list into [{name, tech, rationale, alt}]."""
    components = []
    pattern = re.compile(
        r"\d+\.\s+\*\*(.+?)\*\*:\s+(.+?)\s+—\s+(.+?)(?:\s+\(alt:\s+(.+?)\))?\s*$"
    )
    for line in raw.splitlines():
        m = pattern.match(line.strip())
        if m:
            components.append(
                {
                    "name": m.group(1).strip(),
                    "tech": m.group(2).strip(),
                    "rationale": m.group(3).strip(),
                    "alt": m.group(4).strip() if m.group(4) else None,
                }
            )
    return components


def confirm_tech_stack(raw_recs: str) -> list[dict] | None:
    """Let the user accept, tweak per-component, or skip."""
    components = parse_components(raw_recs)

    if not components:
        print("  Could not parse recommendations — showing raw output above.")
        print("  Edit ARCHITECTURE.md manually after this run.")
        return None

    header("Review Tech Stack — confirm or override each component")
    print("\n  For each component: press Enter to accept, or type your preferred technology.\n")

    confirmed: list[dict] = []
    for c in components:
        alt_hint = f"  (alt: {c['alt']})" if c["alt"] else ""
        print(f"\n  {c['name']}: {c['tech']}{alt_hint}")
        print(f"    {c['rationale']}")
        override = input("  Accept? [Enter] or type replacement: ").strip()
        if override:
            c = {**c, "tech": override, "rationale": "(user override)"}
        confirmed.append(c)

    return confirmed


# ---------------------------------------------------------------------------
# Phase 3 — write ARCHITECTURE.md
# ---------------------------------------------------------------------------

ARCH_PROMPT = """\
You are a senior software architect. Write a concise ARCHITECTURE.md for this project.

Project definition:
{summary}

Agreed tech stack:
{stack}

Include these sections:
1. **Overview** — 1-2 sentences
2. **Components** — markdown table: Component | Technology | Directory | Purpose
3. **Component Details** — one subsection per component with directory path and scope (1-2 sentences)
4. **Interfaces** — APIs and data contracts between components; use TODO where not yet known

Rules:
- Use the exact technology names agreed above.
- Suggest sensible directory paths (e.g. `frontend/`, `api/`, `db/`).
- Keep each section tight. No fluff.
- Start the document with: \
`> Generated by planning/plan.py. Edit manually or re-run the planner to regenerate.`
"""


def write_architecture(sections: dict[str, str], components: list[dict], repo_context: str | None = None) -> None:
    summary = _project_summary(sections, repo_context)
    stack = "\n".join(
        f"- **{c['name']}**: {c['tech']} — {c['rationale']}" for c in components
    )

    header("Generating ARCHITECTURE.md")
    print()

    content = call_claude(ARCH_PROMPT.format(summary=summary, stack=stack), max_tokens=2048)
    ARCHITECTURE_MD.write_text(content)
    print(f"\n\n  Written to {ARCHITECTURE_MD}\n")
    commit_to_plan([ARCHITECTURE_MD], "planning: update ARCHITECTURE.md")


# ---------------------------------------------------------------------------
# Phase 3b — interface review
# ---------------------------------------------------------------------------

INTERFACE_EXTRACT_PROMPT = """\
You are a senior software architect reviewing a project architecture.

ARCHITECTURE.md:
{architecture}

Extract and display all critical interfaces that need explicit design agreement. Cover:
- REST / GraphQL / WebSocket endpoints: method, path, key request + response fields
- JSON schemas: event shapes, DTOs, config files
- Database schemas: tables or collections with key columns / fields and types
- Inter-service contracts: message queues, internal RPC, pub/sub topics
- External integrations: third-party APIs being called or consumed

Format each interface as:

### [Type] Interface Name
<brief schema, signature, or field list — use a code block where helpful>
_TODOs or open questions, if any_

Skip categories that don't apply. Keep entries tight — enough detail to spot gaps, \
not a full spec. Do not include anything not already implied by the architecture.
"""

INTERFACE_APPLY_CORRECTION_PROMPT = """\
You are updating a software architecture document based on user feedback.

Current ARCHITECTURE.md:
{architecture}

User correction:
{correction}

Apply this correction to the architecture. Update interface definitions, schemas, \
endpoint signatures, component details, or any other section as the correction requires. \
Preserve everything not mentioned.

Return the complete updated ARCHITECTURE.md. Begin with the \
`> Generated by planning/plan.py` header line.
"""


def review_interfaces() -> None:
    """
    Extract key interfaces from ARCHITECTURE.md, show them to the user, and iterate
    with natural-language corrections until the user is satisfied.
    """
    print("\n" + hr("="))
    print("  Step 3b: Interface Review")
    print(hr("="))
    print("\n  Extracting critical interfaces from ARCHITECTURE.md...\n")

    while True:
        architecture = ARCHITECTURE_MD.read_text() if ARCHITECTURE_MD.exists() else ""
        call_claude(
            INTERFACE_EXTRACT_PROMPT.format(architecture=architecture),
            max_tokens=2048,
            print_output=True,
        )
        print()

        print(f"  {hr('·')}")
        print("  Enter a correction in plain English, or press Enter when interfaces look good.")
        print(f"  {hr('·')}\n")

        lines: list[str] = []
        while True:
            line = input("  > ")
            if not line:
                break
            lines.append(line)

        if not lines:
            commit_to_plan([ARCHITECTURE_MD], "planning: finalize interfaces in ARCHITECTURE.md")
            print("  Interfaces accepted.\n")
            break

        correction = "\n".join(lines)
        print("\n  Applying correction...\n")
        updated = call_claude(
            INTERFACE_APPLY_CORRECTION_PROMPT.format(
                architecture=architecture,
                correction=correction,
            ),
            max_tokens=3000,
            print_output=False,
        )
        ARCHITECTURE_MD.write_text(updated)
        print("  ARCHITECTURE.md updated — reviewing again...\n")


# ---------------------------------------------------------------------------
# Phase 4 — re-iterate: gaps, alternatives, clarifications
# ---------------------------------------------------------------------------

REITERATE_PROMPT = """\
You are a senior software architect performing a structured plan review.

Project definition:
{summary}

Agreed tech stack:
{stack}

Review the plan across five lenses and produce a short, high-signal list of observations.

Lenses:

- GAP: something not considered that could cause real problems — missing requirements, \
operational concerns, security holes, scaling limits, edge cases, or integration risks.
- RISK: a specific thing that is likely to go wrong or take much longer than expected, \
with a concrete reason why (not generic "this is hard" warnings).
- MOTIVATION: a place where the chosen approach, tech, or scope does not obviously serve \
the stated motivation or success criteria — call out the mismatch and what would align better.
- ALTERNATIVE: a tech or design choice with a meaningful trade-off worth reconsidering, \
paired with a specific suggestion and why it might be a better fit.
- CLARIFY: a question where the answer would meaningfully change the plan or architecture.

Rules:
- Be specific. "Have you considered auth?" is too vague. Instead: "You mentioned user accounts \
but didn't specify social login vs email+password — this changes your auth library choice and \
adds an OAuth integration to scope."
- 5–9 items total across all lenses. Quality over quantity — only raise things that genuinely \
matter for this specific project.
- Do not repeat anything already addressed in the project definition.
- Prioritise RISK and MOTIVATION items if the plan has clear weak points there.
- Format exactly — one item per line, no blank lines between items, no extra text:

[GAP] observation
[RISK] observation
[MOTIVATION] observation
[ALTERNATIVE] observation
[CLARIFY] question
"""

ITEM_LABELS = {
    "GAP":         ("Gap",         "Something not considered that could cause problems"),
    "RISK":        ("Risk",        "Something likely to go wrong or take much longer than expected"),
    "MOTIVATION":  ("Motivation",  "A mismatch between the approach and the stated goals"),
    "ALTERNATIVE": ("Alternative", "Another approach worth weighing"),
    "CLARIFY":     ("Clarify",     "A question whose answer would change the plan"),
}


def _parse_reiterate(raw: str) -> list[dict]:
    items = []
    for line in raw.splitlines():
        line = line.strip()
        for tag in ITEM_LABELS:
            prefix = f"[{tag}]"
            if line.startswith(prefix):
                items.append({"tag": tag, "text": line[len(prefix):].strip()})
                break
    return items


def _stack_summary(components: list[dict]) -> str:
    return "\n".join(
        f"- **{c['name']}**: {c['tech']} — {c['rationale']}" for c in components
    )


def _append_clarifications(entries: list[dict]) -> None:
    """Append a Review Notes section to PROJECT.md with Q&A pairs."""
    existing = PROJECT_MD.read_text() if PROJECT_MD.exists() else ""

    # Remove old block if present
    existing = re.sub(r"\n## Review Notes\n[\s\S]*$", "", existing).rstrip()
    existing = re.sub(r"\n## Clarifications\n[\s\S]*$", "", existing).rstrip()

    block = "\n\n## Review Notes\n\n"
    for e in entries:
        label = ITEM_LABELS[e["tag"]][0]
        block += f"**[{label}]** {e['text']}\n\n"
        block += f"> {e['response']}\n\n"

    PROJECT_MD.write_text(existing + block)


def reiterate(sections: dict[str, str], components: list[dict]) -> None:
    summary = _project_summary(sections)
    stack = _stack_summary(components)

    print("\n" + hr("="))
    print("  Step 4: Re-iterate — Validation & Review")
    print(hr("="))
    print("\n  Reviewing your plan for weak points, risks, motivation alignment, and improvements...\n")

    raw = call_claude(REITERATE_PROMPT.format(summary=summary, stack=stack), max_tokens=1536)

    items = _parse_reiterate(raw)
    if not items:
        print("  Nothing significant to flag. Your plan looks solid.\n")
        return

    print(f"  Found {len(items)} item(s). Go through each — press Enter to skip.\n")

    responses: list[dict] = []
    for i, item in enumerate(items, 1):
        label, subtitle = ITEM_LABELS[item["tag"]]
        print(f"\n  {hr('·')}")
        print(f"  [{i}/{len(items)}]  {label.upper()}  —  {subtitle}")
        print(f"  {hr('·')}")
        print(f"\n  {item['text']}\n")

        answer = input("  Your response (or Enter to skip): ").strip()
        if answer:
            responses.append({**item, "response": answer})
            print("  Noted.")

    if responses:
        _append_clarifications(responses)
        print(f"\n  {len(responses)} response(s) saved to PROJECT.md.\n")
    else:
        print("\n  No responses recorded.\n")


# ---------------------------------------------------------------------------
# Phase 5 — workstreams and PLAN.md
# ---------------------------------------------------------------------------

PLAN_MD = Path("PLAN.md")

WS_RECOMMEND_PROMPT = """\
You are a senior software architect dividing project work into parallel workstreams.

Project definition:
{summary}

Tech stack:
{stack}

Identify {count_instruction} natural workstreams that could be staffed and run in parallel. \
Each should represent a coherent branch of the project with clear ownership.

For each workstream:
- Assign an ID: WS1, WS2, ...
- Suggest a creative single-word codename that captures the essence of the work. \
  Examples: "Keymaster" (auth), "Dazzler" (frontend), "Bedrock" (database), \
  "Puppeteer" (deployment/k8s), "Switchboard" (API gateway), "Archivist" (storage). \
  Make the name memorable and fitting, not generic.
- Write a one-sentence scope: what this workstream owns and does NOT own.

Format exactly — pipe-separated, one workstream per line, no extra text:
WS1 | Codename | Scope sentence
WS2 | Codename | Scope sentence
"""

WS_TASKS_PROMPT = """\
You are a senior software architect generating the task list for one workstream.

Project:
{summary}

Tech stack:
{stack}

All workstreams (for context — do not duplicate work across them):
{all_ws}

Generate the task breakdown for:
  {ws_id} — {ws_name}: {ws_scope}

Rules:
- Tasks should be concrete, actionable steps (imperative verb phrase).
- Order them roughly by execution sequence.
- 4–10 tasks. No padding.
- Priority: P0 = blocking other workstreams or the project / P1 = required for launch / \
  P2 = nice to have
- Estimate: rough (2h / 4h / 1d / 2d / 1w)
- Blockers: other task names, other workstream IDs, or external dependencies. Use "—" if none.

Format exactly — pipe-separated, one task per line, no header, no extra text:
Task name | P0/P1/P2 | estimate | blockers
"""


def _parse_workstreams(raw: str) -> list[dict]:
    ws_list = []
    for line in raw.splitlines():
        line = line.strip()
        parts = [p.strip() for p in line.split("|")]
        if len(parts) == 3 and re.match(r"WS\d+", parts[0]):
            ws_list.append({"id": parts[0], "name": parts[1], "scope": parts[2], "tasks": []})
    return ws_list


def _parse_tasks(raw: str) -> list[dict]:
    tasks = []
    for line in raw.splitlines():
        line = line.strip()
        parts = [p.strip() for p in line.split("|")]
        if len(parts) == 4:
            tasks.append(
                {
                    "name": parts[0],
                    "priority": parts[1],
                    "estimate": parts[2],
                    "blockers": parts[3],
                    "status": "todo",
                }
            )
    return tasks


def _all_ws_summary(ws_list: list[dict]) -> str:
    return "\n".join(f"  {w['id']} — {w['name']}: {w['scope']}" for w in ws_list)


def _stream_text(prompt: str, max_tokens: int = 1024) -> str:
    return call_claude(prompt, max_tokens=max_tokens)


def _get_workstream_count(sections: dict[str, str], components: list[dict]) -> tuple[int | None, str]:
    """Ask the user for a count or let Claude decide. Returns (count_or_None, instruction_string)."""
    print("\n  How many workstreams?")
    print("  Enter a number (e.g. 3 for a 3-person team), or press Enter for Claude to recommend.\n")
    raw = input("  > ").strip()
    if raw.isdigit() and int(raw) > 0:
        n = int(raw)
        return n, f"exactly {n}"
    return None, "2–6 (choose the most natural split for this project)"


def recommend_workstreams(
    sections: dict[str, str], components: list[dict], count_instruction: str,
    repo_context: str | None = None,
) -> list[dict]:
    summary = _project_summary(sections, repo_context)
    stack = _stack_summary(components)

    print("\n  Identifying workstreams...\n")
    raw = _stream_text(
        WS_RECOMMEND_PROMPT.format(
            summary=summary, stack=stack, count_instruction=count_instruction
        ),
    )
    return _parse_workstreams(raw)


def confirm_workstreams(ws_list: list[dict]) -> list[dict]:
    """Show recommended workstreams; let user rename, remove, or add."""
    if not ws_list:
        print("  Could not parse workstream recommendations.\n")
        return []

    header("Review Workstreams — confirm, rename, or adjust")
    print("\n  For each workstream: Enter to accept, type a new name to rename, or 'x' to remove.\n")

    confirmed: list[dict] = []
    idx = 1
    for w in ws_list:
        print(f"\n  {w['id']} — {w['name']}")
        print(f"    {w['scope']}")
        choice = input("  [Enter] accept / new name / x to remove: ").strip()
        if choice.lower() == "x":
            print(f"    Removed.")
            continue
        if choice:
            w = {**w, "name": choice}
        w["id"] = f"WS{idx}"
        confirmed.append(w)
        idx += 1

    # Let user add extra workstreams
    while True:
        print(f"\n  Add another workstream? [Enter to finish, or describe it]: ")
        extra = input("  > ").strip()
        if not extra:
            break
        name_raw = input(f"  Codename for this workstream: ").strip() or f"WS{idx}"
        confirmed.append({"id": f"WS{idx}", "name": name_raw, "scope": extra, "tasks": []})
        idx += 1

    return confirmed


def generate_tasks_for_workstream(
    ws: dict,
    sections: dict[str, str],
    components: list[dict],
    all_ws: list[dict],
    repo_context: str | None = None,
) -> list[dict]:
    summary = _project_summary(sections, repo_context)
    stack = _stack_summary(components)
    all_ws_text = _all_ws_summary(all_ws)

    print(f"\n  {hr('·')}")
    print(f"  {ws['id']} — {ws['name']}")
    print(f"  {hr('·')}")
    print(f"  {ws['scope']}\n")
    print("  Generating tasks...\n")

    raw = _stream_text(
        WS_TASKS_PROMPT.format(
            summary=summary,
            stack=stack,
            all_ws=all_ws_text,
            ws_id=ws["id"],
            ws_name=ws["name"],
            ws_scope=ws["scope"],
        ),
        max_tokens=1024,
    )
    tasks = _parse_tasks(raw)

    print(f"\n  Review tasks for {ws['id']} — {ws['name']}:")
    print("  Press Enter to accept list, or type task numbers to remove (e.g. '2 5').\n")
    for i, t in enumerate(tasks, 1):
        blocker_hint = f"  [blocks: {t['blockers']}]" if t["blockers"] != "—" else ""
        print(f"  {i:2}. [{t['priority']}] {t['name']} ({t['estimate']}){blocker_hint}")

    removes = input("\n  Remove tasks (numbers) or Enter to accept: ").strip()
    if removes:
        drop = {int(x) for x in removes.split() if x.isdigit()}
        tasks = [t for i, t in enumerate(tasks, 1) if i not in drop]

    # Allow adding tasks
    while True:
        extra = input("  Add a task (or Enter to finish): ").strip()
        if not extra:
            break
        pri = input("    Priority [P0/P1/P2, default P1]: ").strip() or "P1"
        est = input("    Estimate (e.g. 4h, 1d): ").strip() or "?"
        tasks.append({"name": extra, "priority": pri, "estimate": est, "blockers": "—", "status": "todo"})

    return tasks


def write_plan_md(ws_list: list[dict]) -> None:
    lines: list[str] = [
        "> Generated by planning/plan.py. Edit manually or re-run the planner to regenerate.\n",
        "# Plan\n",
        "## Workstreams\n",
        "| ID | Name | Scope | Status |",
        "|----|------|-------|--------|",
    ]
    for w in ws_list:
        lines.append(f"| {w['id']} | {w['name']} | {w['scope']} | todo |")

    lines.append("")

    for w in ws_list:
        lines.append(f"\n## {w['id']} — {w['name']}\n")
        lines.append(f"**Scope:** {w['scope']}\n")
        lines.append("| Task | Priority | Estimate | Blockers | Status |")
        lines.append("|------|----------|----------|----------|--------|")
        for t in w.get("tasks", []):
            lines.append(
                f"| {t['name']} | {t['priority']} | {t['estimate']} | {t['blockers']} | {t['status']} |"
            )
        lines.append("")

    PLAN_MD.write_text("\n".join(lines))
    print(f"\n  Written to {PLAN_MD}\n")
    commit_to_plan([PLAN_MD], "planning: update PLAN.md")


def plan_workstreams(sections: dict[str, str], components: list[dict], repo_context: str | None = None) -> list[dict]:
    print("\n" + hr("="))
    print("  Step 5: Workstreams")
    print(hr("="))

    _, count_instruction = _get_workstream_count(sections, components)
    ws_list = recommend_workstreams(sections, components, count_instruction, repo_context)
    ws_list = confirm_workstreams(ws_list)

    if not ws_list:
        print("  No workstreams defined. Skipping PLAN.md.\n")
        return []

    print(f"\n  Generating tasks for {len(ws_list)} workstream(s)...\n")
    for ws in ws_list:
        ws["tasks"] = generate_tasks_for_workstream(ws, sections, components, ws_list, repo_context)

    header("Writing PLAN.md")
    write_plan_md(ws_list)
    return ws_list


# ---------------------------------------------------------------------------
# Phase 6 — task manifest with dependency graph → TASKS.md
# ---------------------------------------------------------------------------

TASKS_MD = Path("TASKS.md")

_TASK_MANIFEST_PROMPT_TEMPLATE = """\
You are a senior software architect generating a complete task manifest with a dependency graph.

Project:
{{summary}}

Tech stack:
{{stack}}

Workstreams and their preliminary tasks:
{{ws_tasks}}

Produce an enriched, sequenced task list across ALL workstreams. Order tasks roughly by \
when they can start (blockers first).

Field definitions — every task MUST include every field, even if the value is —:
{field_defs}

Output each task as a block separated by a line containing only ---
Use exactly the field keys shown below. Do not add or omit any fields.

Example task block:
{example}

---

(continue for all tasks)
"""

TASK_MANIFEST_PROMPT = _TASK_MANIFEST_PROMPT_TEMPLATE.format(
    field_defs=field_descriptions(),
    example=prompt_example(),
)


def _ws_tasks_text(ws_list: list[dict]) -> str:
    lines = []
    for w in ws_list:
        lines.append(f"\n{w['id']} — {w['name']}: {w['scope']}")
        for t in w.get("tasks", []):
            lines.append(f"  - [{t['priority']}] {t['name']} ({t['estimate']})")
    return "\n".join(lines)


def _parse_task_blocks(raw: str) -> list[dict]:
    tasks = []
    blocks = re.split(r"\n---\n", raw.strip())
    field_re = re.compile(r"^(\w+):\s*(.*)$")

    for block in blocks:
        task: dict = {}
        for line in block.strip().splitlines():
            m = field_re.match(line.strip())
            if m:
                task[m.group(1).strip()] = m.group(2).strip()
        if "ID" in task and "name" in task:
            tasks.append(enforce_defaults(task))
    return tasks


def _print_task_table(tasks: list[dict]) -> None:
    print(f"\n  {'ID':<6} {'WS':<6} {'Crit':<5} {'Est':<5}  Task")
    print(f"  {hr('─', 58)}")
    for t in tasks:
        ws_short = t.get("workstream", "").split("—")[0].strip()
        human_flag = "  *" if t.get("human", "—") != "—" else ""
        print(f"  {t['ID']:<6} {ws_short:<6} {t.get('criticality',''):<5} {t.get('estimate',''):<5}  {t['name']}{human_flag}")
    print(f"\n  * = requires human action\n")


def write_tasks_md(tasks: list[dict]) -> None:
    p0 = sum(1 for t in tasks if t.get("criticality") == "P0")
    p1 = sum(1 for t in tasks if t.get("criticality") == "P1")
    p2 = sum(1 for t in tasks if t.get("criticality") == "P2")
    human_count = sum(1 for t in tasks if t.get("human", "—") != "—")

    lines: list[str] = [
        "> Generated by planning/plan.py. Edit manually or re-run the planner to regenerate.\n",
        "# Tasks\n",
        "## Summary\n",
        f"**Total:** {len(tasks)}  |  "
        f"**P0:** {p0}  |  **P1:** {p1}  |  **P2:** {p2}  |  "
        f"**Human steps:** {human_count}  |  **Complete:** 0\n",
        "## Index\n",
        "| ID | Workstream | Task | Crit | Est | Status |",
        "|----|-----------|------|------|-----|--------|",
    ]

    for t in tasks:
        ws_short = t.get("workstream", "").split("—")[0].strip()
        lines.append(
            f"| {t['ID']} | {ws_short} | {t['name']} | {t.get('criticality','')} "
            f"| {t.get('estimate','')} | {t.get('status', 'todo')} |"
        )

    lines.append("\n## Task Details\n")

    for t in tasks:
        lines.append(f"### {t['ID']} · {t['name']}\n")
        # Write every field from the schema explicitly
        for f in TASK_FIELDS:
            if f.key in ("ID", "name"):
                continue  # already in the heading
            value = t.get(f.key, f.default or "—")
            if f.key == "human" and value != "—":
                lines.append(f"> **{f.label}:** {value}\n")
            else:
                lines.append(f"**{f.label}:** {value}  ")
        lines.append("")

    TASKS_MD.write_text("\n".join(lines))
    print(f"  Written to {TASKS_MD}\n")
    commit_to_plan([TASKS_MD], "planning: update TASKS.md")


def _timed_call(fn, label: str) -> str:
    """
    Run fn() in a background thread while showing a live elapsed timer so the
    user can see the process is still running. Returns fn()'s return value.
    """
    result: list = [None]
    error: list = [None]
    done = threading.Event()

    def _worker():
        try:
            result[0] = fn()
        except Exception as e:
            error[0] = e
        finally:
            done.set()

    threading.Thread(target=_worker, daemon=True).start()

    spinners = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    start = time.time()
    i = 0
    while not done.wait(0.1):
        elapsed = int(time.time() - start)
        m, s = divmod(elapsed, 60)
        ts = f"{m}:{s:02d}" if m else f"{s}s"
        print(f"\r  {spinners[i % len(spinners)]}  {label}  [{ts}]   ", end="", flush=True)
        i += 1

    elapsed = int(time.time() - start)
    m, s = divmod(elapsed, 60)
    ts = f"{m}:{s:02d}" if m else f"{s}s"
    print(f"\r  ✓  {label}  [{ts}]                    ")

    if error[0]:
        raise error[0]
    return result[0]


def generate_task_manifest(
    sections: dict[str, str], components: list[dict], ws_list: list[dict],
    repo_context: str | None = None,
) -> list[dict] | None:
    print("\n" + hr("="))
    print("  Step 6: Task Manifest")
    print(hr("="))
    print("\n  Building full task graph with dependencies and human requirements...")
    print("  (Claude reasons across all workstreams — typically takes 1–3 minutes)\n")

    summary = _project_summary(sections, repo_context)
    stack = _stack_summary(components)
    ws_tasks = _ws_tasks_text(ws_list)

    raw = _timed_call(
        lambda: call_claude(
            TASK_MANIFEST_PROMPT.format(summary=summary, stack=stack, ws_tasks=ws_tasks),
            max_tokens=4096,
            print_output=False,
        ),
        "Generating task manifest",
    )

    tasks = _parse_task_blocks(raw)
    if not tasks:
        print("  Could not parse task manifest. Check plan.py output above.\n")
        return

    _print_task_table(tasks)

    print("  Review the task list above.")
    print("  Enter task IDs to remove (e.g. 'T004 T009'), or Enter to accept all.\n")
    removes_raw = input("  > ").strip().upper()
    if removes_raw:
        drop = set(removes_raw.split())
        tasks = [t for t in tasks if t["ID"] not in drop]
        # Re-sequence IDs and patch cross-references
        for i, t in enumerate(tasks, 1):
            old_id = t["ID"]
            new_id = f"T{i:03d}"
            if old_id != new_id:
                for other in tasks:
                    for f in ("depends", "unlocks"):
                        if other.get(f):
                            other[f] = other[f].replace(old_id, new_id)
                t["ID"] = new_id

    # Per-task review of key fields
    tasks = _review_tasks(tasks)

    # Catch any still-blank required fields
    tasks = _validate_and_fix(tasks)

    header("Writing TASKS.md")
    write_tasks_md(tasks)
    return tasks


_REVIEW_FIELDS = [
    ("estimate",    "Time Estimate",       "How long will this realistically take?"),
    ("depends",     "Depends On",          "Task IDs this cannot start until they are done (space-separated)"),
    ("unlocks",     "Unlocks / Blocks",    "Task IDs that are unblocked when this is done (space-separated)"),
    ("acceptance",  "Success Criteria",    "Observable, specific definition of done"),
    ("tricky",      "Risks & Focus Areas", "What is subtle, likely to go wrong, or easy to miss when verifying?"),
    ("human",       "Human Required",      "Anything that requires a human — API keys, billing, OAuth consent, etc. '—' if none"),
]


def _review_tasks(tasks: list[dict]) -> list[dict]:
    """
    Walk through each task and let the user review/amend the six key fields.
    Claude's generated values are shown as defaults — Enter accepts, any text overrides.
    """
    print(f"\n  {hr('=')}")
    print("  Task Review — verify each task's key fields")
    print(f"  {hr('=')}")
    print(f"\n  {len(tasks)} task(s) to review.")
    print("  For each field: press Enter to accept Claude's value, or type to override.\n")

    ans = input("  Review tasks now? [Y/n]: ").strip().lower()
    if ans == "n":
        print("  Skipped — using Claude's generated values.\n")
        return tasks

    for i, task in enumerate(tasks, 1):
        print(f"\n  {hr('─')}")
        ws_short = task.get("workstream", "").split("—")[0].strip()
        print(f"  [{i}/{len(tasks)}]  {task['ID']}  ·  {task.get('name', '')}  [{ws_short}]")
        print(f"  {hr('─')}")

        for key, label, description in _REVIEW_FIELDS:
            current = task.get(key, "—") or "—"
            print(f"\n  {label}")
            print(f"  {description}")
            print(f"  Current: {current}")
            val = input("  > ").strip()
            if val:
                task[key] = val

    print(f"\n  Review complete.\n")
    return tasks


def _validate_and_fix(tasks: list[dict]) -> list[dict]:
    """
    Check every required field is non-blank. For any blank required fields,
    show the user the task and prompt them to fill it in or confirm "" explicitly.
    """
    issues = validate_all(tasks)
    if not issues:
        return tasks

    print(f"\n  {len(issues)} task(s) have blank required fields.\n")
    print("  For each: type a value to fill it in, or press Enter to leave as \"\".\n")

    task_map = {t["ID"]: t for t in tasks}
    for tid, errors in issues.items():
        t = task_map[tid]
        print(f"  {hr('·')}")
        print(f"  {tid} — {t.get('name', '')}")
        for err in errors:
            # err is like "  ID (label) is required but blank"
            # Extract the field key
            key_m = re.match(r"\s*(\w+)\s+\(", err)
            if not key_m:
                continue
            key = key_m.group(1)
            f = next((x for x in TASK_FIELDS if x.key == key), None)
            if not f:
                continue
            print(f"\n    {f.label}: {f.description}")
            val = input(f"    Value (Enter = \"\"): ").strip()
            t[key] = val  # may be "" — that is explicit and allowed

    return tasks


# ---------------------------------------------------------------------------
# Phase 7 — push tasks to BEADS
# ---------------------------------------------------------------------------

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


def push_to_beads(tasks: list[dict]) -> None:
    # Verify bd is installed
    probe = _bd("--version")
    if probe.returncode != 0:
        print("  bd not found — install BEADS: https://github.com/gastownhall/beads")
        print("  Skipping BEADS integration.\n")
        return

    # Init if needed
    if not Path(".beads").exists():
        print("  Initializing BEADS...\n")
        _bd("init", check=True)

    print(f"\n  Creating {len(tasks)} task(s) in BEADS...\n")

    id_map: dict[str, str] = {}  # T001 → bd-xxxx

    # Phase A: create all tasks
    for t in tasks:
        tid = t.get("ID", "")
        name = t.get("name", "")
        ws = t.get("workstream", "")
        human = t.get("human", "—")
        notes = t.get("notes", "—")

        desc_parts = [f"Workstream: {ws}"]
        if human != "—":
            desc_parts.append(f"\nHuman required: {human}")
        if notes != "—":
            desc_parts.append(f"\nNotes: {notes}")

        cmd = [
            "create", f"{tid} — {name}",
            "-p", str(_priority_int(t.get("criticality", "P1"))),
            "-t", "task",
            "-d", "\n".join(desc_parts),
            "--json",
        ]
        mins = _estimate_minutes(t.get("estimate", ""))
        if mins:
            cmd += ["--estimate", str(mins)]

        result = _bd(*cmd)
        if result.returncode == 0:
            try:
                bd_id = json.loads(result.stdout).get("id", "")
                id_map[tid] = bd_id
                print(f"  {tid} → {bd_id}  {name}")
            except (json.JSONDecodeError, AttributeError):
                print(f"  {tid}  WARNING: could not parse bd output")
        else:
            print(f"  {tid}  ERROR: {result.stderr.strip()}")

    # Phase B: link dependencies
    print("\n  Linking dependencies...\n")
    for t in tasks:
        tid = t.get("ID", "")
        child_bd = id_map.get(tid)
        if not child_bd:
            continue
        depends_str = t.get("depends", "—")
        if not depends_str or depends_str == "—":
            continue
        for dep_tid in [d.strip() for d in depends_str.split(",") if d.strip()]:
            parent_bd = id_map.get(dep_tid)
            if not parent_bd:
                continue
            r = _bd("dep", "add", child_bd, parent_bd, "--type", "blocks")
            status = "ok" if r.returncode == 0 else f"ERROR: {r.stderr.strip()}"
            print(f"  {dep_tid} blocks {tid}  [{status}]")

    BEADS_MAP_FILE.write_text(json.dumps(id_map, indent=2))
    print(f"\n  ID mapping saved to {BEADS_MAP_FILE}")

    # Commit issues.jsonl (BEADS export) + .beads_map.json to the plan branch
    # issues.jsonl is auto-written by BEADS after each write operation
    issues_jsonl = Path("issues.jsonl")
    to_commit = [f for f in [BEADS_MAP_FILE, issues_jsonl] if f.exists()]
    if to_commit:
        commit_to_plan(to_commit, "planning: update BEADS task export")
        print(f"  Committed to plan branch: {', '.join(f.name for f in to_commit)}\n")


def push_to_beads_phase(tasks: list[dict]) -> None:
    print("\n" + hr("="))
    print("  Step 7: Push to BEADS")
    print(hr("="))
    print("\n  Push tasks to BEADS for agent-ready task management?")
    print("  Requires `bd` CLI — https://github.com/gastownhall/beads")
    ans = input("\n  [Y/n]: ").strip().lower()
    if ans == "n":
        print("  Skipped. Run `bd init && python planning/render.py` later to set up.\n")
        return
    push_to_beads(tasks)


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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        ensure_gitignore()
        ensure_plan_branch()

        state = _load_state()

        project_type = select_project_type()
        if "repo_context" in state:
            print("  (Resuming — reusing saved repo context)\n")
            repo_context: str | None = state["repo_context"]
        else:
            repo_context = existing_repo_context()
            state["repo_context"] = repo_context
            _save_state(state)

        if project_type:
            repo_context = f"Project type decision:\n{project_type}\n\n{repo_context or ''}".strip() or None

        sections = collect_project_info()

        # Phase 2: tech stack
        if "confirmed_components" in state:
            print("  (Resuming — reusing saved tech stack)\n")
            confirmed: list[dict] | None = state["confirmed_components"]
        else:
            raw_recs = stream_recommendations(sections, repo_context)
            confirmed = confirm_tech_stack(raw_recs)
            state["confirmed_components"] = confirmed
            _save_state(state)

        if not confirmed:
            print("  Skipping ARCHITECTURE.md generation.\n")
        else:
            # Phase 3: architecture
            if state.get("architecture_done"):
                print("  (Resuming — ARCHITECTURE.md already generated)\n")
            else:
                write_architecture(sections, confirmed, repo_context)
                state["architecture_done"] = True
                _save_state(state)

            # Phase 3b: interface review
            if state.get("interface_review_done"):
                print("  (Resuming — interface review already complete)\n")
            else:
                review_interfaces()
                state["interface_review_done"] = True
                _save_state(state)

            # Phase 4: reiterate
            if state.get("reiterate_done"):
                print("  (Resuming — reiterate already complete)\n")
            else:
                reiterate(sections, confirmed)
                state["reiterate_done"] = True
                _save_state(state)

            # Phase 5: workstreams
            if state.get("workstreams_done"):
                print("  (Resuming — workstreams already planned)\n")
                ws_list: list[dict] = state.get("ws_list", [])
            else:
                ws_list = plan_workstreams(sections, confirmed, repo_context)
                state["workstreams_done"] = True
                state["ws_list"] = ws_list
                _save_state(state)

            # Phase 6: task manifest
            if ws_list:
                if state.get("tasks_done"):
                    print("  (Resuming — task manifest already generated)\n")
                else:
                    tasks = generate_task_manifest(sections, confirmed, ws_list, repo_context)
                    if tasks:
                        state["tasks_done"] = True
                        _save_state(state)
                        push_to_beads_phase(tasks)

        # All done — remove state file
        if _STATE_FILE.exists():
            _STATE_FILE.unlink()

        print(hr("="))
        print("  Done! Next steps:")
        print("  1. Review PROJECT.md, ARCHITECTURE.md, PLAN.md, and TASKS.md")
        print("  2. Run start.py to claim a workstream")
        print("  3. Pick your first P0 task from TASKS.md — update status in BEADS as you go")
        print("  4. Run execute/render.py to open the live flowchart in the browser")
        print(hr("=") + "\n")

    except KeyboardInterrupt:
        print("\n\n  Interrupted. Progress saved — re-run plan.py to resume.\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
