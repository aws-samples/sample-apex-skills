#!/usr/bin/env python3
"""Render SIBLING_MAP placeholder bullets in a freshly scaffolded README.md.

Called by `make init-evals SKILL=<name> SIBLINGS="a,b,c"`. Replaces the
two generic placeholder bullets inside the SIBLING_MAP block with one
placeholder bullet per sibling, each keyed to the sibling's slug.

The agent or author still has to:
  - fill in the scope blurb inside each bullet
  - add negative prompts to triggering.json via update_sibling_map.py
    (or hand-edit) and splice the resulting indices into each bullet

This script handles only the mechanical "stamp N bullets with the right
slugs" step — it does not write to triggering.json and does not assign
indices (there are no negatives to attribute yet at scaffold time).

Usage:
  render_siblings.py --readme <path> --siblings "slug-a,slug-b,slug-c"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SIBLING_MAP_START = "<!-- SIBLING_MAP_START -->"
SIBLING_MAP_END = "<!-- SIBLING_MAP_END -->"


def render(readme_path: Path, sibling_slugs: "list[str]") -> None:
    text = readme_path.read_text()
    start = text.find(SIBLING_MAP_START)
    end = text.find(SIBLING_MAP_END)
    if start == -1 or end == -1 or end < start:
        print(
            f"error: SIBLING_MAP markers not found in {readme_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    bullets = "\n".join(
        f"- **`{slug}`** (<REPLACE: one-line scope>) — "
        f"negatives <REPLACE: indices> "
        f'("<REPLACE: short quoted near-miss phrase>").'
        for slug in sibling_slugs
    )

    new_text = (
        text[: start + len(SIBLING_MAP_START)]
        + "\n"
        + bullets
        + "\n"
        + text[end:]
    )
    readme_path.write_text(new_text)
    print(
        f"✓ rendered {len(sibling_slugs)} sibling placeholder(s) in {readme_path}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--readme", required=True, type=Path)
    parser.add_argument(
        "--siblings",
        required=True,
        help='Comma-separated slugs, e.g. "eks-best-practices,eks-upgrader".',
    )
    args = parser.parse_args()

    slugs = [s.strip() for s in args.siblings.split(",") if s.strip()]
    if not slugs:
        print("error: --siblings must contain at least one slug", file=sys.stderr)
        return 1

    render(args.readme, slugs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
