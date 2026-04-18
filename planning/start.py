#!/usr/bin/env python3
"""
Identify yourself and claim a workstream.

Run this at the start of every session — human or AI agent.
Writes WORKSTREAM.md, which CLAUDE.md instructs Claude to always read before acting.

Usage (run from your project root):
    python path/to/planning/start.py
"""

import re
import sys
from datetime import date
from pathlib import Path

import anthropic
import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent))
from git_plan import pull_all, plan_branch_exists

MODEL = "claude-sonnet-4-6"

PLAN_MD = Path("PLAN.md")
WORKSTREAM_MD = Path("WORKSTREAM.md")
ME_MD = Path("ME.md")

_ME_PLACEHOLDER = "_TODO_"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def hr(char: str = "─", width: int = 60) -> str:
    return char * width


def header(title: str) -> None:
    print(f"\n{hr()}")
    print(f"  {title}")
    print(hr())


# ---------------------------------------------------------------------------
# ME.md — personal identity and context
# ---------------------------------------------------------------------------

def _me_is_blank() -> bool:
    if not ME_MD.exists():
        return True
    return _ME_PLACEHOLDER in ME_MD.read_text()


def _read_me_field(label: str) -> str:
    if not ME_MD.exists():
        return ""
    m = re.search(rf"\*\*{re.escape(label)}:\*\*\s*(.+)", ME_MD.read_text())
    return m.group(1).strip() if m else ""


def _write_me_md(workstream: str, notes: str) -> None:
    ME_MD.write_text(
        f"> Personal context. Not committed to git.\n"
        f"> Last updated: {date.today()}  |  Re-run start.py to update.\n\n"
        f"# Me\n\n"
        f"**Workstream:** {workstream or '—'}\n"
        f"**Notes:** {notes or '—'}\n"
    )


def ensure_me_md(ws_label: str = "") -> None:
    """
    Ensure ME.md exists and is filled.
    If blank/missing: ask two questions — workstream and personal notes.
    If filled: show it and offer a quick update.
    """
    if _me_is_blank():
        header("ME.md — Your personal context (not committed)")
        print("\n  Two quick fields. This file is gitignored — it's only for you.\n")
        ws = input(f"  Workstream (e.g. WS1 — Keymaster){f' [{ws_label}]' if ws_label else ''}: ").strip()
        if not ws and ws_label:
            ws = ws_label
        notes = input("  Notes for Claude (preferences, constraints, anything relevant): ").strip()
        _write_me_md(ws, notes)
        print(f"\n  ME.md written.\n")
    else:
        print(f"\n  ME.md: {_read_me_field('Workstream')}  |  {_read_me_field('Notes')[:60]}")
        ans = input("  Update ME.md? [y/N]: ").strip().lower()
        if ans == "y":
            ws = input(f"  Workstream [{_read_me_field('Workstream')}]: ").strip() or _read_me_field("Workstream")
            notes = input(f"  Notes [{_read_me_field('Notes')[:40]}]: ").strip() or _read_me_field("Notes")
            _write_me_md(ws, notes)
            print("  Updated.\n")


# ---------------------------------------------------------------------------
# Parse workstreams from PLAN.md
# ---------------------------------------------------------------------------

def load_workstreams() -> list[dict]:
    """Parse the workstream summary table from PLAN.md."""
    if not PLAN_MD.exists():
        return []

    content = PLAN_MD.read_text()
    workstreams = []

    # Match rows in the | WS1 | Name | Scope | Status | table
    pattern = re.compile(r"^\|\s*(WS\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(\w+)\s*\|", re.MULTILINE)
    for m in pattern.finditer(content):
        workstreams.append(
            {
                "id": m.group(1),
                "name": m.group(2).strip(),
                "scope": m.group(3).strip(),
                "status": m.group(4).strip(),
            }
        )
    return workstreams


# ---------------------------------------------------------------------------
# Claude: draft responsibilities
# ---------------------------------------------------------------------------

RESPONSIBILITIES_PROMPT = """\
You are helping a team member understand their role on a software project.

Project plan workstreams:
{all_ws}

This person is taking on:
  {ws_id} — {ws_name}: {ws_scope}

Their name/identifier: {name}
Their type: {actor_type}

Write a concise bullet list (4–6 points) of their specific responsibilities for this workstream. \
Include:
- What they own end-to-end
- Key integration points with other workstreams they should coordinate on
- Any decisions that are theirs to make

Write only the bullet list. No preamble, no section headers. Use "- " bullets.
"""


