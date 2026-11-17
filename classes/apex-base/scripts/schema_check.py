#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml>=6,<7"]
# ///
"""Check a JSON or YAML document against a JSON Schema (apex-base class tool).

The shared loader and checker the class validators import:
validate_input.py (apex-base), validate_output.py and k_run_diff.py (script)
and run_artifact_checks.py (operator).

The checker is standard library only and covers the subset of JSON Schema
draft 2020-12 that APEX schemas use: type, const, enum, required,
properties, additionalProperties, items, minItems, minLength, maxLength,
pattern, format (date-time only, asserted), anyOf, oneOf, local $ref into
$defs, and the annotations $schema, $id, $comment, title, description,
examples and default. A schema that uses any other keyword is refused
(exit 2), so an unsupported rule never passes silently. YAML is read with
PyYAML's safe loader (pyyaml, the one package the repo's CI already
installs); a duplicate mapping key is refused.

Usage:
  schema_check.py --schema <schema.json> <file>...
  schema_check.py --check-schema <schema.json>...

Exit codes: 0 every file validates; 1 a file does not validate;
2 the check could not run (missing or unreadable file, empty document,
parse error, unsupported schema). Nothing ever exits 0 on absent input.
"""
import argparse
import json
import os
import re
import sys

DRAFT = "https://json-schema.org/draft/2020-12/schema"
ANNOTATIONS = {"$schema", "$id", "$comment", "title", "description", "examples", "default"}
ASSERTIONS = {
    "type", "const", "enum", "required", "properties", "additionalProperties",
    "items", "minItems", "minLength", "maxLength", "pattern", "format",
    "anyOf", "oneOf", "$ref", "$defs",
}
TYPES = {"null", "boolean", "object", "array", "number", "integer", "string"}
DATE_TIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$")


class CheckError(Exception):
    """The check cannot run: exit 2."""


def _yaml():
    try:
        import yaml  # noqa: PLC0415
    except ImportError:
        raise CheckError("PyYAML is not installed (pip install 'pyyaml>=6,<7')")
    return yaml


