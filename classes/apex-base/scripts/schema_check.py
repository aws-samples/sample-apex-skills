#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["jsonschema[format-nongpl]>=4.26,<5", "pyyaml>=6,<7"]
# ///
"""Check a JSON or YAML document against a JSON Schema (apex-base class tool).

A library, not a command: it has no command line of its own and prints
nothing when run. Run the tools that import it.

The shared loader and checker the class validators import:
validate_input.py (apex-base), validate_output.py and k_run_diff.py (script)
and run_artifact_checks.py (operator).

The checker is the jsonschema package's Draft 2020-12 validator, with its
format checker, so `format` is asserted (the format-nongpl extra brings the
date-time checker). The format checks need `jsonschema[format-nongpl]`;
without that extra a bad date-time passes. YAML is read with PyYAML's safe
loader; a duplicate or unhashable mapping key is refused.

Exit codes of the tools that import it: 0 every file validates; 1 a file
does not validate; 2 the check could not run (missing or unreadable file,
empty document, parse error, a schema that fails the Draft 2020-12
metaschema check, a $ref an instance reaches that does not resolve (a $ref
is resolved only when an instance reaches it), jsonschema not installed, a
schema or document nested too deep). Nothing ever exits 0 on absent input.
"""
import argparse
import json
import os
import re
import sys
import time


class CheckError(Exception):
    """The check cannot run: exit 2."""


def _yaml():
    try:
        import yaml  # noqa: PLC0415
    except ImportError:
        raise CheckError("PyYAML is not installed (pip install 'pyyaml>=6,<7')")
    return yaml


def _jsonschema():
    try:
        import jsonschema  # noqa: PLC0415
        import referencing.exceptions  # noqa: PLC0415 (installed with jsonschema)
    except ImportError:
        raise CheckError("jsonschema is not installed (pip install 'jsonschema[format-nongpl]>=4.26,<5')")
    return jsonschema, referencing.exceptions