def draft_responsibilities(name: str, actor_type: str, ws: dict, all_ws: list[dict]) -> str:
    client = anthropic.Anthropic()
    all_ws_text = "\n".join(
        f"  {w['id']} — {w['name']}: {w['scope']}" for w in all_ws
    )

    print("\n  Drafting responsibilities...\n")
    result = ""
    with client.messages.stream(
        model=MODEL,
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": RESPONSIBILITIES_PROMPT.format(
                    all_ws=all_ws_text,
                    ws_id=ws["id"],
                    ws_name=ws["name"],
                    ws_scope=ws["scope"],
                    name=name,
                    actor_type=actor_type,
                ),
            }
        ],
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)
            result += text
    print()
    return result.strip()


# ---------------------------------------------------------------------------
# Write WORKSTREAM.md
# ---------------------------------------------------------------------------

def write_workstream_md(
    name: str,
    actor_type: str,
    ws: dict | None,
    custom_scope: str,
    responsibilities: str,
    focus: str,
) -> None:
    ws_id = ws["id"] if ws else "—"
    ws_name = ws["name"] if ws else "Custom"
    ws_scope = ws["scope"] if ws else custom_scope

    lines = [
        f"> Last updated: {date.today()}  |  Re-run `start.py` to refresh.\n",
        "# Active Workstream\n",
        f"**Name:** {name}",
        f"**Type:** {actor_type}",
        f"**Workstream:** {ws_id} — {ws_name}",
        f"**Scope:** {ws_scope}",
        "",
        "## Responsibilities\n",
        responsibilities,
        "",
    ]

    if focus:
        lines += [
            "## Session Focus\n",
            focus,
            "",
        ]

    lines += [
        "## Current Task\n",
        "_Not started — update this as you begin work._",
        "",
    ]

    WORKSTREAM_MD.write_text("\n".join(lines))
    print(f"\n  Written to {WORKSTREAM_MD}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        print("\n" + hr("="))
        print("  Start — Session Setup")
        print(hr("="))

        # Step 1: Pull everything up to date
        print("\n  Syncing from git...\n")
        pull_all(verbose=True)

        # Step 2: Name and type
        print()
        name = input("  Your name or identifier (e.g. 'Bryce', 'claude-agent-1'): ").strip()
        while not name:
            name = input("  (required) > ").strip()

        print("\n  Human or AI agent? [H/a]: ", end="")
        actor_raw = input().strip().lower()
        actor_type = "AI agent" if actor_raw == "a" else "Human"

        # Load workstreams
        all_ws = load_workstreams()

        ws: dict | None = None
        custom_scope = ""

        if all_ws:
            header("Available Workstreams")
            print()
            for i, w in enumerate(all_ws, 1):
                print(f"  {i}. {w['id']} — {w['name']}")
                print(f"     {w['scope']}")
            print(f"  {len(all_ws) + 1}. Custom / not listed\n")

            choice = input("  Pick a workstream (number): ").strip()
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(all_ws):
                    ws = all_ws[idx]
                else:
                    custom_scope = input("  Describe your role/focus: ").strip()
            else:
                custom_scope = input("  Describe your role/focus: ").strip()
        else:
            print("\n  No PLAN.md found — describe your role manually.")
            custom_scope = input("  Your role or focus: ").strip()

        # Confirm scope
        scope_display = ws["scope"] if ws else custom_scope
        ws_label = f"{ws['id']} — {ws['name']}" if ws else custom_scope
        print(f"\n  Scope: {scope_display}")

        # Step 3: ME.md — now we know the workstream
        ensure_me_md(ws_label)

        # Optional session focus
        print("\n  Any specific focus or constraints for this session?")
        focus = input("  (optional, Enter to skip): ").strip()

        # Draft responsibilities via Claude if workstream is known
        if ws or custom_scope:
            responsibilities = draft_responsibilities(
                name, actor_type, ws or {"id": "—", "name": "Custom", "scope": custom_scope}, all_ws
            )

            print(f"\n  Accept these responsibilities? [Y/n]: ", end="")
            ans = input().strip().lower()
            if ans == "n":
                print("  Paste your responsibilities (blank line to finish):\n")
                lines: list[str] = []
                while True:
                    line = input("  > ")
                    if not line and lines:
                        break
                    if line:
                        lines.append(f"- {line}")
                responsibilities = "\n".join(lines)
        else:
            responsibilities = "- _TODO: define responsibilities_"

        write_workstream_md(name, actor_type, ws, custom_scope, responsibilities, focus)

        print(hr("="))
        print(f"  Ready, {name}. WORKSTREAM.md is set.")
        print(f"  Claude will read it before every action in this project.")
        print(hr("=") + "\n")

    except KeyboardInterrupt:
        print("\n\n  Interrupted.\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
