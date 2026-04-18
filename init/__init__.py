"""
Scaffolding registry.

Each module exposes:
  NAME        str            — display name shown in the menu
  DESCRIPTION str            — one-line summary
  DETECTS     list[str]      — filenames whose presence means this scaffold is done
  scaffold(target: Path) -> bool   — run the scaffolding; return True on success
"""

from pathlib import Path

from . import go, mobile, node, python, rust, web_next, web_vite

# Ordered list shown in the menu
SCAFFOLDERS = [python, web_vite, web_next, node, mobile, go, rust]

# All filenames that signal *any* scaffold (or existing code) is present
ALL_SIGNALS: list[str] = []
for _s in SCAFFOLDERS:
    ALL_SIGNALS.extend(_s.DETECTS)

# Marker written when the user deliberately skips scaffolding
SKIP_MARKER = ".planner_scaffold_skip"


def is_scaffolded(target: Path) -> bool:
    """Return True if the target already has language scaffold or user skipped."""
    if (target / SKIP_MARKER).exists():
        return True
    return any((target / f).exists() for f in ALL_SIGNALS)


def mark_skipped(target: Path) -> None:
    (target / SKIP_MARKER).write_text("scaffold skipped\n")
