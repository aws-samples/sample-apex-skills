#!/usr/bin/env python3
"""Lint a steering-workflow markdown file against the convention.

Usage:
    python quick_validate.py <path-to-workflow.md> [--json]

Exit 0 on pass, 1 on any error. Ground truth lives in
`../references/convention.md`, `../references/tool-routing.md`, and
`../references/anti-patterns.md`. The conforming exemplar at
`../assets/workflow-skeleton.md` MUST lint clean.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple


# ----- data model -----

@dataclass
class Finding:
    code: str
    line: int  # 1-indexed; 0 if file-global
    message: str
    section: str = ""
    anti_pattern: str = ""

    def format(self) -> str:
        loc = f"line {self.line}" if self.line > 0 else "file"
        tail = f" (see references/anti-patterns.md § {self.anti_pattern})" if self.anti_pattern else ""
        return f"  [{self.code}] {loc}: {self.message}{tail}"


# ----- helpers -----

REQUIRED_SECTIONS = [
    "How to Route Requests",
    "Phases",
    "Defaults",
    "Quality Checklist",
    "Conversation Style",
]

ACCESS_MODEL_VALUES = {"read-only", "advisory", "mutating"}

# Acronyms tolerated as ALL-CAPS words inside H2 titles under sentence-case rule.
TITLE_ACRONYMS = {"EKS", "MCP", "AWS", "IAM", "CLI", "API", "RDS", "VPC", "DNS", "IaC", "CI", "CD"}


def find_fenced_code_ranges(lines: List[str]) -> List[Tuple[int, int]]:
    """Return 0-indexed inclusive ranges of lines inside ``` fences or HTML comments."""
    ranges: List[Tuple[int, int]] = []
    in_fence = False
    in_html_comment = False
    start = -1
    fence_re = re.compile(r"^\s*```")
    for i, line in enumerate(lines):
        if in_html_comment:
            if "-->" in line:
                ranges.append((start, i))
                in_html_comment = False
                start = -1
            continue
        if in_fence:
            if fence_re.match(line):
                ranges.append((start, i))
                in_fence = False
                start = -1
            continue
        if fence_re.match(line):
            in_fence = True
            start = i
            continue
        if "<!--" in line and "-->" not in line:
            in_html_comment = True
            start = i
            continue
        if "<!--" in line and "-->" in line:
            ranges.append((i, i))
    if (in_fence or in_html_comment) and start >= 0:
        ranges.append((start, len(lines) - 1))
    return ranges


def strip_code_spans(line: str) -> str:
    """Remove inline `code` spans (single backtick) from a line for style checks."""
    # Remove fenced portions delimited by backticks.
    return re.sub(r"`[^`]*`", "", line)


def in_ranges(i: int, ranges: List[Tuple[int, int]]) -> bool:
    for a, b in ranges:
        if a <= i <= b:
            return True
    return False


TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$")


def is_table_separator(line: str) -> bool:
    return bool(TABLE_SEP_RE.match(line))


# ----- checks -----

def check_frontmatter(lines: List[str]) -> List[Finding]:
    findings: List[Finding] = []
    # Skip leading HTML comment block (the skeleton uses one) and blank lines.
    idx = 0
    # Skip HTML comments at the very top.
    if idx < len(lines) and lines[idx].lstrip().startswith("<!--"):
        while idx < len(lines) and "-->" not in lines[idx]:
            idx += 1
        idx += 1  # past the closing -->
    # Skip blank lines.
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1
    if idx >= len(lines) or lines[idx].strip() != "---":
        findings.append(Finding(
            "E001", idx + 1,
            "frontmatter missing: file must open with '---'",
        ))
        return findings
    start = idx
    end = -1
    for j in range(idx + 1, len(lines)):
        if lines[j].strip() == "---":
            end = j
            break
    if end == -1:
        findings.append(Finding(
            "E002", start + 1,
            "frontmatter not closed: no trailing '---' found",
        ))
        return findings
    body = lines[start + 1:end]
    has_name = any(re.match(r"^\s*name\s*:\s*\S", ln) for ln in body)
    has_desc = any(re.match(r"^\s*description\s*:\s*\S", ln) for ln in body)
    has_inclusion = any(re.match(r"^\s*inclusion\s*:", ln) for ln in body)
    if not has_name:
        findings.append(Finding("E003", start + 1, "frontmatter missing 'name:' key"))
    if not has_desc:
        findings.append(Finding("E004", start + 1, "frontmatter missing 'description:' key"))
    if has_inclusion:
        findings.append(Finding(
            "E005", start + 1,
            "frontmatter must NOT include 'inclusion:' on a workflow file",
            anti_pattern="10. `inclusion: manual` on a workflow file",
        ))
    return findings


