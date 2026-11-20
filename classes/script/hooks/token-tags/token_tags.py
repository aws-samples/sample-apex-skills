#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""script random-token tags (piece 4): mark a script's output with tags no output can forge.

A stdin filter tool, not a hook: nothing registers or runs it yet. The rule it
backs, script.token-tags (one sentence saying what the tags mean), is added to
classes/script/rules.md by a separate change, since that file is not this one's.
Taken from the
four google/skills cloud-trace-querying scripts (secrets.token_hex(8) per run,
and a tag line before the output and one after it; those scripts also have a
flag to leave the tags off, which this tool does not take). The tags mark the
output; they do not filter it. TOKEN is 16 random hex
characters, new on every run, so text inside the output cannot close the tag
early: it would have to guess TOKEN.

    <apex_script_output_TOKEN>
    ...the output, unchanged...
    </apex_script_output_TOKEN>

The Stop gate (stop_gate.py) wraps the check output it sends back to the agent
the same way: the shared tags block below is byte-identical in both files.

Usage:
  token_tags.py < output
      print stdin between the tags; exit 0
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
    parser.parse_args(argv)
    sys.stdout.write(wrap(sys.stdin.read()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
