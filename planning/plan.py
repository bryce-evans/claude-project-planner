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
from pathlib import Path

import anthropic

MODEL = "claude-sonnet-4-6"

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
        if line == "" and lines:
            break
        if line != "":
            lines.append(line)

    return "\n".join(lines)


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
    else:
        print("\n  No PROJECT.md found — starting fresh.")

    for key, title, question in SECTIONS:
        sections[key] = prompt_section(key, title, question, existing.get(key))
        save_project_md(sections)

    return sections


# ---------------------------------------------------------------------------
# Phase 2 — tech stack recommendations
# ---------------------------------------------------------------------------

def _project_summary(sections: dict[str, str]) -> str:
    return "\n".join(
        f"**{title}:** {sections.get(key, 'N/A')}"
        for key, title, _ in SECTIONS
    )


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


def stream_recommendations(sections: dict[str, str]) -> str:
    client = anthropic.Anthropic()
    summary = _project_summary(sections)

    print("\n" + hr("="))
    print("  Step 2: Tech Stack Recommendations")
    print(hr("="))
    print("\n  Analyzing your project...\n")

    full = ""
    with client.messages.stream(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": TECH_STACK_PROMPT.format(summary=summary)}],
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)
            full += text

    print("\n")
    return full


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


def write_architecture(sections: dict[str, str], components: list[dict]) -> None:
    client = anthropic.Anthropic()
    summary = _project_summary(sections)
    stack = "\n".join(
        f"- **{c['name']}**: {c['tech']} — {c['rationale']}" for c in components
    )

    header("Generating ARCHITECTURE.md")
    print()

    content = ""
    with client.messages.stream(
        model=MODEL,
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": ARCH_PROMPT.format(summary=summary, stack=stack),
            }
        ],
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)
            content += text

    ARCHITECTURE_MD.write_text(content)
    print(f"\n\n  Written to {ARCHITECTURE_MD}\n")


# ---------------------------------------------------------------------------
# Phase 4 — re-iterate: gaps, alternatives, clarifications
# ---------------------------------------------------------------------------

REITERATE_PROMPT = """\
You are a senior software architect reviewing a completed project definition and tech stack.

Project definition:
{summary}

Agreed tech stack:
{stack}

Generate a short list of observations in three categories:

- GAP: something the user hasn't considered that could bite them — missing requirements, \
operational concerns, security, scaling, edge cases.
- ALTERNATIVE: a place where their tech or design choice has a meaningful trade-off worth \
reconsidering, with a specific suggestion.
- CLARIFY: a question where understanding their reasoning would sharpen the plan.

Rules:
- Be specific. "Have you considered auth?" is too vague. Instead: "You mentioned user accounts \
but didn't specify social login vs email+password — this changes your auth library choice."
- 4–7 items total. Quality over quantity. Only raise things that genuinely matter for this project.
- Do not repeat anything already well-covered in the project definition.
- Format exactly — one item per line, no blank lines between items, no extra text:

[GAP] observation
[ALTERNATIVE] observation
[CLARIFY] question
"""

ITEM_LABELS = {
    "GAP": ("Gap", "Something you may not have considered"),
    "ALTERNATIVE": ("Alternative", "Another approach worth weighing"),
    "CLARIFY": ("Clarify", "A question about your reasoning"),
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
    """Append a Clarifications section to PROJECT.md with Q&A pairs."""
    existing = PROJECT_MD.read_text() if PROJECT_MD.exists() else ""

    # Remove old clarifications block if present
    existing = re.sub(r"\n## Clarifications\n[\s\S]*$", "", existing).rstrip()

    block = "\n\n## Clarifications\n\n"
    for e in entries:
        label, _ = ITEM_LABELS[e["tag"]][:2]
        block += f"**[{label}]** {e['text']}\n\n"
        block += f"> {e['response']}\n\n"

    PROJECT_MD.write_text(existing + block)


def reiterate(sections: dict[str, str], components: list[dict]) -> None:
    client = anthropic.Anthropic()
    summary = _project_summary(sections)
    stack = _stack_summary(components)

    print("\n" + hr("="))
    print("  Step 4: Re-iterate — Gaps, Alternatives & Clarifications")
    print(hr("="))
    print("\n  Reviewing your plan for things worth reconsidering...\n")

    raw = ""
    with client.messages.stream(
        model=MODEL,
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": REITERATE_PROMPT.format(summary=summary, stack=stack),
            }
        ],
    ) as stream:
        for text in stream.text_stream:
            raw += text

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


