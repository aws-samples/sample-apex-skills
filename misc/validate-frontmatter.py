#!/usr/bin/env python3
"""Validate SKILL.md frontmatter: parseable YAML, description present and <= 1024 chars, manifest sync."""

import json
import os
import sys
from glob import glob

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from safe_frontmatter import FrontmatterError, load_frontmatter


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

    errors = []
    warnings = []
    count = 0

    manifest_path = os.path.join(repo_root, "misc", "website", "static", "manifests", "skills.json")
    manifest_by_name = {}
    if not os.path.isfile(manifest_path):
        print(f"ERROR: skills.json manifest not found at {manifest_path}")
        sys.exit(1)
    try:
        with open(manifest_path, encoding="utf-8") as f:
            for entry in json.load(f):
                if entry["name"] in manifest_by_name:
                    errors.append(f"skills.json: duplicate name '{entry['name']}'")
                manifest_by_name[entry["name"]] = entry["description"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"ERROR: could not parse skills.json manifest ({e})")
        sys.exit(1)

    # M3: check manifest entries for over-length or invalid descriptions
    for name, manifest_desc in manifest_by_name.items():
        if not isinstance(manifest_desc, str):
            errors.append(f"skills.json[{name}]: manifest description is not a string ({type(manifest_desc).__name__})")
        elif len(manifest_desc) > 1024:
            errors.append(f"skills.json[{name}]: manifest description too long ({len(manifest_desc)} chars, max 1024)")

    for pattern in patterns:
        # devops-agent/ and skills/ are separate namespaces — a name may
        # legitimately appear in both. Only flag duplicates within one scope.
        seen_names = {}
        for path in sorted(glob(pattern)):
            count += 1
            rel = os.path.relpath(path, repo_root)

            try:
                raw = extract_frontmatter(path)
                if raw is None:
                    errors.append(f"{rel}: no YAML frontmatter block found (missing closing '---')")
                    continue

                data = load_frontmatter(raw, source=rel)

                desc = data.get("description")
                if desc is None:
                    errors.append(f"{rel}: missing 'description' key")
                    continue

                if not isinstance(desc, str):
                    errors.append(f"{rel}: 'description' must be a string, got {type(desc).__name__}")
                    continue

                if len(desc) > 1024:
                    errors.append(f"{rel}: description too long ({len(desc)} chars, max 1024)")

                if desc == "":
                    warnings.append(f"{rel}: description is empty")

                name = data.get("name")
                if not name or not isinstance(name, str):
                    errors.append(f"{rel}: missing or invalid 'name' key")
                    continue

                if name in seen_names:
                    errors.append(f"{rel}: duplicate name '{name}' (also declared by {seen_names[name]})")
                else:
                    seen_names[name] = rel
                is_devops_agent = rel.startswith("devops-agent/")

                if not is_devops_agent and name in manifest_by_name:
                    if desc != manifest_by_name[name]:
                        errors.append(f"{rel}: description does not match skills.json manifest (run update-pages.sh)")
                elif not is_devops_agent and name not in manifest_by_name:
                    warnings.append(f"{rel}: no manifest entry for '{name}' (not in skills.json)")

            except FrontmatterError as e:
                errors.append(f"{rel}: {e}")
            except yaml.YAMLError as e:
                errors.append(f"{rel}: YAML parse error: {e}")
            except (OSError, UnicodeDecodeError) as e:
                errors.append(f"{rel}: cannot read file: {e}")
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
