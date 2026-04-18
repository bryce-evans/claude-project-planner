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

MODEL = "claude-sonnet-4-6"

PLAN_MD = Path("PLAN.md")
WORKSTREAM_MD = Path("WORKSTREAM.md")


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
        print("  Start — Identify Yourself")
        print(hr("="))

        # Name / identifier
        print()
        name = input("  Your name or identifier (e.g. 'Bryce', 'claude-agent-1'): ").strip()
        while not name:
            name = input("  (required) > ").strip()

        # Human or agent
        print("\n  Are you a human or an AI agent?")
        print("  [H] Human   [A] AI agent\n")
        actor_raw = input("  > ").strip().lower()
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
        print(f"\n  Scope: {scope_display}")

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
