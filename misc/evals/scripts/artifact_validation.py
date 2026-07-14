#!/usr/bin/env python3
"""Artifact validation engine (deterministic, no LLM calls).

Validates files produced by skill runs against structural assertions and
external tool validators declared in evals.json artifact_assertions.
"""

from __future__ import annotations

import glob as globmod
import json
import os
import re
import shutil
import subprocess
import time
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ArtifactAssertionResult:
    assertion: dict
    status: str  # "passed" | "failed" | "skipped"
    evidence: str
    failure_class: str | None
    file_matched: str | None

    def to_dict(self) -> dict:
        return {
            "assertion": self.assertion,
            "status": self.status,
            "evidence": self.evidence,
            "failure_class": self.failure_class,
            "file_matched": self.file_matched,
        }


@dataclass
class ValidatorResult:
    validator: dict
    status: str  # "passed" | "failed" | "skipped"
    detail: str
    exit_code: int | None
    duration_ms: int

    def to_dict(self) -> dict:
        return {
            "validator": self.validator,
            "status": self.status,
            "detail": self.detail,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
        }


@dataclass
class ArtifactValidationResults:
    artifact_root: str
    structural_results: list[ArtifactAssertionResult]
    validator_results: list[ValidatorResult]

    @property
    def structural_passed(self) -> int:
        return sum(1 for r in self.structural_results if r.status == "passed")

    @property
    def structural_failed(self) -> int:
        return sum(1 for r in self.structural_results if r.status == "failed")

    @property
    def structural_skipped(self) -> int:
        return sum(1 for r in self.structural_results if r.status == "skipped")

    @property
    def validators_passed(self) -> int:
        return sum(1 for r in self.validator_results if r.status == "passed")

    @property
    def validators_failed(self) -> int:
        return sum(1 for r in self.validator_results if r.status == "failed")

    @property
    def validators_skipped(self) -> int:
        return sum(1 for r in self.validator_results if r.status == "skipped")

    @property
    def overall_pass_rate(self) -> float:
        passed = self.structural_passed + self.validators_passed
        failed = self.structural_failed + self.validators_failed
        total = passed + failed
        return passed / total if total else 1.0

    def to_dict(self) -> dict:
        return {
            "artifact_root": self.artifact_root,
            "structural_results": [r.to_dict() for r in self.structural_results],
            "validator_results": [r.to_dict() for r in self.validator_results],
            "summary": {
                "structural_passed": self.structural_passed,
                "structural_failed": self.structural_failed,
                "structural_skipped": self.structural_skipped,
                "validators_passed": self.validators_passed,
                "validators_failed": self.validators_failed,
                "validators_skipped": self.validators_skipped,
                "overall_pass_rate": self.overall_pass_rate,
            },
        }


# --- Project root detection ---

PROJECT_MARKERS = ("main.tf", "Chart.yaml", "kustomization.yaml", "package.json", "Makefile")


def detect_project_root(outputs_dir: Path, root_glob: str | None = None) -> Path | None:
    if root_glob:
        matches = sorted(outputs_dir.glob(root_glob))
        dirs = [m for m in matches if m.is_dir()]
        if dirs:
            return dirs[0]
        if matches:
            return matches[0].parent

    for marker in PROJECT_MARKERS:
        found = list(outputs_dir.glob(f"**/{marker}"))
        if found:
            return found[0].parent

    return outputs_dir


# --- Glob helpers ---

def _resolve_glob(root: Path, pattern: str) -> list[Path]:
    results = sorted(root.glob(pattern))
    return [r for r in results if r.is_file()]


# --- Structural assertion evaluators ---

def _eval_file_exists(root: Path, assertion: dict) -> ArtifactAssertionResult:
    pattern = assertion["path"]
    matches = _resolve_glob(root, pattern)
    if matches:
        rel = matches[0].relative_to(root)
        return ArtifactAssertionResult(
            assertion=assertion,
            status="passed",
            evidence=f"File exists: {rel}",
            failure_class=None,
            file_matched=str(rel),
        )
    return ArtifactAssertionResult(
        assertion=assertion,
        status="failed",
        evidence=f"No file matching '{pattern}' found",
        failure_class="artifact_missing",
        file_matched=None,
    )


def _eval_file_not_exists(root: Path, assertion: dict) -> ArtifactAssertionResult:
    pattern = assertion["path"]
    matches = _resolve_glob(root, pattern)
    if matches:
        rel = matches[0].relative_to(root)
        return ArtifactAssertionResult(
            assertion=assertion,
            status="failed",
            evidence=f"Forbidden file found: {rel}",
            failure_class="artifact_invalid",
            file_matched=str(rel),
        )
    return ArtifactAssertionResult(
        assertion=assertion,
        status="passed",
        evidence=f"No file matching '{pattern}' exists (as required)",
        failure_class=None,
        file_matched=None,
    )


