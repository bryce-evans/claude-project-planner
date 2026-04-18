"""React + Vite scaffold."""

import subprocess
from pathlib import Path

NAME = "Web — React + Vite"
DESCRIPTION = "React app with Vite, TypeScript, and Tailwind CSS"
DETECTS = ["vite.config.ts", "vite.config.js"]
STACK_NOTES = "Language: TypeScript | Framework: React + Vite | Package manager: npm | Optional: Tailwind CSS"

_TEMPLATES = {
    "1": ("react-ts", "React + TypeScript  (recommended)"),
    "2": ("react",    "React + JavaScript"),
    "3": ("vue-ts",   "Vue + TypeScript"),
    "4": ("vanilla-ts", "Vanilla TypeScript"),
}


def scaffold(target: Path) -> bool:
    if subprocess.run(["node", "--version"], capture_output=True).returncode != 0:
        print("\n  Node.js is not installed. Install from https://nodejs.org/\n")
        return False

    print("\n  Template:")
    for key, (_, label) in _TEMPLATES.items():
        print(f"    {key}. {label}")
    choice = input("\n  Choice [1]: ").strip() or "1"
    template, label = _TEMPLATES.get(choice, _TEMPLATES["1"])

    tailwind = input("  Add Tailwind CSS? [Y/n]: ").strip().lower() != "n"

    print(f"\n  Running: npm create vite@latest . -- --template {template}\n")
    r = subprocess.run(
        ["npm", "create", "vite@latest", ".", "--", "--template", template],
        cwd=target,
    )
    if r.returncode != 0:
        return False

    print("\n  Installing dependencies...\n")
    subprocess.run(["npm", "install"], cwd=target)

    if tailwind:
        print("\n  Adding Tailwind CSS...\n")
        subprocess.run(
            ["npm", "install", "-D", "tailwindcss", "@tailwindcss/vite"],
            cwd=target,
        )
        # Minimal tailwind config
        (target / "tailwind.config.js").write_text(
            "/** @type {import('tailwindcss').Config} */\n"
            "export default {\n"
            "  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],\n"
            "  theme: { extend: {} },\n"
            "  plugins: [],\n"
            "}\n"
        )
        print("  Tailwind configured.")

    print(f"\n  React + Vite scaffold ready.  Run: npm run dev\n")
    return True