def locate_title_and_header(lines: List[str]) -> Tuple[int, List[Finding]]:
    """Find H1 title line (0-indexed); return (title_line_idx, findings).

    Also validates the 4-line blockquote header block immediately after the title.
    """
    findings: List[Finding] = []
    # Locate end of frontmatter.
    idx = 0
    if idx < len(lines) and lines[idx].lstrip().startswith("<!--"):
        while idx < len(lines) and "-->" not in lines[idx]:
            idx += 1
        idx += 1
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1
    if idx < len(lines) and lines[idx].strip() == "---":
        for j in range(idx + 1, len(lines)):
            if lines[j].strip() == "---":
                idx = j + 1
                break
    # Skip blank lines after frontmatter.
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1
    if idx >= len(lines):
        findings.append(Finding("E010", 0, "no title line found after frontmatter"))
        return -1, findings
    title_line = lines[idx]
    # First non-frontmatter non-blank line must be '# Title' (exactly one '#').
    m = re.match(r"^(#+)\s+", title_line)
    if not m:
        findings.append(Finding(
            "E010", idx + 1,
            f"first non-frontmatter line must be '# <Title>', got: {title_line.strip()[:80]!r}",
        ))
        return idx, findings
    if len(m.group(1)) != 1:
        findings.append(Finding(
            "E011", idx + 1,
            f"title must be H1 (single '#'), found H{len(m.group(1))}",
        ))
        return idx, findings

    # Next non-blank lines -> expect 4-line blockquote header in order.
    j = idx + 1
    while j < len(lines) and lines[j].strip() == "":
        j += 1
    header_lines = []
    while j < len(lines) and lines[j].lstrip().startswith(">"):
        header_lines.append((j, lines[j]))
        j += 1
        if len(header_lines) >= 8:  # sanity cap
            break

    expected_labels = ["Part of", "Lifecycle", "Skill", "Access Model"]
    if not header_lines:
        findings.append(Finding(
            "E012", idx + 2,
            "missing blockquote header block (Part of / Lifecycle / Skill / Access Model)",
            anti_pattern="2. Missing `Access Model` in the header block",
        ))
        return idx, findings

    # Parse each header line: strip leading '>' and optional bold markers.
    parsed: List[Tuple[int, str, str]] = []  # (line_no, label, value)
    for ln_idx, raw in header_lines:
        body = re.sub(r"^\s*>\s?", "", raw).rstrip("\n")
        # Accept **Label:** or Label:
        m2 = re.match(r"^\s*\*\*([^*:]+):\*\*\s*(.*)$", body) or re.match(r"^\s*([A-Za-z ]+?):\s*(.*)$", body)
        if m2:
            parsed.append((ln_idx + 1, m2.group(1).strip(), m2.group(2).strip()))
        else:
            parsed.append((ln_idx + 1, "", body.strip()))

    # Enforce order of the first four expected labels.
    for k, expected in enumerate(expected_labels):
        if k >= len(parsed):
            findings.append(Finding(
                "E013", idx + 2,
                f"header block missing line {k + 1}: '{expected}:'",
                anti_pattern="2. Missing `Access Model` in the header block" if expected == "Access Model" else "",
            ))
            continue
        line_no, label, value = parsed[k]
        if label.lower() != expected.lower():
            findings.append(Finding(
                "E014", line_no,
                f"header line {k + 1}: expected '{expected}:' but found '{label or '?'}:'",
                anti_pattern="2. Missing `Access Model` in the header block" if expected == "Access Model" else "",
            ))
        if expected == "Access Model" and label.lower() == "access model":
            # Strip optional parenthetical and skeleton-style value lists.
            v = value.lower()
            # Accept forms like "read-only", "advisory", "mutating (with gates)",
            # or skeleton alternation "read-only | advisory | mutating (with gates)".
            head = re.split(r"\s*\||\s*\(", v, maxsplit=1)[0].strip()
            if head not in ACCESS_MODEL_VALUES and not any(
                v.startswith(x) for x in ACCESS_MODEL_VALUES
            ):
                # Look deeper: any ACCESS_MODEL_VALUES token anywhere?
                if not any(tok in v for tok in ACCESS_MODEL_VALUES):
                    findings.append(Finding(
                        "E015", line_no,
                        f"Access Model must be one of {sorted(ACCESS_MODEL_VALUES)}; got {value!r}",
                    ))
    return idx, findings