def _eval_contains(root: Path, assertion: dict) -> ArtifactAssertionResult:
    file_pattern = assertion["file"]
    regex = assertion["pattern"]
    flags = re.IGNORECASE if assertion.get("flags", "") == "i" else 0

    matches = _resolve_glob(root, file_pattern)
    if not matches:
        return ArtifactAssertionResult(
            assertion=assertion,
            status="failed",
            evidence=f"No files matching '{file_pattern}' to search",
            failure_class="artifact_missing",
            file_matched=None,
        )

    for f in matches:
        try:
            content = f.read_text(errors="replace")
        except OSError:
            continue
        m = re.search(regex, content, flags)
        if m:
            line_num = content[:m.start()].count("\n") + 1
            rel = f.relative_to(root)
            return ArtifactAssertionResult(
                assertion=assertion,
                status="passed",
                evidence=f"Pattern '{regex}' found in {rel} (line {line_num})",
                failure_class=None,
                file_matched=str(rel),
            )

    return ArtifactAssertionResult(
        assertion=assertion,
        status="failed",
        evidence=f"Pattern '{regex}' not found in any of {len(matches)} files matching '{file_pattern}'",
        failure_class="artifact_invalid",
        file_matched=None,
    )


def _eval_not_contains(root: Path, assertion: dict) -> ArtifactAssertionResult:
    file_pattern = assertion["file"]
    regex = assertion["pattern"]
    flags = re.IGNORECASE if assertion.get("flags", "") == "i" else 0

    matches = _resolve_glob(root, file_pattern)
    if not matches:
        return ArtifactAssertionResult(
            assertion=assertion,
            status="passed",
            evidence=f"No files matching '{file_pattern}' (pattern cannot be present)",
            failure_class=None,
            file_matched=None,
        )

    for f in matches:
        try:
            content = f.read_text(errors="replace")
        except OSError:
            continue
        m = re.search(regex, content, flags)
        if m:
            line_num = content[:m.start()].count("\n") + 1
            rel = f.relative_to(root)
            return ArtifactAssertionResult(
                assertion=assertion,
                status="failed",
                evidence=f"Forbidden pattern '{regex}' found in {rel} (line {line_num})",
                failure_class="artifact_invalid",
                file_matched=str(rel),
            )

    return ArtifactAssertionResult(
        assertion=assertion,
        status="passed",
        evidence=f"Pattern '{regex}' not found in any of {len(matches)} files matching '{file_pattern}'",
        failure_class=None,
        file_matched=None,
    )


def _eval_yaml_valid(root: Path, assertion: dict) -> ArtifactAssertionResult:
    paths_patterns = assertion["paths"]
    all_files: list[Path] = []
    for pattern in paths_patterns:
        all_files.extend(_resolve_glob(root, pattern))

    if not all_files:
        return ArtifactAssertionResult(
            assertion=assertion,
            status="skipped",
            evidence=f"No files matching {paths_patterns}",
            failure_class=None,
            file_matched=None,
        )

    for f in all_files:
        try:
            content = f.read_text(errors="replace")
            if len(content.encode("utf-8")) > 1024 * 1024:
                rel = f.relative_to(root)
                return ArtifactAssertionResult(
                    assertion=assertion,
                    status="failed",
                    evidence=f"Artifact too large to parse safely: {rel}",
                    failure_class="artifact_invalid",
                    file_matched=str(rel),
                )
            list(yaml.safe_load_all(content))
        except yaml.YAMLError as e:
            rel = f.relative_to(root)
            return ArtifactAssertionResult(
                assertion=assertion,
                status="failed",
                evidence=f"Invalid YAML in {rel}: {e}",
                failure_class="artifact_invalid",
                file_matched=str(rel),
            )
        except OSError as e:
            rel = f.relative_to(root)
            return ArtifactAssertionResult(
                assertion=assertion,
                status="failed",
                evidence=f"Cannot read {rel}: {e}",
                failure_class="artifact_missing",
                file_matched=str(rel),
            )

    return ArtifactAssertionResult(
        assertion=assertion,
        status="passed",
        evidence=f"All {len(all_files)} YAML files are valid",
        failure_class=None,
        file_matched=None,
    )


