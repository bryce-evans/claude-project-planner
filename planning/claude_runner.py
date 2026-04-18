"""
Generic Claude caller.

Supports two backends, selected once per project and stored in ME.md:

  claude-code  — uses the `claude -p` CLI (Claude Code auth, no API key needed)
  api-key      — uses the Anthropic SDK (reads ANTHROPIC_API_KEY from env)

Usage:
    from claude_runner import call_claude
    text = call_claude(prompt, max_tokens=1024)

Configuration is read from ME.md (**Claude:** field). If not set, the user
is asked once and the answer is saved.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_ME_MD = Path("ME.md")
_FIELD = "Claude"
_VALID = ("claude-code", "api-key")
_MODEL = "claude-sonnet-4-6"


def read_runner() -> str | None:
    """Read the configured runner from ME.md. Returns None if not set."""
    if not _ME_MD.exists():
        return None
    m = re.search(r"\*\*Claude:\*\*\s*(\S+)", _ME_MD.read_text())
    val = m.group(1).strip() if m else None
    return val if val in _VALID else None


def save_runner(runner: str) -> None:
    """Write or update the **Claude:** field in ME.md."""
    if _ME_MD.exists():
        text = _ME_MD.read_text()
        if "**Claude:**" in text:
            text = re.sub(r"\*\*Claude:\*\*\s*\S+", f"**Claude:** {runner}", text)
        else:
            text = text.rstrip() + f"\n**Claude:** {runner}\n"
        _ME_MD.write_text(text)
    else:
        _ME_MD.write_text(
            "> Personal context. Not committed to git.\n\n"
            "# Me\n\n"
            f"**Claude:** {runner}\n"
        )


def _cli_available() -> bool:
    return subprocess.run(["claude", "--version"], capture_output=True).returncode == 0


def prompt_runner() -> str:
    """
    Ask the user which backend to use, save to ME.md, and return the choice.
    Called automatically on first use if ME.md has no preference.
    """
    print("\n  How should Claude be invoked?\n")
    print("  1. Claude Code  (recommended) — `claude -p`, uses Claude Code login, no API key")
    print("  2. API key      — Anthropic SDK, reads ANTHROPIC_API_KEY from environment\n")

    if not _cli_available():
        print("  (claude CLI not found in PATH — defaulting to api-key)\n")
        runner = "api-key"
    else:
        choice = input("  Choice [1]: ").strip() or "1"
        runner = "api-key" if choice == "2" else "claude-code"

    save_runner(runner)
    label = "`claude -p` (Claude Code)" if runner == "claude-code" else "Anthropic SDK (ANTHROPIC_API_KEY)"
    print(f"  Using {label}. Saved to ME.md.\n")
    return runner


def get_runner() -> str:
    """Return the configured runner, asking once if not yet set."""
    return read_runner() or prompt_runner()


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------

def _call_cli(prompt: str, print_output: bool) -> str:
    """Run `claude -p <prompt>`, stream output line by line."""
    proc = subprocess.Popen(
        ["claude", "-p", prompt],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    result = ""
    for line in proc.stdout:
        result += line
        if print_output:
            print(line, end="", flush=True)
    proc.wait()
    if proc.returncode != 0:
        err = proc.stderr.read().strip()
        raise RuntimeError(f"`claude -p` failed (exit {proc.returncode}): {err}")
    return result.strip()


def _call_api(prompt: str, max_tokens: int, print_output: bool) -> str:
    """Call the Anthropic SDK with streaming."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        print("\n  ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        print("  Set it with: export ANTHROPIC_API_KEY=sk-ant-...", file=sys.stderr)
        print("  Or switch to Claude Code runner by editing **Claude:** in ME.md.\n", file=sys.stderr)
        sys.exit(1)

    try:
        import anthropic
    except ImportError:
        print("\n  anthropic package not installed. Run: pip install anthropic\n", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    result = ""
    with client.messages.stream(
        model=_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            result += text
            if print_output:
                print(text, end="", flush=True)
    if print_output:
        print()
    return result.strip()


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def call_claude(
    prompt: str,
    max_tokens: int = 1024,
    print_output: bool = True,
) -> str:
    """
    Call Claude using the configured backend.
    Returns the full response text.
    """
    runner = get_runner()
    if runner == "claude-code":
        return _call_cli(prompt, print_output)
    return _call_api(prompt, max_tokens, print_output)
