#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""script random-token tags (piece 4): mark a script's output with tags no output can forge.

A stdin filter tool, not a hook: nothing registers or runs it yet, and the rule
it is meant to back, script.token-tags, is not in classes/script/rules.md yet
(its bullet is in P-318's carry, for P-321's rules.md change). Taken from the
four google/skills cloud-trace-querying scripts (secrets.token_hex(8) per run,
a tag line before the output and one after it, and a flag to leave the tags
off). The tags mark the output; they do not filter it. TOKEN is 16 random hex
characters, new on every run, so text inside the output cannot close the tag
early: it would have to guess TOKEN.

    <apex_script_output_TOKEN>
    ...the output, unchanged...
    </apex_script_output_TOKEN>

The Stop gate (stop_gate.py) wraps the check output it sends back to the agent
the same way: the shared tags block below is byte-identical in both files.

Usage:
  token_tags.py [--no-wrapper-tag]  < output
      print stdin between the tags (or unchanged with --no-wrapper-tag); exit 0
Exit 2 on a usage error.
"""

import argparse
import secrets
import sys

# --- shared tags: byte-identical in token_tags.py and stop_gate.py ------------
LABEL = "apex_script_output"


def wrap(text):
    """Return text between <LABEL_TOKEN> and </LABEL_TOKEN> lines, TOKEN random per call."""
    token = secrets.token_hex(8)
    body = text if not text or text.endswith("\n") else text + "\n"
    return f"<{LABEL}_{token}>\n{body}</{LABEL}_{token}>\n"
# --- end of the shared tags ---------------------------------------------------


def main(argv):
    parser = argparse.ArgumentParser(description="Wrap stdin in random-token tags.")
    parser.add_argument("--no-wrapper-tag", action="store_true", help="print stdin unchanged")
    args = parser.parse_args(argv)
    text = sys.stdin.read()
    sys.stdout.write(text if args.no_wrapper_tag else wrap(text))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
