#!/usr/bin/env python3
"""
Copy boilerplate files into a new or existing project directory.

Usage:
    python path/to/planning/setup.py [target_dir]

    target_dir defaults to the current directory.
"""

import shutil
import sys
from pathlib import Path

BOILERPLATE_DIR = Path(__file__).parent.parent / "boilerplate"


def main() -> None:
    target = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    target.mkdir(parents=True, exist_ok=True)

    print(f"\n  Setup — copying boilerplate into: {target}\n")

    if not BOILERPLATE_DIR.exists():
        print(f"  ERROR: boilerplate directory not found at {BOILERPLATE_DIR}")
        sys.exit(1)

    sources = sorted(BOILERPLATE_DIR.iterdir())
    copied, skipped = [], []

    for src in sources:
        if not src.is_file():
            continue
        dst = target / src.name
        if dst.exists():
            ans = input(f"  {src.name} already exists. Overwrite? [y/N]: ").strip().lower()
            if ans != "y":
                skipped.append(src.name)
                print(f"    skipped")
                continue
        shutil.copy2(src, dst)
        copied.append(src.name)
        print(f"  + {src.name}")

    print()
    print(f"  Copied {len(copied)} file(s).", end="")
    if skipped:
        print(f" Skipped: {', '.join(skipped)}.", end="")
    print("\n")
    print("  Next steps:")
    print("  1. python path/to/planning/start.py   — identify yourself and claim a workstream")
    print("  2. python path/to/planning/plan.py    — define the project and generate a plan\n")


if __name__ == "__main__":
    main()
