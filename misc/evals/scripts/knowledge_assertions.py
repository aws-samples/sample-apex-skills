#!/usr/bin/env python3
"""Knowledge assertion engine (deterministic, no LLM calls).

Evaluates assistant text output against expert-authored knowledge assertions.
Each assertion requires a `source` field grounding it to an authoritative reference.

Supports hierarchical/grouped assertions:
- `group` field: groups assertions under a named group with weight and child assertions
- `when_parent_matches` field: conditional evaluation based on prior sibling results
- Per-assertion `weight` field: controls contribution to score (default 1.0)
- Group-level scoring: weighted average of group scores and ungrouped score
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class KnowledgeAssertionResult:
    assertion: dict
    passed: bool
    evidence: str
    failure_class: str | None
    group: str | None = None
    skipped: bool = False
    weight: float = 1.0

    def to_dict(self) -> dict:
        d = {
            "assertion": self.assertion,
            "passed": self.passed,
            "evidence": self.evidence,
            "failure_class": self.failure_class,
        }
        if self.group is not None:
            d["group"] = self.group
        if self.skipped:
            d["skipped"] = True
        if self.weight != 1.0:
            d["weight"] = self.weight
        return d


@dataclass
class GroupResult:
    """Score summary for a single assertion group."""
    name: str
    weight: float
    score: float
    passed: int
    failed: int
    skipped: int
    total: int
    results: list[KnowledgeAssertionResult]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "weight": self.weight,
            "score": self.score,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "total": self.total,
            "results": [r.to_dict() for r in self.results],
        }


@dataclass
class KnowledgeAssertionResults:
    results: list[KnowledgeAssertionResult]
    passed: int
    failed: int
    total: int
    pass_rate: float
    failure_classes: dict[str, int]
    groups: list[GroupResult] = field(default_factory=list)
    skipped: int = 0

    def to_dict(self) -> dict:
        d = {
            "results": [r.to_dict() for r in self.results],
            "passed": self.passed,
            "failed": self.failed,
            "total": self.total,
            "pass_rate": self.pass_rate,
            "failure_classes": self.failure_classes,
        }
        if self.groups:
            d["groups"] = [g.to_dict() for g in self.groups]
        if self.skipped > 0:
            d["skipped"] = self.skipped
        return d


def _get_flags(assertion: dict) -> int:
    flags = 0
    flag_str = assertion.get("flags", "i")
    if "i" in flag_str:
        flags |= re.IGNORECASE
    if "m" in flag_str:
        flags |= re.MULTILINE
    if "s" in flag_str:
        flags |= re.DOTALL
    return flags


def _eval_must_contain(text: str, assertion: dict) -> KnowledgeAssertionResult:
    pattern = assertion["pattern"]
    flags = _get_flags(assertion)

    m = re.search(pattern, text, flags)
    if m:
        start = max(0, m.start() - 30)
        end = min(len(text), m.end() + 30)
        snippet = text[start:end].replace("\n", " ")
        return KnowledgeAssertionResult(
            assertion=assertion,
            passed=True,
            evidence=f"Pattern '{pattern}' found: ...{snippet}...",
            failure_class=None,
        )

    return KnowledgeAssertionResult(
        assertion=assertion,
        passed=False,
        evidence=f"Pattern '{pattern}' not found in output",
        failure_class="knowledge_gap",
    )


def _eval_must_not_contain(text: str, assertion: dict) -> KnowledgeAssertionResult:
    pattern = assertion["pattern"]
    flags = _get_flags(assertion)

    m = re.search(pattern, text, flags)
    if m:
        start = max(0, m.start() - 30)
        end = min(len(text), m.end() + 30)
        snippet = text[start:end].replace("\n", " ")
        return KnowledgeAssertionResult(
            assertion=assertion,
            passed=False,
            evidence=f"Forbidden pattern '{pattern}' found: ...{snippet}...",
            failure_class="knowledge_violation",
        )

    return KnowledgeAssertionResult(
        assertion=assertion,
        passed=True,
        evidence=f"Pattern '{pattern}' correctly absent from output",
        failure_class=None,
    )


def _eval_must_contain_one_of(text: str, assertion: dict) -> KnowledgeAssertionResult:
    patterns = assertion["patterns"]
    flags = _get_flags(assertion)

    for pattern in patterns:
        m = re.search(pattern, text, flags)
        if m:
            start = max(0, m.start() - 30)
            end = min(len(text), m.end() + 30)
            snippet = text[start:end].replace("\n", " ")
            return KnowledgeAssertionResult(
                assertion=assertion,
                passed=True,
                evidence=f"Pattern '{pattern}' matched (from {len(patterns)} alternatives): ...{snippet}...",
                failure_class=None,
            )

    return KnowledgeAssertionResult(
        assertion=assertion,
        passed=False,
        evidence=f"None of {len(patterns)} patterns matched: {patterns}",
        failure_class="knowledge_gap",
    )


def _eval_regex_match(text: str, assertion: dict) -> KnowledgeAssertionResult:
    pattern = assertion["pattern"]
    flags = _get_flags(assertion)

    m = re.search(pattern, text, flags)
    if m:
        start = max(0, m.start() - 30)
        end = min(len(text), m.end() + 30)
        snippet = text[start:end].replace("\n", " ")
        return KnowledgeAssertionResult(
            assertion=assertion,
            passed=True,
            evidence=f"Regex '{pattern}' matched: ...{snippet}...",
            failure_class=None,
        )

    return KnowledgeAssertionResult(
        assertion=assertion,
        passed=False,
        evidence=f"Regex '{pattern}' did not match",
        failure_class="knowledge_gap",
    )


_EVALUATORS = {
    "must-contain": _eval_must_contain,
    "must-not-contain": _eval_must_not_contain,
    "must-contain-one-of": _eval_must_contain_one_of,
    "regex-match": _eval_regex_match,
}


def validate_assertion(assertion: dict) -> str | None:
    """Return an error message if the assertion is malformed, else None.

    Accepts both flat assertions and group assertions (with a 'group' key).
    """
    # Group assertion validation
    if "group" in assertion:
        return _validate_group_assertion(assertion)

    atype = assertion.get("type")
    if atype not in _EVALUATORS:
        return f"Unknown assertion type: '{atype}'"
    if not assertion.get("source"):
        return f"Missing required 'source' field on {atype} assertion"
    if atype in ("must-contain", "must-not-contain", "regex-match"):
        if not assertion.get("pattern"):
            return f"Missing required 'pattern' field on {atype} assertion"
    if atype == "must-contain-one-of":
        if not assertion.get("patterns") or not isinstance(assertion.get("patterns"), list):
            return f"Missing or invalid 'patterns' field on {atype} assertion"

    # Validate optional weight field
    weight = assertion.get("weight")
    if weight is not None:
        if not isinstance(weight, (int, float)) or weight < 0:
            return f"Invalid 'weight' field: must be a non-negative number, got {weight!r}"

    return None


def _validate_group_assertion(group: dict) -> str | None:
    """Validate a group assertion structure."""
    if not isinstance(group.get("group"), str) or not group["group"]:
        return "Group assertion must have a non-empty 'group' string field"
    if "weight" in group:
        w = group["weight"]
        if not isinstance(w, (int, float)) or w < 0 or w > 1:
            return f"Group 'weight' must be a float between 0 and 1, got {w!r}"
    children = group.get("assertions")
    if not isinstance(children, list) or len(children) == 0:
        return f"Group '{group['group']}' must have a non-empty 'assertions' list"
    for i, child in enumerate(children):
        err = _validate_child_assertion(child, group["group"], i)
        if err:
            return err
    return None


def _validate_child_assertion(assertion: dict, group_name: str, index: int) -> str | None:
    """Validate a child assertion within a group."""
    atype = assertion.get("type")
    if atype not in _EVALUATORS:
        return f"Group '{group_name}' child[{index}]: unknown assertion type '{atype}'"
    if not assertion.get("source"):
        return f"Group '{group_name}' child[{index}]: missing required 'source' field"
    if atype in ("must-contain", "must-not-contain", "regex-match"):
        if not assertion.get("pattern"):
            return f"Group '{group_name}' child[{index}]: missing required 'pattern' field"
    if atype == "must-contain-one-of":
        if not assertion.get("patterns") or not isinstance(assertion.get("patterns"), list):
            return f"Group '{group_name}' child[{index}]: missing or invalid 'patterns' field"
    # Validate optional fields
    weight = assertion.get("weight")
    if weight is not None:
        if not isinstance(weight, (int, float)) or weight < 0:
            return f"Group '{group_name}' child[{index}]: invalid 'weight' field"
    wpm = assertion.get("when_parent_matches")
    if wpm is not None:
        if not isinstance(wpm, str):
            return f"Group '{group_name}' child[{index}]: 'when_parent_matches' must be a string regex"
        try:
            re.compile(wpm)
        except re.error as e:
            return f"Group '{group_name}' child[{index}]: invalid 'when_parent_matches' regex: {e}"
    return None


def _evaluate_flat(text: str, assertions: list[dict]) -> list[KnowledgeAssertionResult]:
    """Evaluate a list of flat (non-grouped) assertions."""
    results: list[KnowledgeAssertionResult] = []
    for assertion in assertions:
        err = validate_assertion(assertion)
        if err:
            results.append(KnowledgeAssertionResult(
                assertion=assertion,
                passed=False,
                evidence=err,
                failure_class=None,
                weight=assertion.get("weight", 1.0),
            ))
            continue

        atype = assertion["type"]
        evaluator = _EVALUATORS[atype]
        result = evaluator(text, assertion)
        result.weight = assertion.get("weight", 1.0)
        results.append(result)
    return results


def _evaluate_group(text: str, group: dict) -> GroupResult:
    """Evaluate a group of assertions, respecting when_parent_matches conditions."""
    group_name = group["group"]
    group_weight = group.get("weight", 1.0)
    children = group["assertions"]

    results: list[KnowledgeAssertionResult] = []
    # Track which patterns have passed (for when_parent_matches lookups)
    passed_patterns: list[str] = []

    for child in children:
        child_weight = child.get("weight", 1.0)

        # Check when_parent_matches condition
        wpm = child.get("when_parent_matches")
        if wpm is not None:
            # Only evaluate if a prior sibling with a matching pattern passed
            condition_met = False
            try:
                wpm_re = re.compile(wpm)
                for pp in passed_patterns:
                    if wpm_re.search(pp):
                        condition_met = True
                        break
            except re.error:
                condition_met = False

            if not condition_met:
                results.append(KnowledgeAssertionResult(
                    assertion=child,
                    passed=False,
                    evidence=f"Skipped: when_parent_matches '{wpm}' condition not met (no prior sibling matched)",
                    failure_class=None,
                    group=group_name,
                    skipped=True,
                    weight=child_weight,
                ))
                continue

        # Evaluate the child assertion
        atype = child["type"]
        evaluator = _EVALUATORS[atype]
        result = evaluator(text, child)
        result.group = group_name
        result.weight = child_weight

        # Track passed patterns for when_parent_matches
        if result.passed and child.get("pattern"):
            passed_patterns.append(child["pattern"])

        results.append(result)

    # Compute group score (weighted, excluding skipped)
    evaluated = [r for r in results if not r.skipped]
    total_weight = sum(r.weight for r in evaluated)
    weighted_pass = sum(r.weight for r in evaluated if r.passed)
    group_score = weighted_pass / total_weight if total_weight > 0 else 0.0

    passed_count = sum(1 for r in evaluated if r.passed)
    failed_count = sum(1 for r in evaluated if not r.passed)
    skipped_count = sum(1 for r in results if r.skipped)

    return GroupResult(
        name=group_name,
        weight=group_weight,
        score=group_score,
        passed=passed_count,
        failed=failed_count,
        skipped=skipped_count,
        total=len(results),
        results=results,
    )


def evaluate(text: str, assertions: list[dict]) -> KnowledgeAssertionResults:
    """Evaluate assertions against text. Supports both flat and grouped assertions.

    If no groups exist, behaves identically to the original flat-only implementation.
    """
    # Separate flat assertions from group assertions
    flat_assertions: list[dict] = []
    group_assertions: list[dict] = []

    for assertion in assertions:
        if "group" in assertion:
            group_assertions.append(assertion)
        else:
            flat_assertions.append(assertion)

    # If no groups, use the original simple logic (backwards-compatible)
    if not group_assertions:
        results = _evaluate_flat(text, flat_assertions)

        # Compute weighted score
        total_weight = sum(r.weight for r in results)
        weighted_pass = sum(r.weight for r in results if r.passed)
        pass_rate = weighted_pass / total_weight if total_weight > 0 else 0.0

        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed
        total = len(results)

        failure_classes: dict[str, int] = {}
        for r in results:
            if r.failure_class:
                failure_classes[r.failure_class] = failure_classes.get(r.failure_class, 0) + 1

        return KnowledgeAssertionResults(
            results=results,
            passed=passed,
            failed=failed,
            total=total,
            pass_rate=pass_rate,
            failure_classes=failure_classes,
        )

    all_results: list[KnowledgeAssertionResult] = []
    group_results: list[GroupResult] = []

    # Evaluate flat assertions
    flat_results = _evaluate_flat(text, flat_assertions)
    all_results.extend(flat_results)

    # Evaluate group assertions
    for group in group_assertions:
        err = validate_assertion(group)
        if err:
            # Add a single failed result for the invalid group
            all_results.append(KnowledgeAssertionResult(
                assertion=group,
                passed=False,
                evidence=err,
                failure_class=None,
                weight=group.get("weight", 1.0),
            ))
            continue
        gr = _evaluate_group(text, group)
        group_results.append(gr)
        all_results.extend(gr.results)

    # Compute final weighted score:
    # final_score = (ungrouped_score * ungrouped_weight) + sum(group_score * group_weight)
    # where weights are normalized to sum to 1.0

    # Calculate ungrouped weighted score
    flat_evaluated = [r for r in flat_results]
    flat_total_weight_sum = sum(r.weight for r in flat_evaluated)
    flat_weighted_pass = sum(r.weight for r in flat_evaluated if r.passed)
    flat_score = flat_weighted_pass / flat_total_weight_sum if flat_total_weight_sum > 0 else 0.0

    # Determine the weight for the ungrouped portion
    # If groups have explicit weights, ungrouped gets 1 - sum(group_weights)
    # If no flat assertions exist, ungrouped_weight is 0
    total_group_weight = sum(gr.weight for gr in group_results)

    if flat_assertions:
        ungrouped_weight = max(0.0, 1.0 - total_group_weight)
    else:
        ungrouped_weight = 0.0

    # Compute final pass_rate as weighted combination
    if ungrouped_weight + total_group_weight > 0:
        # Normalize weights
        normalization = ungrouped_weight + total_group_weight
        final_score = ungrouped_weight * flat_score
        for gr in group_results:
            final_score += gr.weight * gr.score
        final_score /= normalization
    else:
        final_score = 0.0

    # Aggregate counts
    passed = sum(1 for r in all_results if r.passed and not r.skipped)
    skipped = sum(1 for r in all_results if r.skipped)
    failed = sum(1 for r in all_results if not r.passed and not r.skipped)
    total = len(all_results)

    failure_classes: dict[str, int] = {}
    for r in all_results:
        if r.failure_class and not r.skipped:
            failure_classes[r.failure_class] = failure_classes.get(r.failure_class, 0) + 1

    return KnowledgeAssertionResults(
        results=all_results,
        passed=passed,
        failed=failed,
        total=total,
        pass_rate=final_score,
        failure_classes=failure_classes,
        groups=group_results,
        skipped=skipped,
    )


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            f"Usage: {sys.argv[0]} <text-file> <assertions.json>",
            file=sys.stderr,
        )
        print(
            "  text-file: plain text file containing assistant output",
            file=sys.stderr,
        )
        print(
            '  assertions.json: JSON list of assertion objects or dict with "knowledge_assertions" key.',
            file=sys.stderr,
        )
        sys.exit(2)

    text_path = Path(sys.argv[1])
    assertions_path = Path(sys.argv[2])

    if not text_path.exists():
        print(f"File not found: {text_path}", file=sys.stderr)
        sys.exit(2)
    if not assertions_path.exists():
        print(f"File not found: {assertions_path}", file=sys.stderr)
        sys.exit(2)

    text = text_path.read_text(errors="replace")
    raw = json.loads(assertions_path.read_text())
    if isinstance(raw, list):
        assertions = raw
    elif isinstance(raw, dict) and "knowledge_assertions" in raw:
        assertions = raw["knowledge_assertions"]
    else:
        print("assertions file must be a list or have a 'knowledge_assertions' key", file=sys.stderr)
        sys.exit(2)

    results = evaluate(text, assertions)
    print(json.dumps(results.to_dict(), indent=2))
    sys.exit(0 if results.failed == 0 else 1)