def find_h2_sections(lines: List[str], code_ranges: List[Tuple[int, int]]) -> List[Tuple[int, str]]:
    """Return list of (line_idx_0based, title) for each H2 outside code fences."""
    out: List[Tuple[int, str]] = []
    for i, ln in enumerate(lines):
        if in_ranges(i, code_ranges):
            continue
        m = re.match(r"^##\s+(.+?)\s*$", ln)
        if m and not ln.startswith("###"):
            out.append((i, m.group(1).strip()))
    return out


def check_required_sections(h2s: List[Tuple[int, str]]) -> List[Finding]:
    findings: List[Finding] = []
    # Check presence + order + duplicates for the required five.
    positions = {name: [] for name in REQUIRED_SECTIONS}
    for idx, (lineno, title) in enumerate(h2s):
        for req in REQUIRED_SECTIONS:
            if title.lower() == req.lower():
                positions[req].append((idx, lineno, title))
    # Missing?
    missing_anti = {
        "Defaults": "3. Missing `## Defaults` section",
        "Quality Checklist": "4. Missing `## Quality Checklist` section",
    }
    for req in REQUIRED_SECTIONS:
        if not positions[req]:
            findings.append(Finding(
                "E020", 0,
                f"missing required H2 section: '## {req}'",
                anti_pattern=missing_anti.get(req, ""),
            ))
    # Duplicate?
    for req in REQUIRED_SECTIONS:
        if len(positions[req]) > 1:
            findings.append(Finding(
                "E021", positions[req][1][1] + 1,
                f"duplicate required H2 section: '## {req}' appears {len(positions[req])} times",
            ))
    # Case drift note.
    for req in REQUIRED_SECTIONS:
        for _, lineno, title in positions[req]:
            if title != req:
                findings.append(Finding(
                    "E022", lineno + 1,
                    f"section title case drift: '{title}' should be '{req}'",
                ))
    # Order.
    present_order = []
    for req in REQUIRED_SECTIONS:
        if positions[req]:
            present_order.append((req, positions[req][0][0]))
    for i in range(1, len(present_order)):
        if present_order[i][1] < present_order[i - 1][1]:
            findings.append(Finding(
                "E023", h2s[present_order[i][1]][0] + 1,
                f"section order wrong: '{present_order[i][0]}' appears before '{present_order[i - 1][0]}'",
            ))
    return findings


def check_h2_sentence_case(h2s: List[Tuple[int, str]]) -> List[Finding]:
    findings: List[Finding] = []
    required_lower = {r.lower() for r in REQUIRED_SECTIONS}
    for lineno, title in h2s:
        # Required section titles are fixed by spec; don't flag their casing here.
        if title.lower() in required_lower:
            continue
        words = re.findall(r"[A-Za-z][A-Za-z0-9'\-]*", title)
        if not words:
            continue
        capitalized_after_first = 0
        for w in words[1:]:
            if w in TITLE_ACRONYMS:
                continue
            if w[0].isupper():
                capitalized_after_first += 1
        if capitalized_after_first > 1:
            findings.append(Finding(
                "E024", lineno + 1,
                f"H2 title appears title-cased (should be sentence case): '{title}'",
            ))
    return findings


