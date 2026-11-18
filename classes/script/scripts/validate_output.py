#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["jsonschema[format-nongpl]>=4.26,<5", "pyyaml>=6,<7"]
# ///
"""Check a Script skill's output against its declared output schema (Script class tool).

script.output-schema: the script's own output validates against the JSON
Schema in the skill's assets/, declared in metadata.apex-outputs.
apex.validate-output: run this on the output before you hand it on.

Usage (from a skill folder where the class sync copied this tool to
scripts/script_validate_output.py, the skill folder is found by itself):
  validate_output.py [--skill-dir <skill>] <output.yaml|output.json>...

It imports the apex-base class tool schema_check (the class sync
rewrites the import to the flat copy's name). In this repo, run it with
PYTHONPATH=classes/apex-base/scripts.
Exit codes: 0 valid; 1 invalid (do not hand it on); 2 the check could not run.
"""
import sys

try:
    import schema_check
except ImportError:
    print("cannot check: the apex-base class tool schema_check is not installed beside this tool", file=sys.stderr)
    sys.exit(2)

if __name__ == "__main__":
    sys.exit(schema_check.run_declared("apex-outputs", sys.argv[1:], __file__))
