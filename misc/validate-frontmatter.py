#!/usr/bin/env python3
"""Validate SKILL.md frontmatter: parseable YAML, description present and <= 1024 chars, manifest sync."""

import json
import os
import sys
from glob import glob

import yaml


def extract_frontmatter(path):
    """Extract frontmatter YAML string using line-based delimiter detection."""
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    if not lines or lines[0].rstrip() != "---":
        return None
    fm_lines = []
    for line in lines[1:]:
        if line.rstrip() == "---":
            return "".join(fm_lines)
        fm_lines.append(line)
    return None


def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    patterns = [
        os.path.join(repo_root, "skills", "*", "SKILL.md"),
        os.path.join(repo_root, "devops-agent", "*", "SKILL.md"),
    ]

    manifest_path = os.path.join(repo_root, "misc", "website", "static", "manifests", "skills.json")
    manifest_by_name = {}
    if not os.path.isfile(manifest_path):
        print(f"ERROR: skills.json manifest not found at {manifest_path}")
        sys.exit(1)
    try:
        with open(manifest_path, encoding="utf-8") as f:
            for entry in json.load(f):
                manifest_by_name[entry["name"]] = entry["description"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"ERROR: could not parse skills.json manifest ({e})")
        sys.exit(1)

    errors = []
    warnings = []
    count = 0

    # M3: check manifest entries for over-length or invalid descriptions
    for name, manifest_desc in manifest_by_name.items():
        if not isinstance(manifest_desc, str):
            errors.append(f"skills.json[{name}]: manifest description is not a string ({type(manifest_desc).__name__})")
        elif len(manifest_desc) > 1024:
            errors.append(f"skills.json[{name}]: manifest description too long ({len(manifest_desc)} chars, max 1024)")

    for pattern in patterns:
        for path in sorted(glob(pattern)):
            count += 1
            rel = os.path.relpath(path, repo_root)

            try:
                raw = extract_frontmatter(path)
                if raw is None:
                    errors.append(f"{rel}: no YAML frontmatter block found (missing closing '---')")
                    continue

                data = yaml.safe_load(raw)

                if not isinstance(data, dict):
                    errors.append(f"{rel}: frontmatter is not a mapping")
                    continue

                desc = data.get("description")
                if desc is None:
                    errors.append(f"{rel}: missing 'description' key")
                    continue

                if not isinstance(desc, str):
                    errors.append(f"{rel}: 'description' must be a string, got {type(desc).__name__}")
                    continue

                if len(desc) > 1024:
                    errors.append(f"{rel}: description too long ({len(desc)} chars, max 1024)")

                name = data.get("name")
                if not name or not isinstance(name, str):
                    errors.append(f"{rel}: missing or invalid 'name' key")
                    continue
                is_devops_agent = rel.startswith("devops-agent/")

                if not is_devops_agent and name in manifest_by_name:
                    if desc != manifest_by_name[name]:
                        errors.append(f"{rel}: description does not match skills.json manifest (run update-pages.sh)")
                elif not is_devops_agent and name not in manifest_by_name:
                    warnings.append(f"{rel}: no manifest entry for '{name}' (not in skills.json)")

            except yaml.YAMLError as e:
                errors.append(f"{rel}: YAML parse error: {e}")
            except Exception as e:
                errors.append(f"{rel}: unexpected error: {e}")

    for w in warnings:
        print(f"WARN: {w}")
    for e in errors:
        print(f"ERROR: {e}")

    if errors:
        print(f"\n{count} skills checked, {len(errors)} error(s)")
        sys.exit(1)
    else:
        print(f"\n{count} skills validated, 0 errors")
        sys.exit(0)


if __name__ == "__main__":
    main()