def find_phase_section_range(
    lines: List[str], h2s: List[Tuple[int, str]]
) -> Optional[Tuple[int, int]]:
    """Return 0-indexed [start, end) line range for the '## Phases' section."""
    start = None
    for i, (lineno, title) in enumerate(h2s):
        if title.lower() == "phases":
            start = lineno
            end = len(lines)
            if i + 1 < len(h2s):
                end = h2s[i + 1][0]
            return (start, end)
    return None


def check_phases(lines: List[str], h2s: List[Tuple[int, str]], code_ranges: List[Tuple[int, int]]) -> List[Finding]:
    findings: List[Finding] = []
    rng = find_phase_section_range(lines, h2s)
    # Also detect flat ## Phase N: (drift).
    # Scan the whole file for H2 phase headings anywhere — that is drift.
    for i, ln in enumerate(lines):
        if in_ranges(i, code_ranges):
            continue
        if re.match(r"^##\s+Phase\s+\d+\s*:", ln, re.IGNORECASE):
            findings.append(Finding(
                "E030", i + 1,
                f"phase heading must be H3 '### Phase N: ...', not H2: {ln.strip()[:80]!r}",
            ))
    if rng is None:
        return findings
    start, end = rng
    phase_re = re.compile(r"^###\s+Phase\s+(\d+)\s*:\s*(.+?)\s*$", re.IGNORECASE)
    # Collect phase boundaries.
    phases: List[Tuple[int, int, str]] = []  # (start_idx, num, name)
    for i in range(start, end):
        if in_ranges(i, code_ranges):
            continue
        m = phase_re.match(lines[i])
        if m:
            phases.append((i, int(m.group(1)), m.group(2)))
    # For each phase, slice its body and check Source:, CLI fallback (if live).
    for k, (pstart, pnum, pname) in enumerate(phases):
        pend = phases[k + 1][0] if k + 1 < len(phases) else end
        body = lines[pstart:pend]
        # Source annotation.
        source_val = None
        source_line = -1
        for j, bln in enumerate(body):
            if in_ranges(pstart + j, code_ranges):
                continue
            m = re.match(r"^\s*(?:\*\*)?Source(?:\*\*)?\s*:\s*(.+?)\s*$", bln, re.IGNORECASE)
            if m:
                source_val = m.group(1).strip().lower()
                source_line = pstart + j
                break
        if source_val is None:
            findings.append(Finding(
                "E031", pstart + 1,
                f"phase {pnum} ({pname!r}) missing 'Source:' annotation",
                anti_pattern="7. Phase structure without a `Source:` annotation",
            ))
        else:
            # Accept tokens knowledge, live, either (possibly followed by more text).
            head = re.match(r"(knowledge|live|either)\b", source_val)
            if not head:
                findings.append(Finding(
                    "E032", source_line + 1,
                    f"phase {pnum}: Source value must start with one of knowledge|live|either, got {source_val!r}",
                ))
            else:
                if head.group(1) == "live":
                    # Check CLI fallback presence somewhere in the body.
                    has_fallback = False
                    for j, bln in enumerate(body):
                        if re.match(r"^\s*(?:\*\*)?CLI fallback(?:\*\*)?\s*:", bln, re.IGNORECASE):
                            has_fallback = True
                            break
                        # Prose form: sentence containing 'CLI fallback' and a code span.
                        if re.search(r"CLI fallback", bln, re.IGNORECASE) and ("`" in bln):
                            has_fallback = True
                            break
                    if not has_fallback:
                        findings.append(Finding(
                            "E033", pstart + 1,
                            f"phase {pnum} is Source: live but has no 'CLI fallback:' line",
                            anti_pattern="8. Missing CLI fallback on `live` phases",
                        ))
    # At least one **STOP.** marker inside the Phases section.
    has_stop = False
    stop_re = re.compile(r"\*\*STOP\.\*\*")
    for i in range(start, end):
        if in_ranges(i, code_ranges):
            continue
        if stop_re.search(lines[i]):
            has_stop = True
            break
    if not has_stop:
        findings.append(Finding(
            "E034", start + 1,
            "Phases section has no '**STOP.**' checkpoint (at least one required)",
            anti_pattern="5. Inconsistent STOP-gate syntax",
        ))
    return findings


