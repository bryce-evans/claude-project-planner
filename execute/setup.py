#!/usr/bin/env python3
"""
Execute-phase setup: install deps, configure build, scaffold CI, set up test harness.

Run this once at the start of the execute phase, from your project root:
    python path/to/execute/setup.py

Reads ARCHITECTURE.md to know the project type, then runs the appropriate
scaffold commands from init/ (the actions deferred from the planning phase).
"""

import subprocess
import sys
from pathlib import Path

PLANNER_DIR = Path(__file__).parent.parent
INIT_DIR = PLANNER_DIR / "init"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def hr(char: str = "─", width: int = 60) -> str:
    return char * width


def _run(label: str, cmd: list[str], cwd: Path = Path(".")) -> bool:
    print(f"\n  $ {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=cwd)
    if r.returncode != 0:
        print(f"  ✗ {label} failed (exit {r.returncode})")
    return r.returncode == 0


# ---------------------------------------------------------------------------
# Read project type from ARCHITECTURE.md
# ---------------------------------------------------------------------------

def _read_project_type() -> tuple[str, str] | None:
    """Return (type_name, stack_notes) from ARCHITECTURE.md, or None."""
    arch = Path("ARCHITECTURE.md")
    if not arch.exists():
        return None
    text = arch.read_text()
    marker = "## Project Type\n"
    if marker not in text:
        return None
    start = text.index(marker) + len(marker)
    end = text.find("\n##", start)
    block = text[start:end].strip() if end != -1 else text[start:].strip()
    # Parse **Type:** line
    for line in block.splitlines():
        if line.startswith("**Type:**"):
            type_name = line.replace("**Type:**", "").strip()
            return type_name, block
    return None


# ---------------------------------------------------------------------------
# CI scaffolding
# ---------------------------------------------------------------------------

_GITHUB_ACTIONS_DIR = Path(".github/workflows")

_CI_TEMPLATES = {
    "python": """\
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - run: uv run pytest
""",
    "node": """\
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20', cache: 'npm' }
      - run: npm ci
      - run: npm test
""",
    "go": """\
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with: { go-version: 'stable' }
      - run: go test ./...
""",
    "rust": """\
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
      - run: cargo test
""",
}

# Deploy workflow snippets appended to CI when a deploy target is chosen
_DEPLOY_SNIPPETS = {
    "aws-ecs": """\

  deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ secrets.AWS_REGION }}
      - uses: aws-actions/amazon-ecr-login@v2
      - run: |
          docker build -t ${{ secrets.ECR_REGISTRY }}/${{ secrets.ECR_REPO }}:${{ github.sha }} .
          docker push ${{ secrets.ECR_REGISTRY }}/${{ secrets.ECR_REPO }}:${{ github.sha }}
      # Update your ECS task definition and service here
""",
    "aws-lambda": """\

  deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ secrets.AWS_REGION }}
      - run: pip install awscli
      - run: |
          zip -r function.zip .
          aws lambda update-function-code --function-name ${{ secrets.LAMBDA_FUNCTION }} --zip-file fileb://function.zip
""",
    "k8s": """\

  deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - uses: azure/k8s-set-context@v3
        with:
          kubeconfig: ${{ secrets.KUBECONFIG }}
      - run: |
          docker build -t $IMAGE:${{ github.sha }} .
          docker push $IMAGE:${{ github.sha }}
          kubectl set image deployment/$DEPLOY_NAME app=$IMAGE:${{ github.sha }}
""",
    "fly": """\

  deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - uses: superfly/flyctl-actions/setup-flyctl@master
      - run: flyctl deploy --remote-only
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
""",
    "render": """\

  # Render.com: set up auto-deploy from your Render dashboard.
  # No workflow step needed — Render deploys on push to main automatically.
""",
    "railway": """\

  # Railway: set up auto-deploy from your Railway dashboard.
  # No workflow step needed — Railway deploys on push automatically.
""",
}

_TYPE_CI_MAP = {
    "Python (uv)": "python",
    "Web — React + Vite": "node",
    "Web — Next.js": "node",
    "Node.js (backend / API)": "node",
    "Mobile — Expo (React Native + TypeScript)": "node",
    "Go": "go",
    "Rust (Cargo)": "rust",
}

_TYPE_TEST_MAP = {
    "Python (uv)":                        ("pytest", ["uv", "add", "--dev", "pytest", "pytest-cov"]),
    "Web — React + Vite":                 ("vitest", ["npm", "install", "-D", "vitest", "@testing-library/react", "@testing-library/user-event"]),
    "Web — Next.js":                      ("jest",   ["npm", "install", "-D", "jest", "@testing-library/react", "@testing-library/user-event", "jest-environment-jsdom"]),
    "Node.js (backend / API)":            ("jest",   ["npm", "install", "-D", "jest", "@types/jest", "ts-jest"]),
    "Mobile — Expo (React Native + TypeScript)": ("jest", ["npm", "install", "-D", "jest", "@testing-library/react-native", "jest-expo"]),
    "Go":   None,   # go test is built-in
    "Rust": None,   # cargo test is built-in
}


_DEPLOY_OPTIONS = [
    ("1", "aws-ecs",  "AWS ECS       — Docker container on ECS"),
    ("2", "aws-lambda", "AWS Lambda  — serverless function"),
    ("3", "k8s",     "Kubernetes    — generic k8s cluster"),
    ("4", "fly",     "Fly.io        — managed container platform"),
    ("5", "render",  "Render.com    — auto-deploy from git push"),
    ("6", "railway", "Railway       — auto-deploy from git push"),
    ("7", "none",    "None / local  — no remote deploy step"),
]

_CI_PROVIDERS = [
    ("1", "github",   "GitHub Actions  (recommended)"),
    ("2", "skip",     "Skip — I'll set up CI manually"),
]


def _scaffold_ci(type_name: str, deploy_key: str | None) -> None:
    print("\n  CI provider:")
    for key, slug, label in _CI_PROVIDERS:
        print(f"  {key}. {label}")
    choice = input("\n  Choice [1]: ").strip() or "1"

    if choice == "2":
        print("  Skipped.\n")
        return

    lang_key = _TYPE_CI_MAP.get(type_name)
    if not lang_key:
        print("  No CI template for this project type — skipping.\n")
        return

    # Build CI file content
    ci_content = _CI_TEMPLATES[lang_key]
    if deploy_key and deploy_key in _DEPLOY_SNIPPETS:
        ci_content = ci_content.rstrip() + "\n" + _DEPLOY_SNIPPETS[deploy_key]

    # Branch that triggers deploy
    branch = input("  Deploy branch [main]: ").strip() or "main"
    ci_content = ci_content.replace("refs/heads/main", f"refs/heads/{branch}")

    _GITHUB_ACTIONS_DIR.mkdir(parents=True, exist_ok=True)
    ci_file = _GITHUB_ACTIONS_DIR / "ci.yml"
    if ci_file.exists():
        ans = input(f"  {ci_file} already exists. Overwrite? [y/N]: ").strip().lower()
        if ans != "y":
            print("  Skipped.\n")
            return

    ci_file.write_text(ci_content)
    print(f"  Written: {ci_file}")
    if deploy_key and deploy_key not in ("none", "render", "railway"):
        print("  Remember to add required secrets to your GitHub repo settings.\n")
    else:
        print()


def _scaffold_deployment() -> str | None:
    """
    Ask about remote server / deployment target. Returns the deploy key
    (e.g. 'aws-ecs', 'k8s', 'fly') or None if local/none.
    Also writes deployment decisions to ARCHITECTURE.md.
    """
    print("\n  Does this project have a remote server / deployment target?\n")
    ans = input("  [Y/n]: ").strip().lower()
    if ans == "n":
        return None

    print("\n  Deployment target:\n")
    for key, slug, label in _DEPLOY_OPTIONS:
        print(f"  {key}. {label}")

    choice = input("\n  Choice [7]: ").strip() or "7"
    match = next(((slug, label) for k, slug, label in _DEPLOY_OPTIONS if k == choice), ("none", "None / local"))
    deploy_slug, deploy_label = match

    if deploy_slug == "none":
        return None

    # Region / cluster / extra config
    extra = ""
    if deploy_slug.startswith("aws"):
        region = input("  AWS region [us-east-1]: ").strip() or "us-east-1"
        extra = f"\nRegion: {region}"
    elif deploy_slug == "k8s":
        cluster = input("  Cluster name / context: ").strip()
        extra = f"\nCluster: {cluster}" if cluster else ""
    elif deploy_slug == "fly":
        app = input("  Fly app name (leave blank to set later): ").strip()
        extra = f"\nFly app: {app}" if app else ""

    # Record in ARCHITECTURE.md
    arch = Path("ARCHITECTURE.md")
    if arch.exists():
        deploy_block = f"\n\n## Deployment Target\n**Platform:** {deploy_label}{extra}\n"
        existing = arch.read_text()
        if "## Deployment Target" not in existing:
            arch.write_text(existing.rstrip() + deploy_block)
            print(f"  Deployment target recorded in ARCHITECTURE.md.\n")

    return deploy_slug


def _scaffold_tests(type_name: str) -> None:
    entry = _TYPE_TEST_MAP.get(type_name)
    if entry is None:
        print(f"  Test harness: built-in (no install needed for {type_name}).\n")
        return

    harness_name, install_cmd = entry
    print(f"\n  Installing {harness_name}...\n")
    _run(f"install {harness_name}", install_cmd)


# ---------------------------------------------------------------------------
# Main scaffold dispatch
# ---------------------------------------------------------------------------

def _run_scaffold(type_name: str, target: Path) -> bool:
    """Run the init/ scaffold for the chosen project type."""
    sys.path.insert(0, str(INIT_DIR.parent))
    try:
        from init import SCAFFOLDERS
    except ImportError:
        print("  Could not load init/ modules — is this the right working directory?\n")
        return False

    match = next((s for s in SCAFFOLDERS if s.NAME == type_name), None)
    if not match:
        print(f"  No scaffold found for '{type_name}'. Run manually.\n")
        return False

    return match.scaffold(target)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    target = Path.cwd()

    print(f"\n{hr('═')}")
    print("  Execute — Project Setup")
    print(hr("═"))

    # 1. Detect project type
    result = _read_project_type()
    if not result:
        print("\n  No project type found in ARCHITECTURE.md.")
        print("  Run planning/plan.py first, or add a '## Project Type' section manually.\n")
        sys.exit(1)

    type_name, stack_notes = result
    print(f"\n  Project type: {type_name}")
    print(f"  {stack_notes.replace(chr(10), '  ')}\n")

    # 2. Run scaffold (install deps, create files)
    already_scaffolded = any(
        (target / f).exists()
        for f in ["pyproject.toml", "package.json", "go.mod", "Cargo.toml", "app.json"]
    )

    if already_scaffolded:
        print("  Project already scaffolded — skipping init.\n")
        print("  Installing/syncing dependencies...\n")
        # Best-effort dep install based on what's present
        if (target / "pyproject.toml").exists() or (target / "requirements.txt").exists():
            if subprocess.run(["uv", "--version"], capture_output=True).returncode == 0:
                _run("uv sync", ["uv", "sync"])
            else:
                _run("pip install", [sys.executable, "-m", "pip", "install", "-e", "."])
        elif (target / "package.json").exists():
            _run("npm install", ["npm", "install"])
        elif (target / "go.mod").exists():
            _run("go mod download", ["go", "mod", "download"])
        elif (target / "Cargo.toml").exists():
            _run("cargo fetch", ["cargo", "fetch"])
    else:
        print(f"  Running scaffold for {type_name}...\n")
        if not _run_scaffold(type_name, target):
            print("\n  Scaffold failed. Fix the issue and re-run.\n")
            sys.exit(1)

    # 3. Test harness
    print(f"\n{hr('─')}")
    print("  Test harness")
    print(hr("─"))
    ans = input(f"\n  Set up test harness? [Y/n]: ").strip().lower()
    if ans != "n":
        _scaffold_tests(type_name)

    # 4. Deployment target
    print(f"\n{hr('─')}")
    print("  Deployment")
    print(hr("─"))
    deploy_key = _scaffold_deployment()

    # 5. CI
    print(f"\n{hr('─')}")
    print("  CI")
    print(hr("─"))
    ans = input("\n  Set up CI? [Y/n]: ").strip().lower()
    if ans != "n":
        _scaffold_ci(type_name, deploy_key)

    # 5. Summary
    print(f"\n{hr('═')}")
    print("  Setup complete. Next:")
    print("  - Use /next in Claude Code to start executing tasks")
    print("  - Run execute/render.py to open the live task flowchart")
    print(hr("═") + "\n")


if __name__ == "__main__":
    main()