def _stream_text(client: anthropic.Anthropic, prompt: str, max_tokens: int = 1024) -> str:
    full = ""
    with client.messages.stream(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)
            full += text
    print()
    return full


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
    sections: dict[str, str], components: list[dict], count_instruction: str
) -> list[dict]:
    client = anthropic.Anthropic()
    summary = _project_summary(sections)
    stack = _stack_summary(components)

    print("\n  Identifying workstreams...\n")
    raw = _stream_text(
        client,
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
) -> list[dict]:
    client = anthropic.Anthropic()
    summary = _project_summary(sections)
    stack = _stack_summary(components)
    all_ws_text = _all_ws_summary(all_ws)

    print(f"\n  {hr('·')}")
    print(f"  {ws['id']} — {ws['name']}")
    print(f"  {hr('·')}")
    print(f"  {ws['scope']}\n")
    print("  Generating tasks...\n")

    raw = _stream_text(
        client,
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


def plan_workstreams(sections: dict[str, str], components: list[dict]) -> list[dict]:
    print("\n" + hr("="))
    print("  Step 5: Workstreams")
    print(hr("="))

    _, count_instruction = _get_workstream_count(sections, components)
    ws_list = recommend_workstreams(sections, components, count_instruction)
    ws_list = confirm_workstreams(ws_list)

    if not ws_list:
        print("  No workstreams defined. Skipping PLAN.md.\n")
        return []

    print(f"\n  Generating tasks for {len(ws_list)} workstream(s)...\n")
    for ws in ws_list:
        ws["tasks"] = generate_tasks_for_workstream(ws, sections, components, ws_list)

    header("Writing PLAN.md")
    write_plan_md(ws_list)
    return ws_list


# ---------------------------------------------------------------------------
# Phase 6 — task manifest with dependency graph → TASKS.md
# ---------------------------------------------------------------------------

TASKS_MD = Path("TASKS.md")

TASK_MANIFEST_PROMPT = """\
You are a senior software architect generating a complete task manifest with a dependency graph.

Project:
{summary}

Tech stack:
{stack}

Workstreams and their preliminary tasks:
{ws_tasks}

Produce an enriched, sequenced task list across all workstreams.

Rules:
- Assign sequential IDs: T001, T002, ... ordered roughly by when they can start.
- Identify cross-workstream dependencies — e.g. an auth setup task blocking a \
frontend protected-route task.
- depends: IDs of tasks that must be complete before this one can start (or — if none).
- unlocks: IDs of tasks that become unblocked once this one is done (or — if none).
- criticality: P0 = project blocked without it / P1 = required for launch / P2 = polish.
- estimate: 2h / 4h / 1d / 2d / 1w.
- human: anything a human must do manually — set API key, approve billing, click OAuth \
consent, register a domain, fill .env, etc. Write — if fully automatable.
- notes: any important implementation detail, gotcha, or sequencing note. Write — if none.

Output each task as a block, separated by a line containing only ---

ID: T001
workstream: WS1 — Keymaster
name: Register OAuth application with provider
criticality: P0
estimate: 2h
depends: —
unlocks: T002, T007
human: Go to Google Cloud Console → create OAuth 2.0 credentials → copy client ID and secret to .env
notes: Approval can take up to 24h if consent screen is flagged for review

---

ID: T002
...
"""


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
    field = re.compile(r"^(\w+):\s*(.*)$")

    for block in blocks:
        task: dict = {}
        for line in block.strip().splitlines():
            m = field.match(line.strip())
            if m:
                task[m.group(1).strip()] = m.group(2).strip()
        if "ID" in task and "name" in task:
            tasks.append(task)
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
            f"| {t.get('estimate','')} | todo |"
        )

    lines.append("\n## Task Details\n")

    for t in tasks:
        lines += [
            f"### {t['ID']} · {t['name']}\n",
            f"**Workstream:** {t.get('workstream', '—')}  ",
            f"**Criticality:** {t.get('criticality', '—')}  ",
            f"**Estimate:** {t.get('estimate', '—')}  ",
            f"**Status:** todo\n",
            f"**Depends on:** {t.get('depends', '—')}  ",
            f"**Unlocks:** {t.get('unlocks', '—')}\n",
        ]
        human = t.get("human", "—")
        if human != "—":
            lines.append(f"> **Human required:** {human}\n")
        notes = t.get("notes", "—")
        if notes != "—":
            lines.append(f"**Notes:** {notes}\n")
        lines.append("")

    TASKS_MD.write_text("\n".join(lines))
    print(f"  Written to {TASKS_MD}\n")


def generate_task_manifest(
    sections: dict[str, str], components: list[dict], ws_list: list[dict]
) -> None:
    client = anthropic.Anthropic()

    print("\n" + hr("="))
    print("  Step 6: Task Manifest")
    print(hr("="))
    print("\n  Building full task graph with dependencies and human requirements...\n")

    summary = _project_summary(sections)
    stack = _stack_summary(components)
    ws_tasks = _ws_tasks_text(ws_list)

    raw = ""
    with client.messages.stream(
        model=MODEL,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": TASK_MANIFEST_PROMPT.format(
                    summary=summary, stack=stack, ws_tasks=ws_tasks
                ),
            }
        ],
    ) as stream:
        for text in stream.text_stream:
            raw += text

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
        # Re-sequence IDs
        for i, t in enumerate(tasks, 1):
            old_id = t["ID"]
            new_id = f"T{i:03d}"
            if old_id != new_id:
                for other in tasks:
                    for field in ("depends", "unlocks"):
                        if other.get(field):
                            other[field] = other[field].replace(old_id, new_id)
                t["ID"] = new_id

    header("Writing TASKS.md")
    write_tasks_md(tasks)
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
    print(f"\n  ID mapping saved to {BEADS_MAP_FILE}\n")


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
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        sections = collect_project_info()
        print(f"\n  PROJECT.md saved.\n")

        raw_recs = stream_recommendations(sections)
        confirmed = confirm_tech_stack(raw_recs)

        if confirmed:
            write_architecture(sections, confirmed)
            reiterate(sections, confirmed)
            ws_list = plan_workstreams(sections, confirmed)
            if ws_list:
                tasks = generate_task_manifest(sections, confirmed, ws_list)
                if tasks:
                    push_to_beads_phase(tasks)
        else:
            print("  Skipping ARCHITECTURE.md generation.\n")

        print(hr("="))
        print("  Done! Next steps:")
        print("  1. Review PROJECT.md, ARCHITECTURE.md, PLAN.md, and TASKS.md")
        print("  2. Run start.py to claim a workstream")
        print("  3. Pick your first P0 task from TASKS.md — update status in BEADS as you go")
        print("  4. Run render.py to open the live flowchart in the browser")
        print(hr("=") + "\n")

    except KeyboardInterrupt:
        print("\n\n  Interrupted. Progress saved to PROJECT.md.\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
