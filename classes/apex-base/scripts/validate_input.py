#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["jsonschema[format-nongpl]>=4.26,<5", "pyyaml>=6,<7"]
# ///
"""Check a skill's input against its declared input schema (apex-base class tool).

apex.declared-schemas: a skill declares its input schema in its frontmatter,
metadata.apex-inputs (a path in the skill's assets/), and checks its input
against it before it starts. The Operator class's input check is its
rules (operator.typed-input, operator.confirm-before-change), not code.

Usage (from a skill folder where the class sync copied this tool to
scripts/apex_base_validate_input.py, the skill folder is found by itself):
  validate_input.py [--skill-dir <skill>] --json '{"cluster_name": "c1", "region": "us-west-2"}'
  validate_input.py [--skill-dir <skill>] <input.json|input.yaml>...

It imports the apex-base class tool schema_check (the class sync (planned)
rewrites the import to the flat copy's name). In this repo, run it with
PYTHONPATH=classes/apex-base/scripts.
Exit codes: 0 valid; 1 invalid (do not start the task); 2 the check could not run.
"""
import sys

try:
    import schema_check
except ImportError:
    print("cannot check: the apex-base class tool schema_check is not installed beside this tool", file=sys.stderr)
    sys.exit(2)

if __name__ == "__main__":
    sys.exit(schema_check.run_declared("apex-inputs", sys.argv[1:], __file__, inline_json=True))
