"""
Canonical task field schema — loaded from task_fields.yaml.

Single source of truth for:
  - What fields every task must have
  - Claude prompt generation
  - Parser defaults and validation
  - TASKS.md writer

Imported by plan.py and execute/render.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SCHEMA_FILE = Path(__file__).parent / "task_fields.yaml"


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    description: str
    example: str
    default: str = ""       # "" means "explicitly blank" — never None
    required: bool = False


def _load() -> list[Field]:
    raw = yaml.safe_load(SCHEMA_FILE.read_text())
    fields = []
    for entry in raw["fields"]:
        fields.append(
            Field(
                key=entry["key"],
                label=entry["label"],
                description=str(entry["description"]).strip(),
                example=str(entry.get("example", "")),
                default=str(entry.get("default", "")),
                required=bool(entry.get("required", False)),
            )
        )
    return fields


TASK_FIELDS: list[Field] = _load()
FIELD_KEYS: list[str] = [f.key for f in TASK_FIELDS]
REQUIRED_FIELDS: set[str] = {f.key for f in TASK_FIELDS if f.required}
_FIELD_BY_KEY: dict[str, Field] = {f.key: f for f in TASK_FIELDS}


# ---------------------------------------------------------------------------
# Enforcement — no None allowed anywhere
# ---------------------------------------------------------------------------

def enforce_defaults(task: dict[str, Any]) -> dict[str, Any]:
    """
    Return a copy of task with every schema field present and non-None.
    Missing fields get their schema default ("" if none specified).
    """
    out: dict[str, Any] = {}
    for f in TASK_FIELDS:
        val = task.get(f.key)
        if val is None:
            # Use schema default; ID has no default so leave blank string
            out[f.key] = f.default
        else:
            out[f.key] = val
    # Preserve any extra keys not in schema (pass-through)
    for k, v in task.items():
        if k not in out:
            out[k] = "" if v is None else v
    return out


def validate(task: dict[str, Any]) -> list[str]:
    """
    Return a list of validation error messages for a task.
    A task is invalid if a required field is blank ("" or None).
    """
    errors: list[str] = []
    for f in TASK_FIELDS:
        if not f.required:
            continue
        val = task.get(f.key)
        if val is None or str(val).strip() == "":
            errors.append(f"  {f.key} ({f.label}) is required but blank")
    return errors


def validate_all(tasks: list[dict]) -> dict[str, list[str]]:
    """Return {task_id: [errors]} for any tasks that fail validation."""
    issues: dict[str, list[str]] = {}
    for t in tasks:
        errs = validate(t)
        if errs:
            issues[t.get("ID", "?")] = errs
    return issues


# ---------------------------------------------------------------------------
# Claude prompt helpers
# ---------------------------------------------------------------------------

def field_descriptions() -> str:
    lines: list[str] = []
    for f in TASK_FIELDS:
        req = " [REQUIRED — never leave blank]" if f.required else ""
        lines.append(f'- {f.key}: {f.description}{req}')
    return "\n".join(lines)


def prompt_example() -> str:
    """Single example task block for Claude prompts."""
    lines: list[str] = []
    for f in TASK_FIELDS:
        lines.append(f"{f.key}: {f.example}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Markdown schema reference (written to boilerplate)
# ---------------------------------------------------------------------------

def schema_md() -> str:
    lines = [
        "# Task Field Schema\n",
        "> Source of truth: `planning/task_fields.yaml`\n",
        "Every task in TASKS.md must have every field present.",
        'Use `""` (empty string) when a field is genuinely not applicable — never leave a field out.\n',
        "| Field | Required | Default | Description |",
        "|-------|----------|---------|-------------|",
    ]
    for f in TASK_FIELDS:
        req = "yes" if f.required else "no"
        default = f'`"{f.default}"`' if f.default else "—"
        lines.append(f"| `{f.key}` | {req} | {default} | {f.description} |")
    return "\n".join(lines)
