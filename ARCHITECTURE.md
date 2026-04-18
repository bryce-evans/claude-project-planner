# Architecture

## Overview

A three-component toolkit: **boilerplate** (template files for new projects), **planning** (interactive CLI that defines a project and its tech stack), and **render** (live browser view of task execution).

## Components

| Component | Directory | Purpose |
|-----------|-----------|---------|
| boilerplate | `boilerplate/` | Template files copied into new projects |
| planning | `planning/` | Interactive CLI: PROJECT.md → tech stack → ARCHITECTURE.md → PLAN.md |
| render | `render/` | Live browser flowchart of tasks, workstreams, and agent progress |

## Component Details

### boilerplate

- **Directory:** `boilerplate/`
- **Contents:** `PROJECT.md`, `PLAN.md`, `ARCHITECTURE.md`, `STYLE.md`, `CLAUDE.md`
- **Scope:** Read-only templates. Copying and parameterizing them is a manual step (no script yet).

### planning

- **Directory:** `planning/`
- **Entry point:** `plan.py` (run from target project root)
- **Scope:** Reads/writes `PROJECT.md` (project definition), streams Claude API to recommend tech stack, writes `ARCHITECTURE.md`. Future: generates `PLAN.md`.
- **Runtime:** Python 3.11+, `anthropic` SDK (`requirements.txt`)
- **Claude model:** `claude-sonnet-4-6`

### render

- **Directory:** `render/`
- **Scope:** _TODO — define data model, update protocol (polling vs push), browser tech stack._

## Interfaces

### planning → PROJECT.md

`plan.py` reads and writes `PROJECT.md` in the **current working directory** (the target project root). Format: `## Section Title\ncontent` blocks.

### planning → ARCHITECTURE.md

`plan.py` writes `ARCHITECTURE.md` in the current working directory after tech stack confirmation.

### planning → PLAN.md

_TODO — not yet implemented._

### render ↔ execution runtime

_TODO — define how render reads task/workstream state._
