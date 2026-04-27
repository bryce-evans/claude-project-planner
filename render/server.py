#!/usr/bin/env python3
"""
Static file server with GitHub webhook support.

Serves the built render app from dist/ and updates tasks.json
whenever a GitHub push webhook fires (or any POST to /webhook).

Usage (run from your project root):
    python render/server.py [--port 8080] [--secret YOUR_WEBHOOK_SECRET]

Setup:
    1. Build the app once:  cd render && npm run build
    2. Start the server:    python render/server.py
    3. In GitHub repo settings → Webhooks:
       - Payload URL: https://your-host/webhook
       - Content type: application/json
       - Secret: same value as --secret (optional but recommended)
       - Events: Just the push event
"""

import argparse
import hashlib
import hmac
import http.server
import json
import mimetypes
import os
import subprocess
import sys
import threading
from pathlib import Path

RENDER_DIR = Path(__file__).parent
DIST_DIR = RENDER_DIR / "dist"
PUBLIC_DIR = RENDER_DIR / "public"
PROJECT_ROOT = RENDER_DIR.parent


def refresh_tasks() -> str:
    """Pull latest from Dolt and regenerate tasks.json. Returns status message."""
    steps = []

    # Pull latest beads data
    r = subprocess.run(
        ["bd", "dolt", "pull"],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
    )
    steps.append(f"bd dolt pull: {'ok' if r.returncode == 0 else r.stderr.strip()}")

    # Regenerate data files
    r = subprocess.run(
        [sys.executable, str(RENDER_DIR / "render.py"), "--data"],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
    )
    steps.append(f"render.py --data: {'ok' if r.returncode == 0 else r.stderr.strip()}")

    return " | ".join(steps)


class Handler(http.server.BaseHTTPRequestHandler):
    webhook_secret: bytes | None = None

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} {fmt % args}")

    def _send(self, code: int, body: str, content_type: str = "text/plain") -> None:
        encoded = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", len(encoded))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        path = self.path.split("?")[0]

        # Serve tasks.json directly from public/ (always fresh)
        if path == "/tasks.json":
            json_file = PUBLIC_DIR / "tasks.json"
            if not json_file.exists():
                self._send(404, "tasks.json not found — run render.py --data first")
                return
            data = json_file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(data))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
            return

        # Serve static files from dist/
        if not DIST_DIR.exists():
            self._send(503, "dist/ not found — run: cd render && npm run build")
            return

        # Map / to index.html, fall back to index.html for SPA routing
        file_path = DIST_DIR / (path.lstrip("/") or "index.html")
        if not file_path.exists() or not file_path.is_file():
            file_path = DIST_DIR / "index.html"

        if not file_path.exists():
            self._send(404, "Not found")
            return

        mime, _ = mimetypes.guess_type(str(file_path))
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", len(data))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path.split("?")[0] != "/webhook":
            self._send(404, "Not found")
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        # Validate GitHub signature if secret is configured
        if self.webhook_secret:
            sig_header = self.headers.get("X-Hub-Signature-256", "")
            expected = "sha256=" + hmac.new(self.webhook_secret, body, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig_header, expected):
                self._send(403, "Invalid signature")
                return

        # Run refresh in background so webhook response is fast
        def _run():
            msg = refresh_tasks()
            print(f"  webhook refresh: {msg}")

        threading.Thread(target=_run, daemon=True).start()
        self._send(200, "ok — refresh queued")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render static server + webhook handler")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8080)))
    parser.add_argument("--secret", default=os.environ.get("WEBHOOK_SECRET", ""),
                        help="GitHub webhook secret (or set WEBHOOK_SECRET env var)")
    args = parser.parse_args()

    if args.secret:
        Handler.webhook_secret = args.secret.encode()
        print(f"  Webhook secret: configured")
    else:
        print(f"  Webhook secret: none (unauthenticated — set --secret for production)")

    if not DIST_DIR.exists():
        print(f"\n  WARNING: dist/ not found. Build the app first:")
        print(f"    cd render && npm run build\n")
    else:
        print(f"  Serving: {DIST_DIR}")

    print(f"  Webhook: POST /webhook")
    print(f"  Data:    GET  /tasks.json  (always fresh from public/tasks.json)")
    print(f"\n  Listening on http://0.0.0.0:{args.port}\n")

    server = http.server.HTTPServer(("", args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")


if __name__ == "__main__":
    main()
