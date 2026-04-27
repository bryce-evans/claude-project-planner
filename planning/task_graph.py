"""Phase 6b: structural verification of the task dependency graph."""

import re

from claude_runner import call_claude_cli as call_claude
from ui import hr, timed_call
from schema import TASK_FIELDS, enforce_defaults


_SENSITIVE_KEYWORDS = re.compile(
    r"\b(secret|api.?key|credential|token|password|billing|payment|invoice|"
    r"provision|cloud.?account|subscription|oauth|app.?store|domain|dns|"
    r"ssl|certificate|auth|firewall|vpn|hardware|server|deploy|hosting|"
    r"sendgrid|stripe|twilio|aws|gcp|azure|heroku|vercel|fly\.io|"
    r"openai|anthropic|dashboard)\b",
    re.IGNORECASE,
)

_CODE_ONLY_KEYWORDS = re.compile(
    r"\b(implement|write|build|create|add|refactor|migrate|update|fix|test|"
    r"parse|render|display|calculate|connect|integrate|wire|handle|define|"
    r"configure|setup|scaffold|stub|mock|lint|format)\b",
    re.IGNORECASE,
)

_INTEGRATION_KEYWORDS = re.compile(
    r"\b(integrat|end.?to.?end|e2e|mvp|demo|final|launch|ship|release|"
    r"smoke.?test|test.?all|everything|full.?stack)\b",
    re.IGNORECASE,
)


def _task_label(t: dict) -> str:
    return f"{t['ID']} — {t.get('name', '')}"


def parse_task_blocks(raw: str) -> list[dict]:
    """Parse Claude's block-format task output into a list of task dicts."""
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


def depends_on_ids(t: dict, tasks: list[dict]) -> set[str]:
    ids = {x["ID"] for x in tasks}
    raw = t.get("depends", "")
    return {x.strip() for x in re.split(r"[,\s]+", raw) if re.match(r"T\d+", x.strip())} & ids


def _verify_task_graph(tasks: list[dict]) -> list[str]:
    issues: list[str] = []
    ids = {t["ID"] for t in tasks}

    depends_on: dict[str, set[str]] = {}
    for t in tasks:
        raw_dep = t.get("depends", "")
        deps = {x.strip() for x in re.split(r"[,\s]+", raw_dep) if re.match(r"T\d+", x.strip())}
        depends_on[t["ID"]] = deps & ids

    raw_unlocks_map: dict[str, set[str]] = {}
    for t in tasks:
        raw_ul = t.get("unlocks", "")
        uls = {x.strip() for x in re.split(r"[,\s]+", raw_ul) if re.match(r"T\d+", x.strip())}
        raw_unlocks_map[t["ID"]] = uls & ids

    needed_by: set[str] = set()
    for t in tasks:
        needed_by |= depends_on[t["ID"]]

    # Check 1: sensitive tasks should be human-required
    for t in tasks:
        name = t.get("name", "")
        human = (t.get("human") or "").strip()
        if _SENSITIVE_KEYWORDS.search(name) and not human:
            issues.append(
                f"[HUMAN-MISSING]  {_task_label(t)}\n"
                f"    Task name suggests secrets/auth/billing but Human Required is blank."
            )

    # Check 2: clearly code-only tasks should NOT be human-required
    for t in tasks:
        name = t.get("name", "")
        human = (t.get("human") or "").strip()
        if human and _CODE_ONLY_KEYWORDS.search(name) and not _SENSITIVE_KEYWORDS.search(name):
            issues.append(
                f"[HUMAN-SPURIOUS] {_task_label(t)}\n"
                f"    Marked human-required but looks like a pure code task — verify this is intentional.\n"
                f"    Human Required: {human[:120]}"
            )

    # Check 3: every task should unlock something or be depended-on, or be the sink
    integration_tasks = {t["ID"] for t in tasks if _INTEGRATION_KEYWORDS.search(t.get("name", ""))}
    for t in tasks:
        tid = t["ID"]
        depended_on = tid in needed_by
        declares_unlocks = bool(raw_unlocks_map[tid])
        is_sink = tid in integration_tasks
        if not depended_on and not declares_unlocks and not is_sink:
            issues.append(
                f"[ORPHAN-LEAF]    {_task_label(t)}\n"
                f"    Nothing depends on this task and it unlocks nothing — it may be disconnected from the graph."
            )

    if not integration_tasks:
        issues.append(
            "[NO-SINK]        No task with integration/MVP/demo language found.\n"
            "    Consider adding a final 'Integrate & demo MVP' task that depends on all workstream outputs."
        )

    return issues


