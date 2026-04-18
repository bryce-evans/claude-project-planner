"""Rust / Cargo scaffold."""

import subprocess
from pathlib import Path

NAME = "Rust (Cargo)"
DESCRIPTION = "Rust project with Cargo, src/lib.rs or src/main.rs"
DETECTS = ["Cargo.toml", "Cargo.lock"]
STACK_NOTES = "Language: Rust | Build: Cargo | Layout: src/lib.rs or src/main.rs"

_TYPES = {
    "1": ("bin", "Binary — has a main() entry point"),
    "2": ("lib", "Library — crate without a binary"),
}


def scaffold(target: Path) -> bool:
    if subprocess.run(["cargo", "--version"], capture_output=True).returncode != 0:
        print("\n  Rust/Cargo is not installed. Install from https://rustup.rs/\n")
        return False

    print("\n  Project type:")
    for key, (_, label) in _TYPES.items():
        print(f"    {key}. {label}")
    choice = input("\n  Choice [1]: ").strip() or "1"
    kind = _TYPES.get(choice, _TYPES["1"])[0]

    flag = "--bin" if kind == "bin" else "--lib"
    print(f"\n  Running: cargo init {flag} .\n")
    r = subprocess.run(["cargo", "init", flag, "."], cwd=target)
    if r.returncode != 0:
        return False

    print(f"\n  Rust scaffold ready.")
    if kind == "bin":
        print("  Run: cargo run")
    else:
        print("  Run: cargo test")
    print()
    return True
