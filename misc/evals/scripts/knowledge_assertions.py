#!/usr/bin/env python3
"""Knowledge assertion engine (deterministic, no LLM calls).

Evaluates assistant text output against expert-authored knowledge assertions.
Each assertion requires a `source` field grounding it to an authoritative reference.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class KnowledgeAssertionResult:
    assertion: dict
    passed: bool
    evidence: str
    failure_class: str | None

    def to_dict(self) -> dict:
        return {
            "assertion": self.assertion,
            "passed": self.passed,
            "evidence": self.evidence,
            "failure_class": self.failure_class,
        }


@dataclass
class KnowledgeAssertionResults:
    results: list[KnowledgeAssertionResult]
    passed: int
    failed: int
    total: int
    pass_rate: float
    failure_classes: dict[str, int]

    def to_dict(self) -> dict:
        return {
            "results": [r.to_dict() for r in self.results],
            "passed": self.passed,
            "failed": self.failed,
            "total": self.total,
            "pass_rate": self.pass_rate,
            "failure_classes": self.failure_classes,
        }


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
    """Return an error message if the assertion is malformed, else None."""
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
    return None


def evaluate(text: str, assertions: list[dict]) -> KnowledgeAssertionResults:
    results: list[KnowledgeAssertionResult] = []

    for assertion in assertions:
        err = validate_assertion(assertion)
        if err:
            results.append(KnowledgeAssertionResult(
                assertion=assertion,
                passed=False,
                evidence=err,
                failure_class=None,
            ))
            continue

        atype = assertion["type"]
        evaluator = _EVALUATORS[atype]
        results.append(evaluator(text, assertion))

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
        pass_rate=passed / total if total else 0.0,
        failure_classes=failure_classes,
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
