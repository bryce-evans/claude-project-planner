"""Go module scaffold."""

import subprocess
from pathlib import Path

NAME = "Go"
DESCRIPTION = "Go module with cmd/ and internal/ layout"
DETECTS = ["go.mod", "go.sum"]
STACK_NOTES = "Language: Go | Layout: cmd/ + internal/ | Build: go build | Module: go.mod"


def scaffold(target: Path) -> bool:
    if subprocess.run(["go", "version"], capture_output=True).returncode != 0:
        print("\n  Go is not installed. Install from https://go.dev/dl/\n")
        return False

    default_module = f"github.com/user/{target.name}"
    module = input(f"\n  Module path [{default_module}]: ").strip() or default_module

    print(f"\n  Running: go mod init {module}\n")
    r = subprocess.run(["go", "mod", "init", module], cwd=target)
    if r.returncode != 0:
        return False

    # Standard Go layout
    cmd_dir = target / "cmd" / target.name
    cmd_dir.mkdir(parents=True, exist_ok=True)
    (cmd_dir / "main.go").write_text(
        f'package main\n\nimport "fmt"\n\nfunc main() {{\n\tfmt.Println("Hello, {target.name}!")\n}}\n'
    )

    internal = target / "internal"
    internal.mkdir(exist_ok=True)

    print(f"\n  Go scaffold ready.")
    print(f"    go.mod  (module: {module})")
    print(f"    cmd/{target.name}/main.go")
    print(f"    internal/")
    print(f"\n  Run: go run ./cmd/{target.name}\n")
    return True
