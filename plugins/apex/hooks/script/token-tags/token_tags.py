#!/usr/bin/env python3
# generated from classes/script/hooks/token-tags/token_tags.py, do not edit
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""script random-token tags (piece 4): mark a script's output with tags no output can forge.

Backs script.token-tags (classes/script/rules.md). Taken from the four
google/skills cloud-trace-querying scripts (secrets.token_hex(8) per run, a tag
line before the output and one after it, and a flag to leave the tags off).
The tags mark the output; they do not filter it. TOKEN is 16 random hex
characters, new on every run, so text inside the output cannot close the tag
early: it would have to guess TOKEN.

    <apex_script_output_TOKEN>
    ...the output, unchanged...
    </apex_script_output_TOKEN>

The Stop gate (stop_gate.py) wraps the check output it sends back to the agent
the same way: the shared tags block below is byte-identical in both files.

Usage:
  token_tags.py [--label <label>] [--no-wrapper-tag]  < output
      print stdin between the tags (or unchanged with --no-wrapper-tag); exit 0
  token_tags.py --check [--label <label>]  < tagged
      exit 0 when stdin is exactly one tagged block (opening line first,
      closing line last, the same TOKEN, and the token in no other line);
      exit 1 when it is not, with one stderr line per problem
Exit 2 on a usage error. <label> is lowercase letters, digits and _, starting
with a letter (default apex_script_output).
"""

import argparse
import re
import secrets
import sys

# --- shared tags: byte-identical in token_tags.py and stop_gate.py ------------
LABEL = "apex_script_output"


def wrap(text, label=LABEL, token=None):
    """Return text between <label_TOKEN> and </label_TOKEN> lines, TOKEN random per call."""
    token = token or secrets.token_hex(8)
    body = text if not text or text.endswith("\n") else text + "\n"
    return f"<{label}_{token}>\n{body}</{label}_{token}>\n"
# --- end of the shared tags ---------------------------------------------------


LABEL_RE = re.compile(r"[a-z][a-z0-9_]*\Z")


def problems(text, label=LABEL):
    """Return a list of reasons text is not exactly one tagged block; empty means it is."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if len(lines) < 2:
        return ["fewer than two lines: no opening and closing tag"]
    m = re.fullmatch(rf"<{re.escape(label)}_([0-9a-f]{{16}})>", lines[0])
    if not m:
        return [f"the first line is not <{label}_TOKEN> with a 16 hex character TOKEN"]
    token = m.group(1)
    out = []
    if lines[-1] != f"</{label}_{token}>":
        out.append(f"the last line is not </{label}_{token}>")
    inner = [n for n, line in enumerate(lines[1:-1], 2) if token in line]
    if inner:
        out.append(f"the token appears inside the output, line {inner[0]}")
    return out


def main(argv):
    parser = argparse.ArgumentParser(description="Wrap stdin in random-token tags, or check a tagged text.")
    parser.add_argument("--label", default=LABEL)
    parser.add_argument("--no-wrapper-tag", action="store_true", help="print stdin unchanged")
    parser.add_argument("--check", action="store_true", help="check stdin is one tagged block")
    args = parser.parse_args(argv)
    if not LABEL_RE.match(args.label):
        parser.error(f"--label {args.label!r}: lowercase letters, digits and _, starting with a letter")
    if args.check and args.no_wrapper_tag:
        parser.error("--check and --no-wrapper-tag do not go together")
    text = sys.stdin.read()
    if args.check:
        found = problems(text, args.label)
        for p in found:
            print(f"token tags: {p}", file=sys.stderr)
        return 1 if found else 0
    sys.stdout.write(text if args.no_wrapper_tag else wrap(text, args.label))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
