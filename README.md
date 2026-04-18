# Claude Project Planner

A toolkit for spinning up well-structured projects fast and keeping execution visible.

## Components

| Component | Status | Description |
|-----------|--------|-------------|
| **boilerplate** | done | Template files to copy into a new project |
| **planning** | in progress | Interactive CLI: define your project, pick a tech stack, generate ARCHITECTURE.md |
| **render** | planned | Live browser flowchart of tasks, workstreams, and agent progress |

## Quickstart

```sh
PLANNER=path/to/claude-project-planner
pip install -r $PLANNER/planning/requirements.txt
```

### 1. Setup — copy boilerplate

```sh
cd /your/new/project
python $PLANNER/planning/setup.py
```

Copies `PROJECT.md`, `PLAN.md`, `ARCHITECTURE.md`, `STYLE.md`, `CLAUDE.md`, `WORKSTREAM.md` into your project root.

### 2. Identify yourself

```sh
python $PLANNER/planning/start.py
```

Asks for your name, whether you're a human or AI agent, and which workstream you're owning. Writes `WORKSTREAM.md` — Claude reads this before every action so it knows its role and scope.

Re-run this at the start of each session, or whenever ownership changes.

### 3. Plan the project

```sh
python $PLANNER/planning/plan.py
```

Walks you through:
1. Filling in `PROJECT.md` (motivation, goals, success criteria, etc.)
2. Tech stack recommendations — confirm or override per component
3. Re-iteration — gaps, alternatives, clarifying questions
4. Workstream definition — count, codenames, scope
5. Task breakdown per workstream → writes `PLAN.md` and `ARCHITECTURE.md`

### 4. Start working

- Pick a task from your workstream in `PLAN.md`
- Update **Current Task** in `WORKSTREAM.md`
- Mark the task `in-progress`, then `done` when finished

## Boilerplate files

| File | Purpose |
|------|---------|
| `PROJECT.md` | High-level project definition (motivation, goals, success criteria) |
| `PLAN.md` | Task list organized by workstream, with priorities and blockers |
| `ARCHITECTURE.md` | Component map, tech stack, directory layout, interfaces |
| `STYLE.md` | Linting tools, code style rules |
| `CLAUDE.md` | Instructions for Claude — points to the above docs |

## Docs

- [ARCHITECTURE.md](ARCHITECTURE.md) — how this repo itself is structured
- [STYLE.md](STYLE.md) — code style and linting (TBD once stack is chosen)
