"""Phase 4: re-iterate review — gaps, risks, alternatives, clarifications."""

import re
from pathlib import Path

from claude_runner import call_claude_cli as call_claude
from ui import hr
from project_context import PROJECT_MD, SECTIONS, _project_summary, _stack_summary


REITERATE_PROMPT = """\
You are a senior software architect performing a structured plan review.

Project definition:
{summary}

Agreed tech stack:
{stack}

Review the plan across five lenses and produce a short, high-signal list of observations.

Lenses:

- GAP: something not considered that could cause real problems — missing requirements, \
operational concerns, security holes, scaling limits, edge cases, or integration risks.
- RISK: a specific thing that is likely to go wrong or take much longer than expected, \
with a concrete reason why (not generic "this is hard" warnings).
- MOTIVATION: a place where the chosen approach, tech, or scope does not obviously serve \
the stated motivation or success criteria — call out the mismatch and what would align better.
- ALTERNATIVE: a tech or design choice with a meaningful trade-off worth reconsidering, \
paired with a specific suggestion and why it might be a better fit.
- CLARIFY: a question where the answer would meaningfully change the plan or architecture.

Rules:
- Be specific. "Have you considered auth?" is too vague. Instead: "You mentioned user accounts \
but didn't specify social login vs email+password — this changes your auth library choice and \
adds an OAuth integration to scope."
- 5–9 items total across all lenses. Quality over quantity — only raise things that genuinely \
matter for this specific project.
- Do not repeat anything already addressed in the project definition.
- Prioritise RISK and MOTIVATION items if the plan has clear weak points there.
- Format exactly — one item per line, no blank lines between items, no extra text:

[GAP] observation
[RISK] observation
[MOTIVATION] observation
[ALTERNATIVE] observation
[CLARIFY] question
"""

ITEM_LABELS = {
    "GAP":         ("Gap",         "Something not considered that could cause problems"),
    "RISK":        ("Risk",        "Something likely to go wrong or take much longer than expected"),
    "MOTIVATION":  ("Motivation",  "A mismatch between the approach and the stated goals"),
    "ALTERNATIVE": ("Alternative", "Another approach worth weighing"),
    "CLARIFY":     ("Clarify",     "A question whose answer would change the plan"),
}


def _parse_reiterate(raw: str) -> list[dict]:
    items = []
    for line in raw.splitlines():
        line = line.strip()
        for tag in ITEM_LABELS:
            prefix = f"[{tag}]"
            if line.startswith(prefix):
                items.append({"tag": tag, "text": line[len(prefix):].strip()})
                break
    return items


def _append_clarifications(entries: list[dict]) -> None:
    existing = PROJECT_MD.read_text() if PROJECT_MD.exists() else ""
    existing = re.sub(r"\n## Review Notes\n[\s\S]*$", "", existing).rstrip()
    existing = re.sub(r"\n## Clarifications\n[\s\S]*$", "", existing).rstrip()

    block = "\n\n## Review Notes\n\n"
    for e in entries:
        label = ITEM_LABELS[e["tag"]][0]
        block += f"**[{label}]** {e['text']}\n\n"
        block += f"> {e['response']}\n\n"

    PROJECT_MD.write_text(existing + block)


def reiterate(sections: dict[str, str], components: list[dict]) -> None:
    summary = _project_summary(sections)
    stack = _stack_summary(components)

    print("\n" + hr("="))
    print("  Step 4: Re-iterate — Validation & Review")
    print(hr("="))
    print("\n  Reviewing your plan for weak points, risks, motivation alignment, and improvements...\n")

    raw = call_claude(REITERATE_PROMPT.format(summary=summary, stack=stack), max_tokens=1536)

    items = _parse_reiterate(raw)
    if not items:
        print("  Nothing significant to flag. Your plan looks solid.\n")
        return

    print(f"  Found {len(items)} item(s). Go through each — press Enter to skip.\n")

    responses: list[dict] = []
    for i, item in enumerate(items, 1):
        label, subtitle = ITEM_LABELS[item["tag"]]
        print(f"\n  {hr('·')}")
        print(f"  [{i}/{len(items)}]  {label.upper()}  —  {subtitle}")
        print(f"  {hr('·')}")
        print(f"\n  {item['text']}\n")

        answer = input("  Your response (or Enter to skip): ").strip()
        if answer:
            responses.append({**item, "response": answer})
            print("  Noted.")

    if responses:
        _append_clarifications(responses)
        print(f"\n  {len(responses)} response(s) saved to PROJECT.md.\n")
    else:
        print("\n  No responses recorded.\n")
