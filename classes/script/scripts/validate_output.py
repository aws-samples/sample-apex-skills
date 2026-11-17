#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml>=6,<7"]
# ///
"""Check a Script skill's output against its declared output schema (script, piece 3).

script.output-schema: the script's own output validates against the JSON
Schema in the skill's assets/, declared in metadata.apex-outputs.
apex.validate-output: run this on the output before you hand it on.

Usage (from a skill folder where the class sync copied this tool to
scripts/script_validate_output.py, the skill folder is found by itself):
  validate_output.py [--skill-dir <skill>] <output.yaml|output.json>...
  validate_output.py --schema <schema.json> <output>...

It imports the apex-base class tool schema_check (the class sync rewrites the
import to the flat copy's name). In this repo, run it with
PYTHONPATH=classes/apex-base/scripts.
Exit codes: 0 valid; 1 invalid (do not hand it on); 2 the check could not run.
"""
import sys

import schema_check

if __name__ == "__main__":
    sys.exit(schema_check.run_declared("apex-outputs", sys.argv[1:], __file__))