_VERIFY_FIX_PROMPT = """\
You are reviewing a task manifest for structural correctness. Below are the issues found:

{issues}

Here is the full current task list:

{task_blocks}

Fix ALL issues by returning the corrected task list in the same block format (fields separated by \
newlines, tasks separated by ---). Apply minimal changes — only fix what is flagged.
Do NOT add or remove tasks unless absolutely necessary to resolve a [NO-SINK] issue.
For [HUMAN-MISSING]: add a concise Human Required line describing what must be done manually.
For [HUMAN-SPURIOUS]: clear the human field if the task is truly automatable.
For [ORPHAN-LEAF]: add the task ID to a downstream task's depends field, or add a missing unlocks entry.
For [NO-SINK]: add a new final integration task (T999 placeholder — it will be renumbered).
"""


def _tasks_to_block_text(tasks: list[dict]) -> str:
    lines = []
    field_keys = [f.key for f in TASK_FIELDS]
    for t in tasks:
        lines.append(f"ID: {t['ID']}")
        lines.append(f"name: {t.get('name', '')}")
        for k in field_keys:
            if k not in ("ID", "name"):
                lines.append(f"{k}: {t.get(k, '')}")
        lines.append("---")
    return "\n".join(lines)


def verify_task_graph(tasks: list[dict]) -> list[dict]:
    """Show structural issues and offer a Claude auto-fix pass. Returns corrected task list."""
    print(f"\n  {hr('=')}")
    print("  Step 6b: Task Graph Verification")
    print(f"  {hr('=')}\n")

    issues = _verify_task_graph(tasks)

    root_tasks = [t for t in tasks if not depends_on_ids(t, tasks)]
    print(f"  Root tasks (can start immediately): {len(root_tasks)}")
    for t in root_tasks:
        print(f"    {_task_label(t)}")

    if not issues:
        print("\n  ✓ No structural issues found — task graph looks good.\n")
        return tasks

    print(f"\n  {len(issues)} issue(s) found:\n")
    for iss in issues:
        for line in iss.splitlines():
            print(f"    {line}")
        print()

    ans = input("  Auto-fix with Claude? [Y/n]: ").strip().lower()
    if ans in ("n", "no"):
        print("  Skipping auto-fix — issues remain.\n")
        return tasks

    print()
    raw = timed_call(
        lambda: call_claude(
            _VERIFY_FIX_PROMPT.format(
                issues="\n".join(issues),
                task_blocks=_tasks_to_block_text(tasks),
            ),
            max_tokens=4096,
            print_output=False,
        ),
        "Auto-fixing task graph",
    )

    fixed = parse_task_blocks(raw)
    if not fixed:
        print("  Could not parse Claude's corrections — keeping original tasks.\n")
        return tasks

    for i, t in enumerate(fixed, 1):
        t["ID"] = f"T{i:03d}"

    print(f"\n  Fixed task list has {len(fixed)} task(s).\n")
    second_pass = _verify_task_graph(fixed)
    if second_pass:
        print(f"  {len(second_pass)} issue(s) remain after fix — review manually:\n")
        for iss in second_pass:
            for line in iss.splitlines():
                print(f"    {line}")
            print()
    else:
        print("  ✓ All issues resolved.\n")

    return fixed