def _no_dup_pairs(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise CheckError(f"duplicate key {k!r}")
        out[k] = v
    return out


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
            if key in out:
                raise CheckError(f"duplicate key {key!r} at line {knode.start_mark.line + 1}")
            out[key] = loader.construct_object(vnode, deep=deep)
        return out

    Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    try:
        return yaml.load(text, Loader=Loader)  # noqa: S506 (SafeLoader subclass)
    except CheckError as e:
        raise CheckError(f"{name}: {e}")
    except yaml.YAMLError as e:
        raise CheckError(f"{name}: not valid YAML: {e}")


def load(path):
    """Read and parse one JSON or YAML file."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        raise CheckError(f"{path}: cannot read: {e}")
    return loads(text, path)


def check_schema(schema, where="#"):
    """Refuse a schema that uses a keyword this checker does not implement."""
    if isinstance(schema, bool):
        return
    if not isinstance(schema, dict):
        raise CheckError(f"schema {where}: must be an object or a boolean")
    if where == "#" and schema.get("$schema", DRAFT) != DRAFT:
        raise CheckError(f"schema: $schema must be {DRAFT}")
    for key, val in schema.items():
        if key in ANNOTATIONS:
            continue
        if key not in ASSERTIONS:
            raise CheckError(f"schema {where}: unsupported keyword {key!r}")
        if key in ("properties", "$defs"):
            for name, sub in val.items():
                check_schema(sub, f"{where}/{key}/{name}")
        elif key in ("anyOf", "oneOf"):
            if not isinstance(val, list) or not val:
                raise CheckError(f"schema {where}/{key}: must be a non-empty list")
            for i, sub in enumerate(val):
                check_schema(sub, f"{where}/{key}/{i}")
        elif key in ("items", "additionalProperties"):
            check_schema(val, f"{where}/{key}")
        elif key == "type":
            names = val if isinstance(val, list) else [val]
            if not names or any(n not in TYPES for n in names):
                raise CheckError(f"schema {where}/type: unknown type {val!r}")
        elif key == "format" and val != "date-time":
            raise CheckError(f"schema {where}: unsupported format {val!r}")
        elif key == "$ref" and not (isinstance(val, str) and val.startswith("#/")):
            raise CheckError(f"schema {where}: only local $ref ('#/...') is supported")
        elif key == "pattern":
            try:
                re.compile(val)
            except re.error as e:
                raise CheckError(f"schema {where}/pattern: {e}")


def _type_name(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__  # e.g. a YAML timestamp loads as datetime


def _is_type(value, name):
    actual = _type_name(value)
    return actual == name or (name == "number" and actual == "integer")


def _resolve(root, ref):
    node = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            raise CheckError(f"schema: $ref {ref} does not resolve")
        node = node[part]
    return node


def _equal(a, b):
    return _type_name(a) == _type_name(b) and a == b


def validate(instance, schema, root=None, path="$"):
    """Return a list of 'path: message' errors; empty means valid."""
    root = schema if root is None else root
    if schema is True:
        return []
    if schema is False:
        return [f"{path}: not allowed here"]
    errors = []
    if "$ref" in schema:
        errors += validate(instance, _resolve(root, schema["$ref"]), root, path)
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is_type(instance, n) for n in names):
            return errors + [f"{path}: expected {' or '.join(names)}, got {_type_name(instance)}"]
    if "const" in schema and not _equal(instance, schema["const"]):
        errors.append(f"{path}: must equal {json.dumps(schema['const'])}")
    if "enum" in schema and not any(_equal(instance, e) for e in schema["enum"]):
        errors.append(f"{path}: {json.dumps(instance, default=str)} is not one of {json.dumps(schema['enum'])}")
    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            errors.append(f"{path}: shorter than {schema['minLength']} characters")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{path}: longer than {schema['maxLength']} characters")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: does not match pattern {schema['pattern']}")
        if schema.get("format") == "date-time" and not DATE_TIME.match(instance):
            errors.append(f"{path}: not an RFC 3339 date-time")
    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: missing required key {key!r}")
        props = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for key, val in instance.items():
            sub = f"{path}.{key}"
            if key in props:
                errors += validate(val, props[key], root, sub)
            elif extra is False:
                errors.append(f"{path}: unexpected key {key!r}")
            elif isinstance(extra, dict):
                errors += validate(val, extra, root, sub)
    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        if "items" in schema:
            for i, val in enumerate(instance):
                errors += validate(val, schema["items"], root, f"{path}[{i}]")
    for key in ("anyOf", "oneOf"):
        if key not in schema:
            continue
        results = [validate(instance, sub, root, path) for sub in schema[key]]
        passed = sum(1 for r in results if not r)
        if passed == 0:
            best = min(results, key=len)
            errors.append(f"{path}: matches none of the {len(results)} {key} alternatives; nearest fails on:")
            errors += ["  " + e for e in best]
        elif key == "oneOf" and passed > 1:
            errors.append(f"{path}: matches {passed} oneOf alternatives, expected exactly 1")
    return errors


def load_schema(path):
    schema = load(path)
    check_schema(schema)
    return schema


def check_files(schema_path, files, out=sys.stdout):
    """Validate each file; print one result line per file. Return the exit code."""
    schema = load_schema(schema_path)
    rc = 0
    for f in files:
        errors = validate(load(f), schema)
        if errors:
            rc = 1
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


def run_declared(key, argv, script_file, inline_json=False):
    """CLI shared by validate_input.py and validate_output.py."""
    p = argparse.ArgumentParser(description=f"Check a document against the skill's metadata.{key} schema.")
    p.add_argument("--skill-dir", help="skill folder (default: the folder this copied tool sits in)")
    p.add_argument("--schema", help="schema path, instead of the skill's declared one")
    if inline_json:
        p.add_argument("--json", dest="inline", help="the document as inline JSON text")
    p.add_argument("files", nargs="*")
    args = p.parse_args(argv)
    try:
        if args.schema:
            schema_path = args.schema
        else:
            skill_dir = args.skill_dir or default_skill_dir(script_file)
            if not skill_dir:
                raise CheckError("give --skill-dir or --schema")
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
        return check_files(schema_path, args.files)
    except CheckError as e:
        print(f"cannot check: {e}", file=sys.stderr)
        return 2


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--schema", help="the JSON Schema to check the files against")
    g.add_argument("--check-schema", action="store_true", help="only check that each file is a supported schema")
    p.add_argument("files", nargs="+")
    args = p.parse_args(argv)
    try:
        if args.check_schema:
            for f in args.files:
                load_schema(f)
                print(f"ok schema {f}")
            return 0
        return check_files(args.schema, args.files)
    except CheckError as e:
        print(f"cannot check: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