def check_style_rules(lines: List[str], code_ranges: List[Tuple[int, int]]) -> List[Finding]:
    findings: List[Finding] = []
    # Skip frontmatter entirely for style checks? No — em-dash drift in frontmatter
    # description is still worth flagging. But the header block is already prose.
    dash_re = re.compile(r"(?:\w|\s)--(?:\w|\s)")
    arrow_re = re.compile(r"->")
    for i, ln in enumerate(lines):
        if in_ranges(i, code_ranges):
            continue
        if is_table_separator(ln):
            continue
        # Skip frontmatter delimiters themselves (---).
        stripped = ln.strip()
        if stripped == "---":
            continue
        # Strip inline `code` spans before checking for prose drift.
        scrubbed = strip_code_spans(ln)
        if dash_re.search(scrubbed):
            findings.append(Finding(
                "E040", i + 1,
                "'--' used as em-dash replacement in prose (use '—' or '-')",
                anti_pattern="1. `--` instead of em-dash",
            ))
        if arrow_re.search(scrubbed):
            findings.append(Finding(
                "E041", i + 1,
                "'->' used as arrow in prose (use '→' outside code blocks)",
                anti_pattern="6. Unicode-vs-ASCII arrow drift inside the same repo",
            ))
    return findings


def check_length(lines: List[str]) -> List[Finding]:
    findings: List[Finding] = []
    n = len(lines)
    if n > 450:
        findings.append(Finding(
            "E050", 0,
            f"file length {n} lines exceeds hard cap 450 (soft cap ~450; split or move reference content)",
        ))
    elif n >= 400:
        findings.append(Finding(
            "W051", 0,
            f"file length {n} lines approaching 450-line cap",
        ))
    return findings


def section_body(lines: List[str], h2s: List[Tuple[int, str]], name: str) -> Optional[Tuple[int, int]]:
    for i, (lineno, title) in enumerate(h2s):
        if title.lower() == name.lower():
            end = h2s[i + 1][0] if i + 1 < len(h2s) else len(lines)
            return (lineno, end)
    return None


def count_table_rows(lines: List[str], start: int, end: int, code_ranges: List[Tuple[int, int]]) -> int:
    """Count data rows in markdown tables between [start, end). A data row is a
    pipe-bearing line following a separator row."""
    rows = 0
    in_table = False
    after_sep = False
    for i in range(start, end):
        if in_ranges(i, code_ranges):
            in_table = False
            after_sep = False
            continue
        ln = lines[i]
        if "|" in ln and ln.strip().startswith("|") or (ln.count("|") >= 2 and not is_table_separator(ln)):
            if is_table_separator(ln):
                after_sep = True
                in_table = True
                continue
            if after_sep and in_table:
                if ln.strip() and ln.count("|") >= 2:
                    rows += 1
            else:
                in_table = True
        else:
            if ln.strip() == "":
                # blank line ends a table
                in_table = False
                after_sep = False
    return rows


def check_routing_table(lines: List[str], h2s: List[Tuple[int, str]], code_ranges: List[Tuple[int, int]]) -> List[Finding]:
    rng = section_body(lines, h2s, "How to Route Requests")
    if rng is None:
        return []
    rows = count_table_rows(lines, rng[0], rng[1], code_ranges)
    if rows < 2:
        return [Finding(
            "E060", rng[0] + 1,
            f"'## How to Route Requests' must contain a table with >=2 data rows; found {rows}",
        )]
    return []


def check_defaults_table(lines: List[str], h2s: List[Tuple[int, str]], code_ranges: List[Tuple[int, int]]) -> List[Finding]:
    rng = section_body(lines, h2s, "Defaults")
    if rng is None:
        return []
    rows = count_table_rows(lines, rng[0], rng[1], code_ranges)
    if rows < 1:
        return [Finding(
            "E061", rng[0] + 1,
            f"'## Defaults' must contain a table with >=1 data row; found {rows}",
            anti_pattern="3. Missing `## Defaults` section",
        )]
    return []