def _eval_json_valid(root: Path, assertion: dict) -> ArtifactAssertionResult:
    paths_patterns = assertion["paths"]
    all_files: list[Path] = []
    for pattern in paths_patterns:
        all_files.extend(_resolve_glob(root, pattern))

    if not all_files:
        return ArtifactAssertionResult(
            assertion=assertion,
            status="skipped",
            evidence=f"No files matching {paths_patterns}",
            failure_class=None,
            file_matched=None,
        )

    for f in all_files:
        try:
            content = f.read_text(errors="replace")
            json.loads(content)
        except json.JSONDecodeError as e:
            rel = f.relative_to(root)
            return ArtifactAssertionResult(
                assertion=assertion,
                status="failed",
                evidence=f"Invalid JSON in {rel}: {e}",
                failure_class="artifact_invalid",
                file_matched=str(rel),
            )
        except OSError as e:
            rel = f.relative_to(root)
            return ArtifactAssertionResult(
                assertion=assertion,
                status="failed",
                evidence=f"Cannot read {rel}: {e}",
                failure_class="artifact_missing",
                file_matched=str(rel),
            )

    return ArtifactAssertionResult(
        assertion=assertion,
        status="passed",
        evidence=f"All {len(all_files)} JSON files are valid",
        failure_class=None,
        file_matched=None,
    )


def _eval_file_count(root: Path, assertion: dict) -> ArtifactAssertionResult:
    pattern = assertion["glob"]
    min_count = assertion.get("min")
    max_count = assertion.get("max")

    matches = _resolve_glob(root, pattern)
    count = len(matches)

    if min_count is not None and count < min_count:
        return ArtifactAssertionResult(
            assertion=assertion,
            status="failed",
            evidence=f"Found {count} files matching '{pattern}', expected min {min_count}",
            failure_class="artifact_missing",
            file_matched=None,
        )

    if max_count is not None and count > max_count:
        return ArtifactAssertionResult(
            assertion=assertion,
            status="failed",
            evidence=f"Found {count} files matching '{pattern}', expected max {max_count}",
            failure_class="artifact_invalid",
            file_matched=None,
        )

    return ArtifactAssertionResult(
        assertion=assertion,
        status="passed",
        evidence=f"Found {count} files matching '{pattern}' (within [{min_count}, {max_count}])",
        failure_class=None,
        file_matched=None,
    )


def _eval_hcl_resource_exists(root: Path, assertion: dict) -> ArtifactAssertionResult:
    resource_type = assertion["resource_type"]
    resource_name = assertion["resource_name"]

    tf_files = _resolve_glob(root, "**/*.tf")
    if not tf_files:
        return ArtifactAssertionResult(
            assertion=assertion,
            status="failed",
            evidence="No .tf files found",
            failure_class="artifact_missing",
            file_matched=None,
        )

    pattern = rf'{resource_type}\s+"?{re.escape(resource_name)}"?\s*\{{'
    for f in tf_files:
        try:
            content = f.read_text(errors="replace")
        except OSError:
            continue
        if re.search(pattern, content):
            rel = f.relative_to(root)
            return ArtifactAssertionResult(
                assertion=assertion,
                status="passed",
                evidence=f"HCL block '{resource_type} \"{resource_name}\"' found in {rel}",
                failure_class=None,
                file_matched=str(rel),
            )

    return ArtifactAssertionResult(
        assertion=assertion,
        status="failed",
        evidence=f"HCL block '{resource_type} \"{resource_name}\"' not found in {len(tf_files)} .tf files",
        failure_class="artifact_invalid",
        file_matched=None,
    )


def _eval_hcl_attribute_check(root: Path, assertion: dict) -> ArtifactAssertionResult:
    """Check that a specific attribute exists (or matches a value) within an HCL resource block.

    Schema:
        type: hcl-attribute-check
        resource: aws_eks_cluster          # resource type
        resource_name: main                # optional; if omitted checks all instances
        attribute: encryption_config.provider.key_arn  # dot-separated path
        exists: true                       # or "value": "regex_pattern"
        file: main.tf                      # optional; if omitted searches all .tf files
    """
    resource_type = assertion["resource"]
    resource_name = assertion.get("resource_name")  # optional
    attribute_path = assertion["attribute"]
    check_exists = assertion.get("exists")  # bool or None
    value_pattern = assertion.get("value")  # regex string or None
    file_filter = assertion.get("file")  # optional filename

    # Determine which .tf files to search
    if file_filter:
        tf_files = _resolve_glob(root, f"**/{file_filter}")
    else:
        tf_files = _resolve_glob(root, "**/*.tf")

    if not tf_files:
        return ArtifactAssertionResult(
            assertion=assertion,
            status="skipped",
            evidence=f"No .tf files found" + (f" matching '{file_filter}'" if file_filter else ""),
            failure_class=None,
            file_matched=None,
        )

    # Try to use python-hcl2 for accurate parsing
    hcl2_available = False
    try:
        import hcl2 as _hcl2
        hcl2_available = True
    except ImportError:
        pass

    if hcl2_available:
        return _hcl_attribute_check_parsed(root, assertion, tf_files, resource_type, resource_name, attribute_path, check_exists, value_pattern)
    else:
        return _hcl_attribute_check_regex(root, assertion, tf_files, resource_type, resource_name, attribute_path, check_exists, value_pattern)


