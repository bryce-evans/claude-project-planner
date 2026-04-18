Run `planning/git_plan.py`'s `pull_all()` to bring the working directory fully up to date:

## 1. Snapshot current state

Before pulling, capture the current HEAD and any in-progress work:
- `git log --oneline -5` — note current branch tip
- `git stash list` — note any existing stashes

## 2. Run pull-all

```
python - <<'EOF'
import sys
sys.path.insert(0, 'planning')
from git_plan import pull_all
pull_all(verbose=True)
EOF
```

## 3. Handle merge conflicts

If step 2 produces merge conflicts:

1. **Do not blindly accept either side.** Read the conflicting files in full.
2. Consult `git log --merge --oneline` and `git diff --merge` to understand what each branch changed and why.
3. Cross-reference `TASKS.md` and `PLAN.md` (including the `plan` branch version via `git show plan:TASKS.md`) to ensure no task, dependency, acceptance criterion, or verification step is lost in the merge.
4. Resolve each conflict by preserving all functionality from both sides — combine rather than choose. If the changes are genuinely incompatible, pause and explain the conflict to the user before resolving.
5. After resolving, run `git add <files>` and `git merge --continue` (or `git rebase --continue`).

## 4. Report

- What was fetched / merged / synced, noting any failures.
- If planning docs changed (PROJECT.md, ARCHITECTURE.md, PLAN.md, TASKS.md), summarize the diff so the user knows what updated.
- If conflicts were resolved, describe each one and confirm no functionality was lost.
