"""Python + uv scaffold."""

import subprocess
import sys
from pathlib import Path

NAME = "Python (uv)"
DESCRIPTION = "Python project with uv package manager, src/ layout, tests/"
DETECTS = ["pyproject.toml", "uv.lock", ".python-version"]
STACK_NOTES = "Language: Python | Package manager: uv | Layout: src/ + tests/ | Build: hatch/uv build"


def scaffold(target: Path) -> bool:
    # Check uv is available
    if subprocess.run(["uv", "--version"], capture_output=True).returncode != 0:
        print("\n  uv is not installed. Install it from https://docs.astral.sh/uv/")
        print("  Then re-run with -f init.\n")
        return False

    name = input(f"\n  Project name [{target.name}]: ").strip() or target.name
    description = input("  Short description: ").strip()

    print(f"\n  Running: uv init --name {name} .\n")
    r = subprocess.run(
        ["uv", "init", "--name", name, "--no-readme", "."],
        cwd=target,
    )
    if r.returncode != 0:
        return False

    # Create src/ layout and tests/
    src = target / "src" / name.replace("-", "_")
    src.mkdir(parents=True, exist_ok=True)
    (src / "__init__.py").write_text("")

    tests = target / "tests"
    tests.mkdir(exist_ok=True)
    (tests / "__init__.py").write_text("")
    (tests / "test_placeholder.py").write_text(
        f'"""Placeholder test suite for {name}."""\n\n\ndef test_placeholder():\n    pass\n'
    )

    # Add description to pyproject.toml if provided
    if description:
        pyproject = target / "pyproject.toml"
        text = pyproject.read_text()
        text = text.replace('description = ""', f'description = "{description}"')
        pyproject.write_text(text)

    # .python-version (pin to current interpreter)
    ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    (target / ".python-version").write_text(ver + "\n")

    print(f"\n  Python (uv) scaffold ready.")
    print(f"    src/{name.replace('-','_')}/__init__.py")
    print(f"    tests/")
    print(f"    pyproject.toml")
    print(f"    .python-version  ({ver})")
    return True
