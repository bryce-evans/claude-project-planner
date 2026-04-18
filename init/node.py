"""Node.js backend scaffold."""

import json
import subprocess
from pathlib import Path

NAME = "Node.js (backend / API)"
DESCRIPTION = "Node.js backend with TypeScript, your choice of framework"
DETECTS = ["package.json"]
STACK_NOTES = "Language: TypeScript | Runtime: Node.js | Package manager: npm | Framework: Express / Fastify / Hono / none"

_FRAMEWORKS = {
    "1": ("express",  "Express  — minimal, battle-tested"),
    "2": ("fastify",  "Fastify  — fast, schema-first"),
    "3": ("hono",     "Hono     — ultra-lightweight, edge-ready"),
    "4": ("none",     "None     — plain Node.js / TypeScript"),
}


def scaffold(target: Path) -> bool:
    if subprocess.run(["node", "--version"], capture_output=True).returncode != 0:
        print("\n  Node.js is not installed. Install from https://nodejs.org/\n")
        return False

    name = input(f"\n  Project name [{target.name}]: ").strip() or target.name
    description = input("  Short description: ").strip()

    print("\n  Framework:")
    for key, (_, label) in _FRAMEWORKS.items():
        print(f"    {key}. {label}")
    choice = input("\n  Choice [1]: ").strip() or "1"
    framework, _ = _FRAMEWORKS.get(choice, _FRAMEWORKS["1"])

    # npm init
    pkg = {
        "name": name,
        "version": "0.1.0",
        "description": description,
        "type": "module",
        "scripts": {
            "dev": "tsx watch src/index.ts",
            "build": "tsc",
            "start": "node dist/index.js",
        },
        "engines": {"node": ">=20"},
    }
    (target / "package.json").write_text(json.dumps(pkg, indent=2) + "\n")

    # TypeScript + tsx
    deps = ["typescript", "tsx", "@types/node"]
    if framework != "none":
        deps.append(framework)
        if framework == "express":
            deps.append("@types/express")

    print(f"\n  Installing: {', '.join(deps)}\n")
    subprocess.run(["npm", "install", "-D", *deps], cwd=target)

    # tsconfig
    tsconfig = {
        "compilerOptions": {
            "target": "ES2022",
            "module": "NodeNext",
            "moduleResolution": "NodeNext",
            "outDir": "dist",
            "rootDir": "src",
            "strict": True,
            "esModuleInterop": True,
        },
        "include": ["src"],
    }
    (target / "tsconfig.json").write_text(json.dumps(tsconfig, indent=2) + "\n")

    # Minimal entry point
    src = target / "src"
    src.mkdir(exist_ok=True)

    if framework == "express":
        entry = (
            "import express from 'express'\n\n"
            "const app = express()\napp.use(express.json())\n\n"
            "app.get('/', (_req, res) => res.json({ ok: true }))\n\n"
            "app.listen(3000, () => console.log('Listening on :3000'))\n"
        )
    elif framework == "fastify":
        entry = (
            "import Fastify from 'fastify'\n\n"
            "const app = Fastify()\n\n"
            "app.get('/', async () => ({ ok: true }))\n\n"
            "await app.listen({ port: 3000 })\nconsole.log('Listening on :3000')\n"
        )
    elif framework == "hono":
        entry = (
            "import { Hono } from 'hono'\nimport { serve } from '@hono/node-server'\n\n"
            "const app = new Hono()\n\napp.get('/', (c) => c.json({ ok: true }))\n\n"
            "serve(app, () => console.log('Listening on :3000'))\n"
        )
    else:
        entry = (
            "import http from 'node:http'\n\n"
            "const server = http.createServer((_req, res) => {\n"
            "  res.writeHead(200, { 'Content-Type': 'application/json' })\n"
            "  res.end(JSON.stringify({ ok: true }))\n})\n\n"
            "server.listen(3000, () => console.log('Listening on :3000'))\n"
        )

    (src / "index.ts").write_text(entry)

    print(f"\n  Node.js scaffold ready.  Run: npm run dev\n")
    return True