def _navigate_attribute_path(obj: Any, path_parts: list[str]) -> tuple[bool, Any]:
    """Navigate a nested dict/list structure following dot-separated path parts.

    Returns (found: bool, value: Any).
    """
    current = obj
    for part in path_parts:
        if isinstance(current, dict):
            if part in current:
                current = current[part]
            else:
                return False, None
        elif isinstance(current, list):
            # HCL2 parser wraps blocks in lists; search each element
            found_in_list = False
            for item in current:
                found, val = _navigate_attribute_path(item, [part])
                if found:
                    current = val
                    found_in_list = True
                    break
            if not found_in_list:
                return False, None
        else:
            return False, None
    return True, current


def _hcl_attribute_check_parsed(
    root: Path,
    assertion: dict,
    tf_files: list[Path],
    resource_type: str,
    resource_name: str | None,
    attribute_path: str,
    check_exists: bool | None,
    value_pattern: str | None,
) -> ArtifactAssertionResult:
    """HCL attribute check using python-hcl2 parser."""
    import hcl2

    path_parts = attribute_path.split(".")

    for f in tf_files:
        try:
            with open(f, "r") as fh:
                parsed = hcl2.load(fh)
        except Exception as e:
            rel = f.relative_to(root)
            return ArtifactAssertionResult(
                assertion=assertion,
                status="failed",
                evidence=f"HCL parse error in {rel}: {e}",
                failure_class="artifact_invalid",
                file_matched=str(rel),
            )

        # hcl2.load returns {"resource": [{"aws_eks_cluster": {"main": {...}}}], ...}
        resources = parsed.get("resource", [])
        for resource_block in resources:
            if not isinstance(resource_block, dict):
                continue
            if resource_type not in resource_block:
                continue
            type_block = resource_block[resource_type]
            if not isinstance(type_block, dict):
                continue

            # Determine which resource names to check
            names_to_check = [resource_name] if resource_name else list(type_block.keys())

            for name in names_to_check:
                if name not in type_block:
                    continue
                body = type_block[name]

                found, value = _navigate_attribute_path(body, path_parts)
                rel = f.relative_to(root)

                if check_exists is True and found:
                    return ArtifactAssertionResult(
                        assertion=assertion,
                        status="passed",
                        evidence=f"Attribute '{attribute_path}' exists in {resource_type}.{name} ({rel})",
                        failure_class=None,
                        file_matched=str(rel),
                    )
                elif check_exists is False and not found:
                    return ArtifactAssertionResult(
                        assertion=assertion,
                        status="passed",
                        evidence=f"Attribute '{attribute_path}' absent from {resource_type}.{name} ({rel}) as required",
                        failure_class=None,
                        file_matched=str(rel),
                    )
                elif value_pattern is not None and found:
                    str_value = str(value) if not isinstance(value, str) else value
                    if re.search(value_pattern, str_value):
                        return ArtifactAssertionResult(
                            assertion=assertion,
                            status="passed",
                            evidence=f"Attribute '{attribute_path}' in {resource_type}.{name} matches pattern '{value_pattern}' ({rel})",
                            failure_class=None,
                            file_matched=str(rel),
                        )

    # Nothing matched — determine correct failure message
    name_label = f".{resource_name}" if resource_name else ""
    if check_exists is True:
        return ArtifactAssertionResult(
            assertion=assertion,
            status="failed",
            evidence=f"Attribute '{attribute_path}' not found in any {resource_type}{name_label} resource across {len(tf_files)} .tf files",
            failure_class="artifact_invalid",
            file_matched=None,
        )
    elif check_exists is False:
        return ArtifactAssertionResult(
            assertion=assertion,
            status="failed",
            evidence=f"Attribute '{attribute_path}' unexpectedly present in {resource_type}{name_label}",
            failure_class="artifact_invalid",
            file_matched=None,
        )
    elif value_pattern is not None:
        return ArtifactAssertionResult(
            assertion=assertion,
            status="failed",
            evidence=f"Attribute '{attribute_path}' in {resource_type}{name_label} did not match pattern '{value_pattern}' (or attribute/resource not found)",
            failure_class="artifact_invalid",
            file_matched=None,
        )
    else:
        return ArtifactAssertionResult(
            assertion=assertion,
            status="failed",
            evidence=f"No matching assertion condition for {resource_type}{name_label}.{attribute_path}",
            failure_class="artifact_invalid",
            file_matched=None,
        )


