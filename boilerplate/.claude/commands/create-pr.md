Create a pull request for the current branch. Follow these steps carefully:

## 1. Gather state

Run in parallel:
- `git status` — check for uncommitted changes
- `git log main..HEAD --oneline` — list commits since main
- `git diff main...HEAD --stat` — changed files summary

If there are uncommitted changes, ask the user whether to commit them first before proceeding.

## 2. Detect UI changes

Check if any changed files are in a frontend directory (common patterns: `src/`, `render/src/`, `*.tsx`, `*.css`, `*.html`).

If UI files changed:
- Start the dev server (e.g. `npm run dev` inside `render/`) in the background
- Use Playwright to capture before/after screenshots:
  - **Before**: check out `main` in a temp worktree, screenshot the relevant pages
  - **After**: screenshot the same pages on the current branch
- Include the screenshot paths in the PR body as image references or describe what changed visually
- Stop the dev server after capturing

## 3. Commit planning docs to plan branch

Run:
```
python - <<'EOF'
import sys
from pathlib import Path
sys.path.insert(0, 'planning')
from git_plan import commit_to_plan, PLANNING_DOCS
files = [Path(f) for f in PLANNING_DOCS if Path(f).exists()]
if files:
    commit_to_plan(files, "chore: sync planning docs pre-PR")
    print("Planning docs committed to plan branch.")
else:
    print("No planning docs to commit.")
EOF
```

## 4. Push the current branch

Run: `git push -u origin HEAD`

If push fails due to no remote or other error, report it and stop.

## 5. Draft the PR

Analyze all commits since `main` and all changed files. Write a PR with:
- **Title**: concise, under 70 chars, verb-first (Add / Fix / Update / Refactor)
- **Summary**: 2-4 bullets on *what* changed and *why*
- **UI changes** (if applicable): describe visual differences; reference screenshot paths if captured
- **Test plan**: bulleted checklist of how to verify the changes

Create the PR:
```
gh pr create --title "<title>" --body "$(cat <<'BODY'
## Summary
<bullets>

## UI Changes
<visual diff or "No UI changes">

## Test plan
<checklist>

🤖 Generated with [Claude Code](https://claude.com/claude-code)
BODY
)"
```

## 6. Report back

Print the PR URL and a one-line summary of what was included.
