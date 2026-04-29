#!/usr/bin/env python3
"""Mechanical inserter for sibling-map updates.

When a new skill `<new>` is a neighbour of an existing skill `<sibling>`, the
sibling's eval set needs two updates:

  1. Append N new `should_trigger=false` entries to misc/evals/<sibling>/triggering.json
     that phrase requests which should route to <new> (not to <sibling>).
     The script computes the 1-based indices of the new entries.

  2. Insert a new bullet into misc/evals/<sibling>/README.md's SIBLING_MAP block
     with the format the parser in run_all_evals.py expects:

         - **`<new>`** (<scope>) — negatives N, M ("<first-prompt-snippet>").

The script handles index math and markdown shape. It does NOT decide who is a
sibling — that is agent+author judgment in the new-skill workflow's Phase 3.
It does NOT compose the scope blurb or the negative-prompt phrasings — the
agent composes both, the script just inserts.

Refuses to run if:
  - SIBLING_MAP markers missing from the sibling's README
  - A bullet for <new> already exists in the SIBLING_MAP block
  - triggering.json is malformed
  - the sibling dir does not exist

Usage:
  python update_sibling_map.py \\
      --new-skill rds-best-practices \\
      --target-sibling eks-best-practices \\
      --scope "static RDS domain knowledge" \\
      --negative-prompt "Should I use Aurora or RDS for Postgres?" \\
      --negative-prompt "What's the right RDS parameter group for high TPS?"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EVALS_ROOT = Path(__file__).resolve().parent.parent
SIBLING_MAP_START = "<!-- SIBLING_MAP_START -->"
SIBLING_MAP_END = "<!-- SIBLING_MAP_END -->"


def fail(msg: str) -> "None":
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def _snippet(text: str, max_len: int = 40) -> str:
    """First max_len chars of a prompt, for the quoted snippet in the bullet."""
    t = text.strip().replace("\n", " ")
    return t if len(t) <= max_len else t[: max_len - 1].rstrip() + "…"


def _indices_phrase(indices: "list[int]") -> str:
    """Render [9, 10, 11] as 'negatives 9, 10, 11'. Always use comma form —
    ranges like '9-11' are supported by the parser, but the comma form keeps
    the insertion deterministic and easy to audit.
    """
    if len(indices) == 1:
        return f"negative {indices[0]}"
    return "negatives " + ", ".join(str(i) for i in indices)


def append_negatives_to_triggering(
    triggering_path: Path, negative_prompts: "list[str]"
) -> "list[int]":
    """Append negative entries and return their 1-based indices."""
    try:
        data = json.loads(triggering_path.read_text())
    except FileNotFoundError:
        fail(f"triggering.json not found at {triggering_path}")
    except json.JSONDecodeError as e:
        fail(f"triggering.json is not valid JSON: {e}")

    if not isinstance(data, list):
        fail("triggering.json root must be a JSON array")

    start_index_1based = len(data) + 1
    new_indices: "list[int]" = []
    for i, prompt in enumerate(negative_prompts):
        data.append({"query": prompt, "should_trigger": False})
        new_indices.append(start_index_1based + i)

    triggering_path.write_text(json.dumps(data, indent=2) + "\n")
    return new_indices


def bullet_already_present(readme_text: str, new_skill: str) -> bool:
    """Does a bullet for new_skill already exist in the SIBLING_MAP block?"""
    start = readme_text.find(SIBLING_MAP_START)
    end = readme_text.find(SIBLING_MAP_END)
    if start == -1 or end == -1:
        return False
    block = readme_text[start:end]
    # Match both `**\`new-skill\`**` and `**new-skill**` shapes.
    pat = re.compile(
        r"^-\s+\*\*`?" + re.escape(new_skill) + r"`?\*\*",
        re.MULTILINE,
    )
    return bool(pat.search(block))


def insert_bullet(
    readme_path: Path,
    new_skill: str,
    scope: str,
    indices: "list[int]",
    first_prompt_snippet: str,
) -> None:
    """Insert a new bullet just before the SIBLING_MAP_END marker."""
    text = readme_path.read_text()

    start = text.find(SIBLING_MAP_START)
    end = text.find(SIBLING_MAP_END)
    if start == -1 or end == -1 or end < start:
        fail(
            f"SIBLING_MAP markers not found in {readme_path} — "
            "add them before running this helper"
        )
    if bullet_already_present(text, new_skill):
        fail(
            f"SIBLING_MAP in {readme_path} already has a bullet for "
            f"`{new_skill}` — remove it first or edit it by hand"
        )

    bullet = (
        f"- **`{new_skill}`** ({scope}) — "
        f"{_indices_phrase(indices)} "
        f'("{_snippet(first_prompt_snippet)}").'
    )

    # Splice the bullet just before the END marker. Preserve existing block
    # trailing whitespace shape — if the block already ends with a newline
    # before the END marker, keep it; otherwise insert one.
    block = text[start + len(SIBLING_MAP_START) : end]
    if block.endswith("\n"):
        new_block = block + bullet + "\n"
    else:
        new_block = block + "\n" + bullet + "\n"

    new_text = (
        text[: start + len(SIBLING_MAP_START)]
        + new_block
        + text[end:]
    )
    readme_path.write_text(new_text)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Insert a sibling-map bullet + append negative prompts for a new skill."
    )
    parser.add_argument(
        "--new-skill",
        required=True,
        help="Slug of the new skill being added (the neighbour's perspective).",
    )
    parser.add_argument(
        "--target-sibling",
        required=True,
        help="Slug of the existing sibling whose eval set this call updates.",
    )
    parser.add_argument(
        "--scope",
        required=True,
        help="One-line scope blurb for the new skill, inserted into the bullet.",
    )
    parser.add_argument(
        "--negative-prompt",
        action="append",
        required=True,
        help="A prompt that should route to the new skill (not to the sibling). "
        "Pass one or more times; each becomes one negative entry.",
    )
    args = parser.parse_args()

    target_dir = EVALS_ROOT / args.target_sibling
    if not target_dir.is_dir():
        fail(f"sibling eval dir not found: {target_dir}")

    triggering_path = target_dir / "triggering.json"
    readme_path = target_dir / "README.md"
    if not triggering_path.exists():
        fail(f"missing {triggering_path}")
    if not readme_path.exists():
        fail(f"missing {readme_path}")

    # Guard against double-insert before we touch any file.
    if bullet_already_present(readme_path.read_text(), args.new_skill):
        fail(
            f"SIBLING_MAP in {readme_path} already has a bullet for "
            f"`{args.new_skill}` — remove it first or edit it by hand"
        )

    new_indices = append_negatives_to_triggering(
        triggering_path, args.negative_prompt
    )
    insert_bullet(
        readme_path,
        new_skill=args.new_skill,
        scope=args.scope,
        indices=new_indices,
        first_prompt_snippet=args.negative_prompt[0],
    )

    print(
        f"✓ {args.target_sibling}: appended {len(new_indices)} negative(s) "
        f"at {new_indices}, inserted SIBLING_MAP bullet for `{args.new_skill}`"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
