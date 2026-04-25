Find the next actionable task and execute it. Do not stop until the task is done or there is a concrete, named blocker.

## 1. Load context

Read these files (all required — if any are missing, stop and tell the user which one and how to fix it):
- `WORKSTREAM.md` — your current workstream ID and responsibilities
- `TASKS.md` — full task manifest with statuses, dependencies, acceptance criteria, verification steps
- `PLAN.md` — workstream definitions and overall scope

## 2. Get live task status from BEADS (if available)

Run:
```
bd list --json 2>/dev/null || echo "BEADS_UNAVAILABLE"
```

If BEADS is available, use its status as the source of truth over TASKS.md (TASKS.md may be stale). Map statuses:
- `closed` → done
- `in_progress` → already being worked
- `open` → available
- `blocked` → not actionable
- `in_review` → needs review, not new work
- `deferred` → skip

If BEADS is unavailable, fall back to the `status` column in TASKS.md.

## 3. Find the next task

Filter to tasks that satisfy ALL of the following:
1. **Workstream matches** — task's `workstream` field matches your workstream from WORKSTREAM.md, OR the task is unassigned and falls within your stated scope
2. **Status is open** — not already in_progress, in_review, blocked, closed, or deferred
3. **Dependencies are satisfied** — every task listed in the `depends` field is closed/done

Among the qualifying tasks, pick the one that unblocks the most downstream work (largest `unlocks` set), then break ties by order in TASKS.md.

**If no task qualifies:**
- If all your tasks are done → report this clearly and stop.
- If tasks exist but all are blocked → list each blocked task and name exactly what it is waiting on. Stop.
- If tasks exist in other workstreams only → name them and explain why you are not picking them up. Stop.

**Do not guess or invent tasks.** Only work from TASKS.md.

## 4. Announce and claim the task

Print a brief summary:
```
→ Starting: [TASK_ID] [task name]
   Workstream: [WS]
   Estimate: [estimate]
   Depends on: [deps or "none"]
   Unlocks: [unlocks or "nothing downstream"]
```

Then:
1. Update `WORKSTREAM.md` — set **Current Task** to this task's ID and name.
2. Mark the task `in_progress` in BEADS: `bd update <beads-id> --status in_progress`
3. If BEADS unavailable, update the `status` field in `TASKS.md` directly.

## 5. Do the work

Read the task's `acceptance` and `verification` fields carefully before writing a single line of code. Also read `tricky` — it describes easy-to-miss gotchas in verification.

Work through the task:
- Make all necessary code changes.
- Run any relevant tests or build steps to confirm they pass.
- Do not stop to ask clarifying questions unless the acceptance criteria are genuinely ambiguous — in that case, state the ambiguity clearly and ask exactly one question.

## 6. Verify completion

Follow the `verification` steps from TASKS.md exactly. These are concrete, executable steps — run them. If a verification step requires human action (e.g. "log in and confirm the UI shows X"), note it explicitly and pause for the user.

Address anything flagged in `tricky` before declaring done.

## 7. Mark done and continue

If verification passes:
1. Mark task closed in BEADS: `bd update <beads-id> --status closed`
2. Update `TASKS.md` status to `done`.
3. Clear **Current Task** in `WORKSTREAM.md`.
4. Commit all changed files (code + TASKS.md + WORKSTREAM.md) in one commit.

**Then immediately loop back to step 3** and pick the next task. Keep working until there is nothing left to do or a concrete blocker forces a stop.

## Stopping conditions (name them explicitly)

Only halt if:
- All workstream tasks are done → "All tasks complete."
- A task is blocked on another workstream → "Blocked: waiting on [TASK_ID] ([other WS]) — [what it needs to deliver]."
- A verification step requires human input → "Paused: [exactly what the human needs to do]."
- A task has genuinely ambiguous acceptance criteria → "Ambiguous: [exact question]."

Never halt silently. Always state the reason.