def _no_dup_pairs(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise CheckError("duplicate key in a JSON object")
        out[k] = v
    return out


def _yaml_problem(e):
    """Where the YAML fails to parse and why, without the document text PyYAML's
    message quotes: its snippet is dropped, and each quoted span (a tag or alias
    name) becomes '...'. The document may be hostile, and stderr is not wrapped."""
    parts = []
    for what, mark in ((getattr(e, "context", None), getattr(e, "context_mark", None)),
                       (getattr(e, "problem", None), getattr(e, "problem_mark", None))):
        what = re.sub(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"", "'...'", what or "")
        if mark is not None:
            what = f"{what} at line {mark.line + 1}, column {mark.column + 1}".strip()
        if what:
            parts.append(what)
    return ": ".join(parts) or type(e).__name__


def loads(text, name="<input>", fmt=None):
    """Parse JSON or YAML text into one document. fmt is 'json', 'yaml' or None (by name)."""
    if not text.strip():
        raise CheckError(f"{name}: empty document")
    if fmt is None:
        fmt = "json" if name.endswith(".json") else "yaml"
    if fmt == "json":
        try:
            return json.loads(text, object_pairs_hook=_no_dup_pairs)
        except CheckError as e:
            raise CheckError(f"{name}: {e}")
        except ValueError as e:
            raise CheckError(f"{name}: not valid JSON: {e}")
    yaml = _yaml()

    class Loader(yaml.SafeLoader):
        pass

    def mapping(loader, node, deep=False):
        loader.flatten_mapping(node)
        out = {}
        for knode, vnode in node.value:
            key = loader.construct_object(knode, deep=deep)
            try:
                hash(key)
            except TypeError:
                raise CheckError(f"unhashable key at line {knode.start_mark.line + 1}")
            if key in out:
                raise CheckError(f"duplicate key at line {knode.start_mark.line + 1}, column {knode.start_mark.column + 1}")
            out[key] = loader.construct_object(vnode, deep=deep)
        return out

    Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    try:
        doc = yaml.load(text, Loader=Loader)  # noqa: S506 (SafeLoader subclass)
    except CheckError as e:
        raise CheckError(f"{name}: {e}")
    except yaml.YAMLError as e:
        raise CheckError(f"{name}: not valid YAML: {_yaml_problem(e)}")
    if doc is None:
        raise CheckError(f"{name}: empty document")
    return doc


def load(path):
    """Read and parse one JSON or YAML file."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        raise CheckError(f"{path}: cannot read: {e}")
    return loads(text, path)


def check_schema(schema):
    """Refuse a schema that is not valid Draft 2020-12."""
    jsonschema, _ = _jsonschema()
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
    except jsonschema.exceptions.SchemaError as e:
        raise CheckError(f"schema is not valid Draft 2020-12: {e.message}")


def validate(instance, schema):
    """Return a list of 'path: message' errors; empty means valid.

    An anyOf or oneOf failure reports only "is not valid under any of the
    given schemas", not the branch errors; no shipped schema uses either."""
    jsonschema, ref_errors = _jsonschema()
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    try:
        errors = list(validator.iter_errors(instance))
    except ref_errors.Unresolvable as e:
        raise CheckError(f"schema: $ref does not resolve: {e}")
    return sorted(f"{e.json_path}: {e.message}{_quote_hint(e)}" for e in errors)


def _quote_hint(e):
    """A hint for a value YAML read as a number, boolean or date where the schema wants a string."""
    import datetime  # noqa: PLC0415
    wants = e.validator_value if isinstance(e.validator_value, list) else [e.validator_value]
    if e.validator == "type" and "string" in wants and isinstance(
            e.instance, (int, float, bool, datetime.date)):
        return f" (YAML read it as {type(e.instance).__name__}; quote it)"
    return ""


def load_schema(path):
    schema = load(path)
    check_schema(schema)
    return schema


def check_files(schema_path, files, out=None):
    """Validate each file; print one result line per file. Return the worst exit code."""
    out = out if out is not None else sys.stdout
    schema = load_schema(schema_path)
    rc = 0
    for f in files:
        try:
            errors = validate(load(f), schema)
        except CheckError as e:
            rc = 2
            print(f"cannot check: {e}", file=sys.stderr)
            continue
        if errors:
            rc = max(rc, 1)
            print(f"FAIL {f} against {schema_path}", file=out)
            for e in errors:
                print(f"  {e}", file=out)
        else:
            print(f"ok {f} against {schema_path}", file=out)
    return rc


def skill_metadata(skill_dir):
    """Return the metadata mapping from a skill's SKILL.md frontmatter."""
    path = os.path.join(skill_dir, "SKILL.md")
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except (OSError, UnicodeDecodeError) as e:
        raise CheckError(f"{path}: cannot read: {e}")
    if not lines or lines[0].strip() != "---" or "---" not in [ln.strip() for ln in lines[1:]]:
        raise CheckError(f"{path}: no frontmatter block")
    end = [ln.strip() for ln in lines[1:]].index("---") + 1
    front = loads("\n".join(lines[1:end]) or "{}", path, "yaml") or {}
    meta = front.get("metadata") if isinstance(front, dict) else None
    if meta is None:
        return {}
    if not isinstance(meta, dict):
        raise CheckError(f"{path}: frontmatter metadata is not a mapping")
    return meta


def declared_schema(skill_dir, key):
    """Resolve a skill's declared schema path (metadata.<key>), which must sit in its assets/."""
    rel = skill_metadata(skill_dir).get(key)
    if not isinstance(rel, str) or not rel:
        raise CheckError(f"{skill_dir}/SKILL.md: metadata.{key} is not declared")
    assets = os.path.realpath(os.path.join(skill_dir, "assets"))
    full = os.path.realpath(os.path.join(skill_dir, rel))
    if os.path.isabs(rel) or not full.startswith(assets + os.sep):
        raise CheckError(f"{skill_dir}/SKILL.md: metadata.{key} must be a path inside the skill's assets/: {rel}")
    return full


def default_skill_dir(script_file):
    """The skill folder holding a copied tool (<skill>/scripts/<tool>.py), or None."""
    cand = os.path.dirname(os.path.dirname(os.path.abspath(script_file)))
    return cand if os.path.isfile(os.path.join(cand, "SKILL.md")) else None


def record_run(script_file, skill_dir, files):
    """Leave a run record for the operator Stop gate (classes/script/hooks/stop-gate/stop_gate.py).

    The record names paths only, never a verdict: the gate re-runs the tool
    itself, when it is one the gate runs (stop_gate.py stale() and tool_kind()). One JSON
    file run-<ns>-<pid>.json in <root>/.apex-stop-gate/, root the nearest
    folder at or above the working folder holding .git (else the working
    folder). The tool writes only into an existing .apex-stop-gate folder
    there, never through a link (the gate makes it at each Stop it runs with
    its switch on); the gate ignores one that is not a real folder this user
    owns with no group or other write bit, so no run recorded there is checked.
    Best effort: an OSError is ignored. The gate's own re-run sets
    APEX_STOP_GATE_RUN, and then no record is written."""
    if os.environ.get("APEX_STOP_GATE_RUN"):
        return
    try:
        cwd = os.getcwd()
        root = cwd
        while not os.path.exists(os.path.join(root, ".git")) and os.path.dirname(root) != root:
            root = os.path.dirname(root)
        if not os.path.exists(os.path.join(root, ".git")):
            root = cwd
        folder = os.path.join(root, ".apex-stop-gate")
        if not os.path.isdir(folder) or os.path.islink(folder):
            return
        rec = {"tool": os.path.abspath(script_file), "skill_dir": os.path.abspath(skill_dir),
               "files": [os.path.abspath(f) for f in files], "cwd": cwd, "time": time.time()}
        with open(os.path.join(folder, f"run-{time.time_ns()}-{os.getpid()}.json"), "x", encoding="utf-8") as f:
            json.dump(rec, f)
    except OSError:
        pass


def run_declared(key, argv, script_file, inline_json=False):
    """CLI shared by validate_input.py and validate_output.py."""
    p = argparse.ArgumentParser(description=f"Check a document against the skill's metadata.{key} schema.")
    p.add_argument("--skill-dir", help="skill folder (default: the folder this copied tool sits in)")
    if inline_json:
        p.add_argument("--json", dest="inline", help="the document as inline JSON text")
    p.add_argument("files", nargs="*")
    args = p.parse_args(argv)
    try:
        skill_dir = args.skill_dir or default_skill_dir(script_file)
        if not skill_dir:
            raise CheckError("give --skill-dir")
        schema_path = declared_schema(skill_dir, key)
        inline = getattr(args, "inline", None)
        if inline is not None:
            if args.files:
                raise CheckError("give --json or files, not both")
            schema = load_schema(schema_path)
            errors = validate(loads(inline, "--json", "json"), schema)
            for e in errors:
                print(f"  {e}")
            print(("FAIL" if errors else "ok") + f" --json against {schema_path}")
            return 1 if errors else 0
        if not args.files:
            raise CheckError("no input given")
        if key == "apex-outputs":
            record_run(script_file, skill_dir, args.files)
        return check_files(schema_path, args.files)
    except CheckError as e:
        print(f"cannot check: {e}", file=sys.stderr)
        return 2
    except RecursionError:
        print("cannot check: the schema or the document is nested too deep", file=sys.stderr)
        return 2
