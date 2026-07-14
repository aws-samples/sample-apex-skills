#!/usr/bin/env python3
"""Deterministic hygiene pre-flight for misc/evals/<skill>/ entries.

Reuses the pre-flight logic already embedded in run_all_evals.py — runs
quick_validate, checks triggering.json positive/negative counts, checks
evals.json prompt/expectation counts, and confirms every `should_trigger=false`
entry in triggering.json is attributed to a sibling in README.md's
SIBLING_MAP block.

No model calls, no Makefile shell-outs, no live cluster. Safe for a
per-PR CI gate.

Usage:
  check_hygiene.py               — every skill under misc/evals/
  check_hygiene.py --skill NAME  — single skill (used by make init-evals-finalize)

Exit codes:
  0  every skill is clean
  1  one or more skills have hygiene warnings
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent


def _load_run_all_evals():
    """Import run_all_evals.py without relying on a package __init__.py."""
    name = "_run_all_evals_for_hygiene"
    spec = importlib.util.spec_from_file_location(
        name,
        SCRIPTS_DIR / "run_all_evals.py",
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--skill",
        help="Check only this skill (used by `make init-evals-finalize`). "
        "Default: every skill under misc/evals/.",
    )
    args = parser.parse_args()

    rae = _load_run_all_evals()

    skills = rae.discover_skills()
    if args.skill:
        if args.skill not in skills:
            print(
                f"unknown skill: {args.skill} (known: {', '.join(skills) or 'none'})",
                file=sys.stderr,
            )
            return 1
        skills = [args.skill]

    if not skills:
        print("no skills discovered under misc/evals/", file=sys.stderr)
        return 1

    any_fail = False
    for skill in skills:
        warnings: list[str] = []

        hygiene = rae.hygiene_check(skill)
        warnings.extend(hygiene.warnings)

        # Sibling-map attribution check — mirror the body of process_skill()
        # without shelling out to make.
        readme_path = rae.EVALS_ROOT / skill / "README.md"
        triggering_path = rae.EVALS_ROOT / skill / "triggering.json"
        try:
            triggering = json.loads(triggering_path.read_text())
        except FileNotFoundError:
            triggering = []
        except json.JSONDecodeError:
            triggering = []

        try:
            readme = readme_path.read_text()
        except FileNotFoundError:
            readme = ""
            warnings.append(f"missing README.md at {readme_path}")

        if readme and triggering:
            sibling_entries = rae.parse_sibling_map(readme)
            if not sibling_entries:
                warnings.append(
                    "sibling map empty — missing SIBLING_MAP markers or unparseable bullets"
                )
            _, _, unmatched = rae.build_index_to_sibling(sibling_entries, triggering)
            if unmatched:
                warnings.append(
                    f"sibling map does not attribute negative indices: {sorted(unmatched)}"
                )

        # --- New checks (errors = fail hygiene) ---

        # 1. skill_name in evals.json must match the directory name.
        evals_path = rae.EVALS_ROOT / skill / "evals.json"
        try:
            evals_data = json.loads(evals_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            evals_data = {}

        evals_skill_name = evals_data.get("skill_name")
        if evals_skill_name and evals_skill_name != skill:
            warnings.append(
                f"evals.json skill_name '{evals_skill_name}' does not match directory name '{skill}'"
            )

        # 2. Duplicate id values within evals.json.
        prompts = evals_data.get("evals") or []
        seen_ids: dict[Any, int] = {}
        for idx, p in enumerate(prompts):
            pid = p.get("id")
            if pid is None:
                continue
            if pid in seen_ids:
                warnings.append(
                    f"evals.json has duplicate id={pid} (indices {seen_ids[pid]} and {idx})"
                )
            else:
                seen_ids[pid] = idx

        # --- New checks (warnings only = non-breaking) ---

        # 3. live_only field (if present) must be boolean.
        for p in prompts:
            if "live_only" in p and not isinstance(p["live_only"], bool):
                warnings.append(
                    f"evals.json prompt id={p.get('id', '?')} has non-boolean live_only: {type(p['live_only']).__name__}"
                )

        # 4. Referenced files entries (if non-empty) must exist on disk.
        files_dir = rae.EVALS_ROOT / skill / "files"
        for p in prompts:
            for f in p.get("files") or []:
                if not f:
                    continue
                file_path = files_dir / f
                if not file_path.exists():
                    warnings.append(
                        f"evals.json prompt id={p.get('id', '?')} references file '{f}' but {file_path} does not exist"
                    )

        # 5. artifact_assertions schema validation (if present).
        VALID_STRUCTURAL_TYPES = {
            "file-exists", "file-not-exists", "contains", "not-contains",
            "yaml-valid", "json-valid", "file-count", "hcl-resource-exists",
            "json-schema", "mermaid-valid",
        }
        VALID_VALIDATOR_TYPES = {
            "terraform-fmt", "terraform-validate", "checkov", "shellcheck",
            "markdownlint", "kubectl-dry-run", "script",
        }
        for p in prompts:
            aa = p.get("artifact_assertions")
            if not aa:
                continue
            pid = p.get("id", "?")
            if not isinstance(aa, dict):
                warnings.append(f"evals.json prompt id={pid}: artifact_assertions must be a dict")
                continue
            for key in aa:
                if key not in ("root_glob", "validators", "structural"):
                    warnings.append(f"evals.json prompt id={pid}: unknown artifact_assertions key '{key}'")
            for i, s in enumerate(aa.get("structural") or []):
                stype = s.get("type")
                if stype not in VALID_STRUCTURAL_TYPES:
                    warnings.append(
                        f"evals.json prompt id={pid}: structural[{i}] has unknown type '{stype}'"
                    )
            for i, v in enumerate(aa.get("validators") or []):
                vtype = v.get("type")
                if vtype not in VALID_VALIDATOR_TYPES:
                    warnings.append(
                        f"evals.json prompt id={pid}: validators[{i}] has unknown type '{vtype}'"
                    )
                if vtype == "script" and "path" not in v:
                    warnings.append(
                        f"evals.json prompt id={pid}: validators[{i}] type=script requires 'path'"
                    )

        # 6. .skilleval.yaml presence and basic structure.
        skilleval_path = rae.EVALS_ROOT / skill / ".skilleval.yaml"
        if not skilleval_path.exists():
            warnings.append(f"missing .skilleval.yaml at {skilleval_path}")
        else:
            try:
                import yaml
                skilleval_text = skilleval_path.read_text()
                if len(skilleval_text.encode("utf-8")) > 256 * 1024:
                    warnings.append(".skilleval.yaml exceeds maximum allowed size")
                    skilleval_raw = None
                else:
                    skilleval_raw = yaml.safe_load(skilleval_text) or {}
                if skilleval_raw is None:
                    pass  # oversize; already reported
                elif not isinstance(skilleval_raw, dict):
                    warnings.append(".skilleval.yaml must be a YAML mapping")
                else:
                    if "skill_name" not in skilleval_raw:
                        warnings.append(".skilleval.yaml missing 'skill_name' field")
                    elif skilleval_raw["skill_name"] != skill:
                        warnings.append(
                            f".skilleval.yaml skill_name '{skilleval_raw['skill_name']}' "
                            f"does not match directory name '{skill}'"
                        )
                    if "weights" not in skilleval_raw:
                        warnings.append(".skilleval.yaml missing 'weights' field")
                    elif isinstance(skilleval_raw["weights"], dict):
                        wsum = sum(float(v) for v in skilleval_raw["weights"].values())
                        if abs(wsum - 1.0) > 0.01:
                            warnings.append(
                                f".skilleval.yaml weights sum to {wsum:.3f} (expected ~1.0)"
                            )
            except ImportError:
                pass  # PyYAML not available — skip validation
            except Exception as e:
                warnings.append(f".skilleval.yaml parse error: {e}")

        # 7. knowledge_assertions schema validation (if present).
        VALID_KNOWLEDGE_TYPES = {
            "must-contain", "must-not-contain", "must-contain-one-of", "regex-match",
        }
        for p in prompts:
            ka = p.get("knowledge_assertions")
            if not ka:
                continue
            pid = p.get("id", "?")
            if not isinstance(ka, list):
                warnings.append(f"evals.json prompt id={pid}: knowledge_assertions must be a list")
                continue
            for i, a in enumerate(ka):
                atype = a.get("type")
                if atype not in VALID_KNOWLEDGE_TYPES:
                    warnings.append(
                        f"evals.json prompt id={pid}: knowledge_assertions[{i}] has unknown type '{atype}'"
                    )
                if not a.get("source"):
                    warnings.append(
                        f"evals.json prompt id={pid}: knowledge_assertions[{i}] missing required 'source' field"
                    )
                if atype in ("must-contain", "must-not-contain", "regex-match") and not a.get("pattern"):
                    warnings.append(
                        f"evals.json prompt id={pid}: knowledge_assertions[{i}] type={atype} requires 'pattern'"
                    )
                if atype == "must-contain-one-of" and not isinstance(a.get("patterns"), list):
                    warnings.append(
                        f"evals.json prompt id={pid}: knowledge_assertions[{i}] type={atype} requires 'patterns' list"
                    )

        if warnings:
            any_fail = True
            print(f"✗ {skill}")
            for w in warnings:
                print(f"    - {w}")
        else:
            print(f"✓ {skill}")

    if any_fail:
        print("\nHygiene check failed. Fix the warnings above before merging.", file=sys.stderr)
        return 1

    print("\nAll skills pass hygiene.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