def _hcl_attribute_check_regex(
    root: Path,
    assertion: dict,
    tf_files: list[Path],
    resource_type: str,
    resource_name: str | None,
    attribute_path: str,
    check_exists: bool | None,
    value_pattern: str | None,
) -> ArtifactAssertionResult:
    """Regex-based fallback for HCL attribute check (when python-hcl2 is unavailable).

    Best-effort heuristic — locates the resource block by regex, then searches for
    the leaf attribute name within it.
    """
    import warnings
    warnings.warn("python-hcl2 not available; hcl-attribute-check using regex fallback (results may be imprecise)", stacklevel=2)

    # Build regex for the resource block header
    if resource_name:
        block_pattern = rf'resource\s+"{re.escape(resource_type)}"\s+"{re.escape(resource_name)}"\s*\{{'
    else:
        block_pattern = rf'resource\s+"{re.escape(resource_type)}"\s+"[^"]+"\s*\{{'

    # The leaf attribute is the last segment of the dot path
    leaf_attr = attribute_path.split(".")[-1]

    for f in tf_files:
        try:
            content = f.read_text(errors="replace")
        except OSError:
            continue

        for match in re.finditer(block_pattern, content):
            # Extract the block body by counting braces
            start = match.start()
            brace_count = 0
            block_body = ""
            for i in range(match.end() - 1, len(content)):
                ch = content[i]
                if ch == "{":
                    brace_count += 1
                elif ch == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        block_body = content[match.end():i]
                        break

            if not block_body:
                continue

            # Search for the leaf attribute in the block
            # Match attribute assignment (=) or block label
            attr_found = re.search(
                rf'(?:^|\n)\s*{re.escape(leaf_attr)}\s*[=\{{]', block_body
            )

            rel = f.relative_to(root)

            if check_exists is True:
                if attr_found:
                    return ArtifactAssertionResult(
                        assertion=assertion,
                        status="passed",
                        evidence=f"Attribute '{attribute_path}' found in {resource_type} block ({rel}) [regex heuristic]",
                        failure_class=None,
                        file_matched=str(rel),
                    )
            elif check_exists is False:
                if not attr_found:
                    return ArtifactAssertionResult(
                        assertion=assertion,
                        status="passed",
                        evidence=f"Attribute '{attribute_path}' absent from {resource_type} block ({rel}) as required [regex heuristic]",
                        failure_class=None,
                        file_matched=str(rel),
                    )
                else:
                    return ArtifactAssertionResult(
                        assertion=assertion,
                        status="failed",
                        evidence=f"Attribute '{attribute_path}' unexpectedly present in {resource_type} block ({rel}) [regex heuristic]",
                        failure_class="artifact_invalid",
                        file_matched=str(rel),
                    )
            elif value_pattern is not None:
                if attr_found:
                    # Try to extract the value after the attribute
                    value_match = re.search(
                        rf'{re.escape(leaf_attr)}\s*=\s*["\']?([^"\'\n\r]*)["\']?',
                        block_body,
                    )
                    if value_match and re.search(value_pattern, value_match.group(1)):
                        return ArtifactAssertionResult(
                            assertion=assertion,
                            status="passed",
                            evidence=f"Attribute '{attribute_path}' matches pattern '{value_pattern}' in {resource_type} block ({rel}) [regex heuristic]",
                            failure_class=None,
                            file_matched=str(rel),
                        )

    # Nothing matched
    name_label = f".{resource_name}" if resource_name else ""
    if check_exists is True:
        return ArtifactAssertionResult(
            assertion=assertion,
            status="failed",
            evidence=f"Attribute '{attribute_path}' not found in any {resource_type}{name_label} resource [regex heuristic]",
            failure_class="artifact_invalid",
            file_matched=None,
        )
    elif check_exists is False:
        # If we didn't find the resource at all, it's effectively absent
        return ArtifactAssertionResult(
            assertion=assertion,
            status="passed",
            evidence=f"No {resource_type}{name_label} resource found, so attribute is absent [regex heuristic]",
            failure_class=None,
            file_matched=None,
        )
    elif value_pattern is not None:
        return ArtifactAssertionResult(
            assertion=assertion,
            status="failed",
            evidence=f"Attribute '{attribute_path}' in {resource_type}{name_label} did not match pattern '{value_pattern}' (or not found) [regex heuristic]",
            failure_class="artifact_invalid",
            file_matched=None,
        )
    else:
        return ArtifactAssertionResult(
            assertion=assertion,
            status="failed",
            evidence=f"No matching assertion condition for {resource_type}{name_label}.{attribute_path} [regex heuristic]",
            failure_class="artifact_invalid",
            file_matched=None,
        )