def check_quality_checklist(lines: List[str], h2s: List[Tuple[int, str]], code_ranges: List[Tuple[int, int]]) -> List[Finding]:
    rng = section_body(lines, h2s, "Quality Checklist")
    if rng is None:
        return []
    start, end = rng
    has_checklist = False
    has_threshold = False
    checklist_re = re.compile(r"^\s*[-*]\s*\[[ xX]\]\s+")
    threshold_re = re.compile(r"pass threshold", re.IGNORECASE)
    for i in range(start, end):
        if in_ranges(i, code_ranges):
            continue
        if checklist_re.match(lines[i]):
            has_checklist = True
        if threshold_re.search(lines[i]):
            has_threshold = True
    out: List[Finding] = []
    if not has_checklist:
        out.append(Finding(
            "E062", start + 1,
            "'## Quality Checklist' must contain at least one '- [ ]' or '- [x]' item",
            anti_pattern="4. Missing `## Quality Checklist` section",
        ))
    if not has_threshold:
        out.append(Finding(
            "E063", start + 1,
            "'## Quality Checklist' must mention a pass threshold (regex: 'pass threshold')",
            anti_pattern="4. Missing `## Quality Checklist` section",
        ))
    return out


# ----- orchestration -----

def run_all_checks(path: str) -> List[Finding]:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    lines = text.splitlines()
    code_ranges = find_fenced_code_ranges(lines)
    findings: List[Finding] = []
    findings.extend(check_frontmatter(lines))
    _title_idx, title_findings = locate_title_and_header(lines)
    findings.extend(title_findings)
    h2s = find_h2_sections(lines, code_ranges)
    findings.extend(check_required_sections(h2s))
    findings.extend(check_h2_sentence_case(h2s))
    findings.extend(check_phases(lines, h2s, code_ranges))
    findings.extend(check_style_rules(lines, code_ranges))
    findings.extend(check_length(lines))
    findings.extend(check_routing_table(lines, h2s, code_ranges))
    findings.extend(check_defaults_table(lines, h2s, code_ranges))
    findings.extend(check_quality_checklist(lines, h2s, code_ranges))
    return findings


def group_findings(findings: List[Finding]) -> dict:
    buckets: dict = {}
    code_section = {
        "E001": "Frontmatter", "E002": "Frontmatter", "E003": "Frontmatter",
        "E004": "Frontmatter", "E005": "Frontmatter",
        "E010": "Title/Header", "E011": "Title/Header", "E012": "Title/Header",
        "E013": "Title/Header", "E014": "Title/Header", "E015": "Title/Header",
        "E020": "Required sections", "E021": "Required sections",
        "E022": "Required sections", "E023": "Required sections",
        "E024": "Required sections",
        "E030": "Phases", "E031": "Phases", "E032": "Phases",
        "E033": "Phases", "E034": "Phases",
        "E040": "Style", "E041": "Style",
        "E050": "Length", "W051": "Length",
        "E060": "Routing table", "E061": "Defaults table",
        "E062": "Quality Checklist", "E063": "Quality Checklist",
    }
    for f in findings:
        section = code_section.get(f.code, "Other")
        buckets.setdefault(section, []).append(f)
    return buckets


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Lint a steering-workflow markdown file.")
    parser.add_argument("path", help="path to workflow .md")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    try:
        findings = run_all_checks(args.path)
    except FileNotFoundError:
        print(f"ERROR: file not found: {args.path}", file=sys.stderr)
        return 1

    errors = [f for f in findings if f.code.startswith("E")]
    warnings = [f for f in findings if f.code.startswith("W")]

    if args.json:
        out = {
            "path": args.path,
            "pass": len(errors) == 0,
            "findings": [asdict(f) for f in findings],
        }
        print(json.dumps(out, indent=2))
        return 0 if not errors else 1

    print(f"quick_validate: {args.path}")
    if not findings:
        print("  (no findings)")
    else:
        buckets = group_findings(findings)
        for section in [
            "Frontmatter", "Title/Header", "Required sections",
            "Phases", "Style", "Routing table", "Defaults table",
            "Quality Checklist", "Length", "Other",
        ]:
            items = buckets.get(section)
            if not items:
                continue
            print(f"\n{section}:")
            for f in items:
                print(f.format())
    print()
    if errors:
        print(f"FAIL — {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    else:
        print(f"PASS — 0 error(s), {len(warnings)} warning(s)")
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
