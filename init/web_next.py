"""Next.js scaffold."""

import subprocess
from pathlib import Path

NAME = "Web — Next.js"
DESCRIPTION = "Next.js app with TypeScript and App Router"
DETECTS = ["next.config.js", "next.config.ts", "next.config.mjs"]
STACK_NOTES = "Language: TypeScript | Framework: Next.js (App Router) | Package manager: npm | Optional: Tailwind CSS"


def scaffold(target: Path) -> bool:
    if subprocess.run(["node", "--version"], capture_output=True).returncode != 0:
        print("\n  Node.js is not installed. Install from https://nodejs.org/\n")
        return False

    print("\n  create-next-app will ask a few questions interactively.")
    print("  Recommended answers: TypeScript=Yes, ESLint=Yes, Tailwind=Yes, src/=Yes, App Router=Yes\n")

    r = subprocess.run(
        ["npx", "create-next-app@latest", "."],
        cwd=target,
    )
    if r.returncode != 0:
        return False

    print("\n  Next.js scaffold ready.  Run: npm run dev\n")
    return True
