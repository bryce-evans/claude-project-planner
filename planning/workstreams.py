"""Phase 5: workstream recommendation, confirmation, task generation, and PLAN.md."""

import re
from pathlib import Path

from git_plan import commit_planning_docs
from claude_runner import call_claude_cli as call_claude
from ui import hr, header
from project_context import _project_summary, _stack_summary


PLAN_MD = Path("PLAN.md")
FUTURE_WORK_MD = Path("FUTURE_WORK.md")


def _future_work_context() -> str:
    if not FUTURE_WORK_MD.exists():
        return ""
    text = FUTURE_WORK_MD.read_text().strip()
    if "None yet" in text or not text:
        return ""
    return f"\nDeferred / out-of-scope items (do NOT include these in the current plan):\n{text}\n"


WS_RECOMMEND_PROMPT = """\
You are a senior software architect dividing project work into parallel workstreams.

Project definition:
{summary}

Tech stack:
{stack}
{future_work}
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
{future_work}
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
            tasks.append({
                "name": parts[0],
                "priority": parts[1],
                "estimate": parts[2],
                "blockers": parts[3],
                "status": "todo",
            })
    return tasks


def _all_ws_summary(ws_list: list[dict]) -> str:
    return "\n".join(f"  {w['id']} — {w['name']}: {w['scope']}" for w in ws_list)


def _get_workstream_count(sections: dict[str, str], components: list[dict]) -> tuple[int | None, str]:
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
    raw = call_claude(
        WS_RECOMMEND_PROMPT.format(
            summary=summary, stack=stack, count_instruction=count_instruction,
            future_work=_future_work_context(),
        ),
    )
    return _parse_workstreams(raw)


def confirm_workstreams(ws_list: list[dict]) -> list[dict]:
    """Show recommended workstreams; let user rename, assign owners, or add."""
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
        owner = input("  Owner (name or email, Enter to leave unassigned): ").strip()
        w["owner"] = owner
        confirmed.append(w)
        idx += 1

    while True:
        print(f"\n  Add another workstream? [Enter to finish, or describe it]: ")
        extra = input("  > ").strip()
        if not extra:
            break
        name_raw = input(f"  Codename for this workstream: ").strip() or f"WS{idx}"
        owner = input("  Owner (name or email, Enter to leave unassigned): ").strip()
        confirmed.append({"id": f"WS{idx}", "name": name_raw, "scope": extra, "owner": owner, "tasks": []})
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

    raw = call_claude(
        WS_TASKS_PROMPT.format(
            summary=summary,
            stack=stack,
            all_ws=all_ws_text,
            future_work=_future_work_context(),
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
        "| ID | Name | Scope | Owner | Status |",
        "|----|------|-------|-------|--------|",
    ]
    for w in ws_list:
        owner = w.get("owner") or ""
        lines.append(f"| {w['id']} | {w['name']} | {w['scope']} | {owner} | todo |")

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
    commit_planning_docs([PLAN_MD], "planning: update PLAN.md")


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
