# Claude Instructions

Before writing any code or taking any action in this repo, read **all** of the following.
If any file is missing, stop and tell the user which one is absent and how to regenerate it.

- [ME.md](ME.md) — who you are: expertise, workflow style, current constraints. If this file is missing, stop and ask the user to run `python path/to/planning/start.py` to regenerate it.
- [WORKSTREAM.md](WORKSTREAM.md) — your current role, workstream, and responsibilities. If missing, same: ask user to run `start.py`.
- [ARCHITECTURE.md](ARCHITECTURE.md) — component boundaries, APIs, interfaces, and scope
- [STYLE.md](STYLE.md) — linting, code style rules, and how to enforce them
- [PLAN.md](PLAN.md) — workstreams, scope, and status
- [TASKS.md](TASKS.md) — full task manifest: dependencies, unlocks, estimates, human requirements
- [FUTURE_WORK.md](FUTURE_WORK.md) — intentionally deferred items. **Read before adding tasks to PLAN.md** to avoid pulling deferred work back into current scope.

When picking up a task:
1. Confirm it belongs to your workstream before starting.
2. Update the **Current Task** field in `WORKSTREAM.md` as you begin.
3. Mark the task `in-progress` in `PLAN.md`.
4. When done, mark it `done` in `PLAN.md` and clear **Current Task** in `WORKSTREAM.md`.