def _eval_mermaid_valid(root: Path, assertion: dict) -> ArtifactAssertionResult:
    paths_patterns = assertion["paths"]
    all_files: list[Path] = []
    for pattern in paths_patterns:
        all_files.extend(_resolve_glob(root, pattern))

    if not all_files:
        return ArtifactAssertionResult(
            assertion=assertion,
            status="skipped",
            evidence=f"No files matching {paths_patterns}",
            failure_class=None,
            file_matched=None,
        )

    mmdc = shutil.which("mmdc")
    for f in all_files:
        try:
            content = f.read_text(errors="replace")
        except OSError:
            continue

        if mmdc:
            result = subprocess.run(
                [mmdc, "-i", str(f), "-o", "/dev/null"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                rel = f.relative_to(root)
                return ArtifactAssertionResult(
                    assertion=assertion,
                    status="failed",
                    evidence=f"Invalid Mermaid in {rel}: {result.stderr[:200]}",
                    failure_class="artifact_invalid",
                    file_matched=str(rel),
                )
        else:
            valid_starts = ("graph ", "flowchart ", "sequenceDiagram", "classDiagram",
                           "stateDiagram", "erDiagram", "gantt", "pie ", "gitGraph",
                           "mindmap", "timeline", "C4Context", "architecture")
            stripped = content.strip()
            if not any(stripped.startswith(s) for s in valid_starts):
                rel = f.relative_to(root)
                return ArtifactAssertionResult(
                    assertion=assertion,
                    status="failed",
                    evidence=f"File {rel} doesn't start with a recognized Mermaid diagram type (heuristic check; install mmdc for full validation)",
                    failure_class="artifact_invalid",
                    file_matched=str(rel),
                )

    return ArtifactAssertionResult(
        assertion=assertion,
        status="passed",
        evidence=f"All {len(all_files)} Mermaid files are valid" + (" (heuristic)" if not mmdc else ""),
        failure_class=None,
        file_matched=None,
    )


_STRUCTURAL_EVALUATORS = {
    "file-exists": _eval_file_exists,
    "file-not-exists": _eval_file_not_exists,
    "contains": _eval_contains,
    "not-contains": _eval_not_contains,
    "yaml-valid": _eval_yaml_valid,
    "json-valid": _eval_json_valid,
    "file-count": _eval_file_count,
    "hcl-resource-exists": _eval_hcl_resource_exists,
    "hcl-attribute-check": _eval_hcl_attribute_check,
    "mermaid-valid": _eval_mermaid_valid,
}


def run_structural_assertions(root: Path, assertions: list[dict]) -> list[ArtifactAssertionResult]:
    results: list[ArtifactAssertionResult] = []
    for assertion in assertions:
        atype = assertion.get("type", "")
        evaluator = _STRUCTURAL_EVALUATORS.get(atype)
        if evaluator is None:
            results.append(ArtifactAssertionResult(
                assertion=assertion,
                status="failed",
                evidence=f"Unknown structural assertion type: '{atype}'",
                failure_class=None,
                file_matched=None,
            ))
            continue
        results.append(evaluator(root, assertion))
    return results


# --- Validator runners ---

def _run_command(cmd: list[str], cwd: Path, timeout: int = 120) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s"
    except FileNotFoundError:
        return -2, "", f"Command not found: {cmd[0]}"


def _validator_terraform_fmt(root: Path, validator: dict) -> ValidatorResult:
    if not shutil.which("terraform"):
        return ValidatorResult(
            validator=validator, status="skipped",
            detail="terraform not found on PATH", exit_code=None, duration_ms=0,
        )

    start = time.time()
    rc, stdout, stderr = _run_command(["terraform", "fmt", "-check", "-recursive", "."], root)
    elapsed = int((time.time() - start) * 1000)

    if rc == 0:
        return ValidatorResult(
            validator=validator, status="passed",
            detail="All files properly formatted", exit_code=0, duration_ms=elapsed,
        )
    if rc == -2:
        return ValidatorResult(
            validator=validator, status="skipped",
            detail="terraform not found", exit_code=None, duration_ms=0,
        )

    detail = stdout.strip() or stderr.strip()
    return ValidatorResult(
        validator=validator, status="failed",
        detail=f"Unformatted files:\n{detail[:500]}", exit_code=rc, duration_ms=elapsed,
    )


def _validator_terraform_validate(root: Path, validator: dict) -> ValidatorResult:
    if not shutil.which("terraform"):
        return ValidatorResult(
            validator=validator, status="skipped",
            detail="terraform not found on PATH", exit_code=None, duration_ms=0,
        )

    start = time.time()
    rc, stdout, stderr = _run_command(
        ["terraform", "init", "-backend=false", "-input=false"], root, timeout=120,
    )
    if rc != 0:
        elapsed = int((time.time() - start) * 1000)
        return ValidatorResult(
            validator=validator, status="skipped",
            detail=f"terraform init failed (may need providers): {stderr[:300]}",
            exit_code=rc, duration_ms=elapsed,
        )

    rc, stdout, stderr = _run_command(["terraform", "validate", "-json"], root)
    elapsed = int((time.time() - start) * 1000)

    if rc == 0:
        return ValidatorResult(
            validator=validator, status="passed",
            detail="terraform validate: Success", exit_code=0, duration_ms=elapsed,
        )

    detail = stderr.strip() or stdout.strip()
    return ValidatorResult(
        validator=validator, status="failed",
        detail=f"terraform validate failed:\n{detail[:500]}", exit_code=rc, duration_ms=elapsed,
    )


def _validator_checkov(root: Path, validator: dict) -> ValidatorResult:
    if not shutil.which("checkov"):
        return ValidatorResult(
            validator=validator, status="skipped",
            detail="checkov not found on PATH", exit_code=None, duration_ms=0,
        )

    framework = validator.get("framework", "terraform")
    skip_checks = validator.get("skip_checks", [])
    cmd = ["checkov", "-d", ".", "--framework", framework, "--compact", "--output", "json"]
    for check in skip_checks:
        cmd.extend(["--skip-check", check])

    start = time.time()
    rc, stdout, stderr = _run_command(cmd, root, timeout=300)
    elapsed = int((time.time() - start) * 1000)

    if rc == 0:
        return ValidatorResult(
            validator=validator, status="passed",
            detail="checkov: all checks passed", exit_code=0, duration_ms=elapsed,
        )
    if rc == -2:
        return ValidatorResult(
            validator=validator, status="skipped",
            detail="checkov not found", exit_code=None, duration_ms=0,
        )

    detail = stderr.strip() or stdout[:500]
    return ValidatorResult(
        validator=validator, status="failed",
        detail=f"checkov failures:\n{detail[:500]}", exit_code=rc, duration_ms=elapsed,
    )


def _validator_shellcheck(root: Path, validator: dict) -> ValidatorResult:
    if not shutil.which("shellcheck"):
        return ValidatorResult(
            validator=validator, status="skipped",
            detail="shellcheck not found on PATH", exit_code=None, duration_ms=0,
        )

    paths_patterns = validator.get("paths", ["**/*.sh"])
    all_files: list[Path] = []
    for pattern in paths_patterns:
        all_files.extend(_resolve_glob(root, pattern))

    if not all_files:
        return ValidatorResult(
            validator=validator, status="skipped",
            detail=f"No files matching {paths_patterns}", exit_code=None, duration_ms=0,
        )

    start = time.time()
    rc, stdout, stderr = _run_command(
        ["shellcheck"] + [str(f) for f in all_files], root,
    )
    elapsed = int((time.time() - start) * 1000)

    if rc == 0:
        return ValidatorResult(
            validator=validator, status="passed",
            detail=f"shellcheck: {len(all_files)} files passed", exit_code=0, duration_ms=elapsed,
        )

    detail = stdout.strip() or stderr.strip()
    return ValidatorResult(
        validator=validator, status="failed",
        detail=f"shellcheck issues:\n{detail[:500]}", exit_code=rc, duration_ms=elapsed,
    )


def _validator_markdownlint(root: Path, validator: dict) -> ValidatorResult:
    mdl = shutil.which("markdownlint") or shutil.which("mdl")
    if not mdl:
        return ValidatorResult(
            validator=validator, status="skipped",
            detail="markdownlint/mdl not found on PATH", exit_code=None, duration_ms=0,
        )

    paths_patterns = validator.get("paths", ["**/*.md"])
    all_files: list[Path] = []
    for pattern in paths_patterns:
        all_files.extend(_resolve_glob(root, pattern))

    if not all_files:
        return ValidatorResult(
            validator=validator, status="skipped",
            detail=f"No files matching {paths_patterns}", exit_code=None, duration_ms=0,
        )

    start = time.time()
    rc, stdout, stderr = _run_command(
        [mdl] + [str(f) for f in all_files], root,
    )
    elapsed = int((time.time() - start) * 1000)

    if rc == 0:
        return ValidatorResult(
            validator=validator, status="passed",
            detail=f"markdownlint: {len(all_files)} files passed", exit_code=0, duration_ms=elapsed,
        )

    detail = stdout.strip() or stderr.strip()
    return ValidatorResult(
        validator=validator, status="failed",
        detail=f"markdownlint issues:\n{detail[:500]}", exit_code=rc, duration_ms=elapsed,
    )


def _validator_kubectl_dry_run(root: Path, validator: dict) -> ValidatorResult:
    if not shutil.which("kubectl"):
        return ValidatorResult(
            validator=validator, status="skipped",
            detail="kubectl not found on PATH", exit_code=None, duration_ms=0,
        )

    paths_patterns = validator.get("paths", ["**/*.yaml"])
    exclude_patterns = validator.get("exclude", [])
    all_files: list[Path] = []
    for pattern in paths_patterns:
        all_files.extend(_resolve_glob(root, pattern))

    excluded: set[Path] = set()
    for pattern in exclude_patterns:
        excluded.update(_resolve_glob(root, pattern))
    all_files = [f for f in all_files if f not in excluded]

    k8s_files: list[Path] = []
    for f in all_files:
        try:
            content = f.read_text(errors="replace")
            if "apiVersion" in content and "kind" in content:
                k8s_files.append(f)
        except OSError:
            continue

    if not k8s_files:
        return ValidatorResult(
            validator=validator, status="skipped",
            detail="No Kubernetes manifests found", exit_code=None, duration_ms=0,
        )

    start = time.time()
    failures: list[str] = []
    for f in k8s_files:
        rc, stdout, stderr = _run_command(
            ["kubectl", "apply", "--dry-run=client", "-f", str(f)], root,
        )
        if rc != 0:
            rel = f.relative_to(root)
            failures.append(f"{rel}: {stderr.strip()[:100]}")

    elapsed = int((time.time() - start) * 1000)

    if not failures:
        return ValidatorResult(
            validator=validator, status="passed",
            detail=f"kubectl dry-run: {len(k8s_files)} manifests passed",
            exit_code=0, duration_ms=elapsed,
        )

    return ValidatorResult(
        validator=validator, status="failed",
        detail=f"kubectl dry-run failures:\n" + "\n".join(failures[:10]),
        exit_code=1, duration_ms=elapsed,
    )


def _validator_script(root: Path, validator: dict, repo_root: Path) -> ValidatorResult:
    script_path = repo_root / validator["path"]
    if not script_path.exists():
        return ValidatorResult(
            validator=validator, status="failed",
            detail=f"Script not found: {validator['path']}", exit_code=None, duration_ms=0,
        )

    args = []
    for arg in validator.get("args", []):
        args.append(arg.replace("{root}", str(root)))

    cmd = [str(script_path)] + args

    start = time.time()
    rc, stdout, stderr = _run_command(cmd, root, timeout=300)
    elapsed = int((time.time() - start) * 1000)

    if rc == 0:
        last_lines = stdout.strip().split("\n")[-5:]
        return ValidatorResult(
            validator=validator, status="passed",
            detail="\n".join(last_lines), exit_code=0, duration_ms=elapsed,
        )

    detail = stdout.strip() or stderr.strip()
    return ValidatorResult(
        validator=validator, status="failed",
        detail=detail[-500:], exit_code=rc, duration_ms=elapsed,
    )


_VALIDATOR_RUNNERS = {
    "terraform-fmt": _validator_terraform_fmt,
    "terraform-validate": _validator_terraform_validate,
    "checkov": _validator_checkov,
    "shellcheck": _validator_shellcheck,
    "markdownlint": _validator_markdownlint,
    "kubectl-dry-run": _validator_kubectl_dry_run,
}


def run_validators(root: Path, validators: list[dict], repo_root: Path) -> list[ValidatorResult]:
    results: list[ValidatorResult] = []
    for validator in validators:
        vtype = validator.get("type", "")
        if vtype == "script":
            results.append(_validator_script(root, validator, repo_root))
        elif vtype in _VALIDATOR_RUNNERS:
            results.append(_VALIDATOR_RUNNERS[vtype](root, validator))
        else:
            results.append(ValidatorResult(
                validator=validator, status="failed",
                detail=f"Unknown validator type: '{vtype}'", exit_code=None, duration_ms=0,
            ))
    return results


# --- Top-level API ---

def validate_run(
    outputs_dir: Path,
    assertions_config: dict,
    repo_root: Path,
) -> ArtifactValidationResults:
    root_glob = assertions_config.get("root_glob")
    root = detect_project_root(outputs_dir, root_glob)

    if root is None:
        root = outputs_dir

    try:
        artifact_root_str = str(root.relative_to(outputs_dir))
    except ValueError:
        artifact_root_str = str(root)

    structural = assertions_config.get("structural", [])
    validators_cfg = assertions_config.get("validators", [])

    structural_results = run_structural_assertions(root, structural)
    validator_results = run_validators(root, validators_cfg, repo_root)

    return ArtifactValidationResults(
        artifact_root=artifact_root_str,
        structural_results=structural_results,
        validator_results=validator_results,
    )
