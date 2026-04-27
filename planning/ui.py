"""Shared UI helpers: formatting, prompts, and the timed spinner."""

import threading
import time


def hr(char: str = "─", width: int = 60) -> str:
    return char * width


def header(title: str) -> None:
    print(f"\n{hr()}")
    print(f"  {title}")
    print(hr())


def prompt_section(key: str, title: str, question: str, existing: str | None) -> str:
    header(title)
    print(f"\n  {question}")

    if existing:
        print(f"\n  Current answer:\n")
        for line in existing.splitlines():
            print(f"    {line}")
        print()
        keep = input("  Keep this? [Y/n]: ").strip().lower()
        if keep != "n":
            return existing

    print()
    lines: list[str] = []
    print("  (Enter your answer. Blank line to finish.)\n")
    while True:
        line = input("  > ")
        if line == "":
            break
        lines.append(line)

    return "\n".join(lines)


def timed_call(fn, label: str) -> str:
    """Run fn() in a background thread while showing a live elapsed timer."""
    result: list = [None]
    error: list = [None]
    done = threading.Event()

    def _worker():
        try:
            result[0] = fn()
        except Exception as e:
            error[0] = e
        finally:
            done.set()

    threading.Thread(target=_worker, daemon=True).start()

    spinners = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    start = time.time()
    i = 0
    while not done.wait(0.1):
        elapsed = int(time.time() - start)
        m, s = divmod(elapsed, 60)
        ts = f"{m}:{s:02d}" if m else f"{s}s"
        print(f"\r  {spinners[i % len(spinners)]}  {label}  [{ts}]   ", end="", flush=True)
        i += 1

    elapsed = int(time.time() - start)
    m, s = divmod(elapsed, 60)
    ts = f"{m}:{s:02d}" if m else f"{s}s"
    print(f"\r  ✓  {label}  [{ts}]                    ")

    if error[0]:
        raise error[0]
    return result[0]
