"""Print one SkillSpector report as GitHub annotations, less the findings the baseline suppresses.

Usage: annotate.py <skill dir> <report.json> <baseline.md>

A finding is suppressed only when a baseline row with verdict `accepted` or
`false positive` matches it on file, line and rule (the file path names the skill), and the
report's scanner version equals the version the baseline was made with. A moved line or another
scanner version re-opens the finding. `true positive` and `coverage gap` rows, and rule AE1, are
never suppressed. Advisory: always exits 0.
"""
import collections, json, os, re, sys

SUPPRESSIBLE = {'accepted', 'false positive'}
ROW = re.compile(r'^\| (\S+):(\d+) \| (\w+) \| (\w+) \| ([a-z ]+) \| ')
SCANNER = re.compile(r'^- Scanner: SkillSpector v(\S+) ')


def esc(s, prop=False):
    s = str(s).replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
    return s.replace(':', '%3A').replace(',', '%2C') if prop else s


def load_baseline(path):
    version, rows = None, collections.defaultdict(list)
    try:
        lines = open(path, encoding='utf-8').read().splitlines()
    except OSError:
        return None, rows
    for ln in lines:
        m = SCANNER.match(ln)
        if m and version is None:
            version = m.group(1)
        m = ROW.match(ln)
        if m:
            rows[(m.group(1), m.group(3))].append((int(m.group(2)), m.group(5).strip()))
    return version, rows


def main(skill_dir, report_path, baseline_path):
    report = json.load(open(report_path, encoding='utf-8'))
    risk = report.get('risk_assessment', {})
    issues = report.get('issues') or []
    scanner = str((report.get('metadata') or {}).get('skillspector_version') or 'unknown')
    base_version, rows = load_baseline(baseline_path)
    same_version = base_version is not None and base_version == scanner
    # Each baseline row matches at most one finding.
    left = {k: collections.Counter(v) for k, v in rows.items()}
    counts = collections.Counter()
    print(f"{skill_dir}: risk {risk.get('score')} {risk.get('severity')}, {len(issues)} finding(s)")
    for i in issues:
        loc = i.get('location') or {}
        rel = loc.get('file') or 'SKILL.md'
        line = int(loc.get('start_line') or 1)
        rule = i.get('id') or 'finding'
        path = f'{skill_dir}/{rel}'
        here = left.get((path, rule), collections.Counter())
        verdicts = [v for (n, v), c in here.items() if n == line and c > 0]
        note = ''
        if 'true positive' in verdicts or 'coverage gap' in verdicts:
            v = 'true positive' if 'true positive' in verdicts else 'coverage gap'
            here[(line, v)] -= 1
            counts['kept'] += 1
            note = f' (baseline: {v}, never suppressed)'
        elif verdicts and rule != 'AE1' and same_version:
            here[(line, verdicts[0])] -= 1
            counts['suppressed'] += 1
            continue
        elif verdicts or any(v in SUPPRESSIBLE for (n, v), c in here.items() if c > 0):
            counts['reopened'] += 1
            if verdicts and not same_version:
                note = f' (re-opened: baseline made with scanner {base_version}, this run {scanner})'
            elif verdicts:
                note = ' (re-opened: rule AE1 is never suppressed)'
            else:
                at = sorted(n for (n, v), c in here.items() if c > 0 and v in SUPPRESSIBLE)
                note = f" (re-opened: baselined for this file and rule at line {', '.join(map(str, at))}, not {line})"
        else:
            counts['new'] += 1
        sev = str(i.get('severity', '')).upper()
        level = 'warning' if sev in ('HIGH', 'CRITICAL') else 'notice'
        parts = [i.get('pattern'), i.get('explanation'), i.get('finding')]
        msg = (': '.join(str(x) for x in parts if x) or rule) + note
        print(f"::{level} file={esc(path, True)},line={line},"
              f"title={esc('SkillSpector ' + sev + ' ' + rule, True)}::{esc(msg)}")

    if base_version is None:
        base_line = f"Baseline {baseline_path} not read: nothing suppressed."
    elif not same_version:
        base_line = (f"Baseline made with SkillSpector {base_version}, this run {scanner}: "
                     "nothing suppressed, every baselined finding re-opened.")
    else:
        base_line = f"Baseline read (SkillSpector {scanner})."
    out = [f"### {skill_dir}", "",
           f"{len(issues)} finding(s): {counts['suppressed']} suppressed by the baseline, "
           f"{counts['reopened']} re-opened (line moved, other scanner version, or rule AE1), "
           f"{counts['kept']} baselined true positive or coverage gap (always shown), "
           f"{counts['new']} not in the baseline. {base_line}"]

    # Coverage: name every file the scan inspected only in part or not at all.
    comp = report.get('analysis_completeness') or {}
    partial = int(comp.get('partially_inspected_files') or 0)
    skipped = int(comp.get('entirely_uninspected_files') or 0)
    files = {}
    for e in comp.get('ledger_exceptions') or []:
        # reference_missing: the skill names a file it does not bundle; not an inspection gap.
        if e.get('path') and e.get('reason_code') != 'reference_missing':
            files.setdefault(e['path'], set()).add(str(e.get('reason_code') or e.get('outcome')))
    degraded = [s.get('analyzer_id') for s in comp.get('analyzer_statuses') or []
                if s.get('status') == 'degraded']
    out.append(f"Coverage {comp.get('status', 'unknown')}: "
               f"{comp.get('fully_inspected_files', '?')} of {comp.get('total_components', '?')} files "
               f"fully inspected, {partial} partly, {skipped} not inspected.")
    if files or partial or skipped:
        out.append("Findings are a lower bound for these files; no finding in them does not mean clean:")
        out += [f"- `{skill_dir}/{p}` ({', '.join(sorted(r))})" for p, r in sorted(files.items())]
        if partial + skipped > len(files):
            out.append(f"- {partial + skipped - len(files)} more file(s) counted as partial or not inspected; the report does not name them")
    if degraded:
        out.append(f"Analyzers that ran degraded across this skill: {', '.join(degraded)}.")
    text = '\n'.join(out) + '\n\n'
    print(text)
    with open(os.environ.get('GITHUB_STEP_SUMMARY', os.devnull), 'a', encoding='utf-8') as fh:
        fh.write(text)


if __name__ == '__main__':
    main(*sys.argv[1:4])
