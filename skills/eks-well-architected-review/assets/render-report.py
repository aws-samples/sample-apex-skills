#!/usr/bin/env python3
"""Render an EKS Well-Architected review as a self-contained Cloudscape-styled HTML report.

Usage:  python3 render-report.py <WORK_DIR> [-o report.html]

Reads ONLY the files the collection step wrote and the scorers produced:
  scores.json      pillar + overall scores (authoritative — never recomputed here)
  results.jsonl    one line per question: pillar, id, track, state, detail
  drift.md         the 10 baseline checks, already rendered as a markdown table
  cluster.json     header facts (name, region, version, compute mode)
  nodes.json       node count
  podidentity.json / oidcproviders.json / fargate.json  compute + identity context

WHY THIS IS A SCRIPT AND NOT PROSE INSTRUCTIONS
Every number in the output is copied from scores.json / results.jsonl. The renderer does no
arithmetic and makes no judgement, so the HTML inherits the skill's determinism property: the
same work dir always produces byte-identical HTML. Asking an agent to hand-write 131 findings
as styled HTML would be slower, non-deterministic, and would drift from the design tokens.

DESIGN
Cloudscape Design System (https://cloudscape.aws.dev). Token values are transcribed from the
design-tokens reference and carried as CSS custom properties, with the documented light and dark
values wired to prefers-color-scheme. No network requests, no external CSS or JS — the report is
one file that opens offline, which the skill's "all data stays local" contract requires.
"""
import argparse
import html
import json
import pathlib
import re
import sys

# ---------------------------------------------------------------------------
# Severity weights — MUST stay identical to SKILL.md Step 7 / reduce.sh sev().
# Used only to LABEL a finding, never to compute a score.
# ---------------------------------------------------------------------------
SEV3 = {
    "sec-2", "sec-6", "sec-18", "rbac-1", "sec-21", "sec-29", "sec-4", "sec-30",
    "net-2", "sec-11", "podsec-2", "podsec-4", "lens-11", "sec-26",
    "ope-5", "ope-6", "ope-11", "ope-12",
    "rel-1", "rel-6", "rel-7", "rel-12", "rel-13", "lens-15", "perf-1",
    "cost-6", "cost-8", "cost-9",
}
SEV1 = {
    "sec-5", "sec-17", "sec-8", "sec-23", "sec-27", "sec-28", "net-1", "net-3",
    "sec-12", "sec-32", "sec-35", "sec-36", "sec-37",
    "ope-3", "ope-4", "ope-10", "ope-14", "ope-17", "ope-18",
    "fargate-1", "fargate-2", "fargate-3", "fargate-4", "lens-1",
    "rel-11", "rel-15", "rel-16", "rel-17", "rel-19", "rel-20", "rel-23", "lens-2", "lens-3",
    "perf-2", "perf-4", "perf-5", "perf-6", "lens-5", "lens-8", "lens-9", "lens-10",
    "cost-3", "cost-4", "lens-4", "lens-13", "lens-16",
}

PILLARS = [
    ("operational-excellence", "Operational Excellence"),
    ("security", "Security"),
    ("reliability", "Reliability"),
    ("performance-efficiency", "Performance Efficiency"),
    ("cost-optimization", "Cost Optimization"),
]

# state -> (Cloudscape status-indicator type, label)
STATE_UI = {
    "all":  ("success", "Pass"),
    "most": ("info", "Mostly"),
    "some": ("warning", "Partial"),
    "none": ("error", "Fail"),
    "na":   ("inactive", "Not applicable"),
}


def sev_of(qid):
    return 3 if qid in SEV3 else 1 if qid in SEV1 else 2


def rating(score):
    if not isinstance(score, (int, float)):
        return "—"
    return ("Excellent" if score >= 90 else "Good" if score >= 80 else
            "Fair" if score >= 70 else "Needs improvement" if score >= 60 else "Poor")


def risk(score):
    """Risk band per SKILL.md Step 7: >=80 LOW, >=60 MEDIUM, <60 HIGH."""
    if not isinstance(score, (int, float)):
        return ("inactive", "Not assessed")
    return (("success", "Low") if score >= 80 else
            ("warning", "Medium") if score >= 60 else ("error", "High"))


def e(s):
    return html.escape(str(s), quote=True)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
def load(work):
    work = pathlib.Path(work)

    def j(name, default=None):
        p = work / name
        if not p.exists():
            if default is None:
                sys.exit(f"render-report: required file missing: {p}")
            return default
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError as exc:
            sys.exit(f"render-report: {p} is not valid JSON ({exc}) — refusing to render a "
                     f"report from data the scorers could not have read either")

    scores = j("scores.json")
    results = []
    rp = work / "results.jsonl"
    if not rp.exists():
        sys.exit(f"render-report: required file missing: {rp}")
    for line in rp.read_text().splitlines():
        if line.strip():
            results.append(json.loads(line))

    drift = (work / "drift.md").read_text() if (work / "drift.md").exists() else ""
    return {
        "scores": scores,
        "results": results,
        "drift": drift,
        "cluster": j("cluster.json", {}).get("cluster", {}),
        "nodes": j("nodes.json", {"items": []}).get("items", []),
        "fargate": j("fargate.json", {}).get("fargateProfileNames", []),
        "podidentity": j("podidentity.json", {}).get("associations", []),
        "oidcproviders": j("oidcproviders.json", {}).get("OpenIDConnectProviderList", []),
        "pods": j("pods.json", {"items": []}).get("items", []),
    }


def question_titles(ref_dir):
    """Map question id -> human-readable question text, parsed from the reference files.

    results.jsonl carries only an id and a machine detail, so without this the report would be a
    wall of `sec-11  none  0/4 PSS labels`. Titles are read from the same files that define the
    questions, so they cannot drift from the scorers.
    """
    titles = {}
    ref = pathlib.Path(ref_dir)
    if not ref.is_dir():
        return titles
    for md in sorted(ref.rglob("*.md")):
        for m in re.finditer(r"^###\s+([a-z]+-\d+)\s*:\s*(.+?)\s*$", md.read_text(), re.M):
            titles.setdefault(m.group(1), m.group(2))
    return titles


def parse_drift(md):
    """Pull (num, check, ok, evidence) out of the already-rendered drift markdown table."""
    rows = []
    for line in md.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4 or cells[0] in ("#", "---") or set(cells[0]) <= set("-"):
            continue
        if not cells[0].isdigit():
            continue
        rows.append((cells[0], cells[1], "✅" in cells[2], cells[3]))
    return rows


# ---------------------------------------------------------------------------
# Cloudscape stylesheet — token values transcribed from the design-tokens reference.
#
# Split three ways so a theme can be FORCED, not just offered to prefers-color-scheme:
#   TOKENS_SHARED  typography, spacing, radius — identical in both visual modes
#   TOKENS_LIGHT / TOKENS_DARK   the two colour sets Cloudscape documents
#   BASE           every selector, written against the token names only
# `--theme auto` (default) ships both and lets the OS choose; `dark`/`light` pin one, which is what
# you need when the report is emailed, attached to a ticket, or printed, since the viewer's OS
# setting is not yours to predict.
# ---------------------------------------------------------------------------
TOKENS_LIGHT = """
  /* Colors — Cloudscape design tokens, light mode */
  --color-background-layout-main:#ffffff;
  --color-background-container-content:#ffffff;
  --color-background-home-header:#0f141a;
  --color-background-layout-panel:#f9f9fa;
  --color-background-cell-shaded:#f6f6f9;
  --color-text-heading-default:#0f141a;
  --color-text-body-default:#0f141a;
  --color-text-body-secondary:#424650;
  --color-text-status-error:#db0000;
  --color-text-status-success:#00802f;
  --color-text-status-warning:#855900;
  --color-text-status-info:#006ce0;
  --color-text-status-inactive:#656871;
  --color-text-link-default:#006ce0;
  --color-text-inverted:#ffffff;
  --color-border-divider-default:#c6c6cd;
  --color-border-divider-secondary:#ebebf0;
  --color-background-status-error:#fff5f5;
  --color-background-status-success:#effff1;
  --color-background-status-warning:#fffef0;
  --color-background-status-info:#f0fbff;
  --color-border-status-error:#db0000;
  --color-border-status-success:#00802f;
  --color-border-status-warning:#855900;
  --color-border-status-info:#006ce0;
  --color-severity-critical:#870303;
  --color-severity-high:#ce3311;
  --color-severity-medium:#f89256;
  --color-severity-low:#f2cd54;
  --color-severity-neutral:#656871;
  --color-background-badge-grey:#424650;
  --shadow-container:0 1px 8px 2px rgba(0,7,22,.12);
"""

TOKENS_SHARED = """
  /* Typography */
  --font-family-base:"Amazon Ember","Amazon Ember Display",Helvetica,Arial,sans-serif;
  --font-family-monospace:Monaco,Menlo,Consolas,"Courier Prime",Courier,"Courier New",monospace;
  --font-size-display-l:42px;   --line-height-display-l:48px;
  --font-size-heading-xl:24px;  --line-height-heading-xl:30px;
  --font-size-heading-l:20px;   --line-height-heading-l:24px;
  --font-size-heading-m:18px;   --line-height-heading-m:22px;
  --font-size-heading-s:16px;   --line-height-heading-s:20px;
  --font-size-body-m:14px;      --line-height-body-m:20px;
  --font-size-body-s:12px;      --line-height-body-s:16px;
  --font-weight-heavy:700; --font-weight-normal:400; --font-weight-lighter:300;

  /* Spacing + radius */
  --space-xxxs:2px; --space-xxs:4px; --space-xs:8px; --space-s:12px;
  --space-m:16px; --space-l:20px; --space-xl:24px; --space-xxl:32px; --space-xxxl:40px;
  --border-radius-container:16px; --border-radius-badge:4px; --border-radius-input:8px;
"""

TOKENS_DARK = """
    /* Colors — Cloudscape design tokens, dark mode */
    --color-background-layout-main:#0f141a;
    --color-background-container-content:#161d26;
    --color-background-layout-panel:#1b232d;
    --color-background-cell-shaded:#1b232d;
    --color-text-heading-default:#ebebf0;
    --color-text-body-default:#c6c6cd;
    --color-text-body-secondary:#c6c6cd;
    --color-text-status-error:#ff7a7a;
    --color-text-status-success:#2bb534;
    --color-text-status-warning:#fbd332;
    --color-text-status-info:#42b4ff;
    --color-text-status-inactive:#a4a4ad;
    --color-text-link-default:#42b4ff;
    --color-border-divider-default:#424650;
    --color-border-divider-secondary:#232b37;
    --color-background-status-error:#1f0000;
    --color-background-status-success:#001401;
    --color-background-status-warning:#191100;
    --color-background-status-info:#001129;
    --color-border-status-error:#ff7a7a;
    --color-border-status-success:#2bb534;
    --color-border-status-warning:#fbd332;
    --color-border-status-info:#42b4ff;
    --color-severity-critical:#d63f38;
    --color-severity-high:#fe6e73;
    --color-background-badge-grey:#656871;
    --shadow-container:0 1px 8px 2px rgba(0,7,22,.6);
"""

BASE = """
*,*::before,*::after{box-sizing:border-box}
body{
  margin:0;background:var(--color-background-layout-main);
  color:var(--color-text-body-default);
  font-family:var(--font-family-base);
  font-size:var(--font-size-body-m);line-height:var(--line-height-body-m);
  -webkit-font-smoothing:antialiased;
}
code,.mono,td.num{font-family:var(--font-family-monospace)}

/* --- Top navigation (Cloudscape home header surface) --- */
.top-nav{
  background:var(--color-background-home-header);color:#ffffff;
  padding:var(--space-s) var(--space-xl);
  display:flex;align-items:center;gap:var(--space-s);flex-wrap:wrap;
}
.top-nav .product{font-size:var(--font-size-heading-s);font-weight:var(--font-weight-heavy)}
.top-nav .sep{color:#8c8c94}
.top-nav .ctx{font-size:var(--font-size-body-s);color:#c6c6cd;font-family:var(--font-family-monospace)}

/* --- Theme toggle (top right) ---
   `hidden` in the markup and un-hidden by the inline script, so a viewer with JavaScript disabled
   or stripped (some mail clients, CSP-restricted wikis) never sees a dead control — the report just
   follows prefers-color-scheme, which needs no script at all. */
.theme-toggle{
  margin-left:auto;display:inline-flex;align-items:center;gap:var(--space-xxs);
  background:transparent;color:#ebebf0;cursor:pointer;
  border:1px solid #424650;border-radius:var(--border-radius-input);
  padding:var(--space-xxs) var(--space-xs);
  font-family:inherit;font-size:var(--font-size-body-s);font-weight:var(--font-weight-heavy);
}
.theme-toggle:hover{background:#232b37;border-color:#656871}
.theme-toggle:focus-visible{outline:2px solid #42b4ff;outline-offset:2px}
.theme-toggle svg{width:14px;height:14px;flex:none}
.theme-toggle[hidden]{display:none}
/* Show the icon for the mode you will GET, not the one you are in. */
.theme-toggle .i-sun{display:none}
.theme-toggle[aria-pressed="true"] .i-sun{display:inline}
.theme-toggle[aria-pressed="true"] .i-moon{display:none}
@media print{.theme-toggle{display:none}}

/* --- Layout --- */
.layout{max-width:1200px;margin:0 auto;padding:var(--space-xl)}
.stack>*+*{margin-top:var(--space-l)}
.grid{display:grid;gap:var(--space-l)}
@media(min-width:900px){.grid.cols-2{grid-template-columns:repeat(2,1fr)}
  .grid.cols-3{grid-template-columns:repeat(3,1fr)}
  .grid.cols-4{grid-template-columns:repeat(4,1fr)}}

/* --- Page header --- */
.page-header h1{
  font-size:var(--font-size-heading-xl);line-height:var(--line-height-heading-xl);
  font-weight:var(--font-weight-heavy);margin:0;color:var(--color-text-heading-default)
}
.page-header p{margin:var(--space-xxs) 0 0;color:var(--color-text-body-secondary)}

/* --- Container --- */
.container{
  background:var(--color-background-container-content);
  border-radius:var(--border-radius-container);
  box-shadow:var(--shadow-container);
  border:1px solid transparent;overflow:hidden;
}
.container>.hd{
  padding:var(--space-m) var(--space-l);
  border-bottom:1px solid var(--color-border-divider-secondary);
  display:flex;align-items:baseline;gap:var(--space-xs);flex-wrap:wrap;
}
.container>.hd h2{
  margin:0;font-size:var(--font-size-heading-l);line-height:var(--line-height-heading-l);
  font-weight:var(--font-weight-heavy);color:var(--color-text-heading-default)
}
.container>.hd .counter{color:var(--color-text-body-secondary);font-weight:var(--font-weight-normal)}
.container>.hd .desc{flex-basis:100%;color:var(--color-text-body-secondary);font-size:var(--font-size-body-s)}
.container>.bd{padding:var(--space-l)}
.container>.bd.flush{padding:0}

/* --- Key/value pairs --- */
.kv dt{
  font-size:var(--font-size-body-s);line-height:var(--line-height-body-s);
  color:var(--color-text-body-secondary);margin:0 0 var(--space-xxxs)
}
.kv dd{margin:0 0 var(--space-m);font-family:var(--font-family-monospace)}
.kv dd:last-child{margin-bottom:0}

/* --- Big score --- */
.score-hero{display:flex;align-items:baseline;gap:var(--space-s);flex-wrap:wrap}
.score-hero .val{
  font-size:var(--font-size-display-l);line-height:var(--line-height-display-l);
  font-weight:var(--font-weight-heavy);font-family:var(--font-family-monospace)
}
.score-hero .den{color:var(--color-text-body-secondary);font-size:var(--font-size-heading-l)}
.score-hero .rating{font-size:var(--font-size-heading-s);color:var(--color-text-body-secondary)}

/* --- Table --- */
table{width:100%;border-collapse:collapse;font-size:var(--font-size-body-m)}
thead th{
  text-align:left;padding:var(--space-xs) var(--space-l);
  font-size:var(--font-size-body-s);line-height:var(--line-height-body-s);
  font-weight:var(--font-weight-heavy);color:var(--color-text-body-secondary);
  border-bottom:1px solid var(--color-border-divider-default);white-space:nowrap;
}
tbody td{
  padding:var(--space-xs) var(--space-l);vertical-align:top;
  border-bottom:1px solid var(--color-border-divider-secondary);
}
tbody tr:last-child td{border-bottom:none}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
td.qid{font-family:var(--font-family-monospace);white-space:nowrap;color:var(--color-text-body-secondary)}
td.detail{color:var(--color-text-body-secondary);font-family:var(--font-family-monospace);font-size:var(--font-size-body-s)}
.shaded{background:var(--color-background-cell-shaded)}

/* --- Status indicator --- */
.si{display:inline-flex;align-items:center;gap:var(--space-xxs);white-space:nowrap}
.si-success{color:var(--color-text-status-success)}
.si-error{color:var(--color-text-status-error)}
.si-warning{color:var(--color-text-status-warning)}
.si-info{color:var(--color-text-status-info)}
.si-inactive{color:var(--color-text-status-inactive)}
.si .ico{font-weight:var(--font-weight-heavy)}

/* --- Badge --- */
.badge{
  display:inline-block;border-radius:var(--border-radius-badge);
  padding:0 var(--space-xxs);font-size:var(--font-size-body-s);line-height:18px;
  font-weight:var(--font-weight-heavy);color:#f9f9fa;background:var(--color-background-badge-grey);
  white-space:nowrap;
}
.badge-critical{background:var(--color-severity-critical)}
.badge-high{background:var(--color-severity-high)}
.badge-medium{background:var(--color-severity-medium);color:#0f141a}
.badge-low{background:var(--color-severity-low);color:#0f141a}
.badge-neutral{background:var(--color-severity-neutral)}

/* --- Alert --- */
.alert{
  border:2px solid;border-radius:var(--border-radius-input);
  padding:var(--space-s) var(--space-m);display:flex;gap:var(--space-xs);align-items:flex-start;
}
.alert .ico{font-weight:var(--font-weight-heavy);flex:none}
.alert h3{margin:0 0 var(--space-xxs);font-size:var(--font-size-body-m);font-weight:var(--font-weight-heavy)}
.alert p{margin:0}
.alert p+p{margin-top:var(--space-xs)}
.alert-error{background:var(--color-background-status-error);border-color:var(--color-border-status-error)}
.alert-warning{background:var(--color-background-status-warning);border-color:var(--color-border-status-warning)}
.alert-info{background:var(--color-background-status-info);border-color:var(--color-border-status-info)}
.alert-success{background:var(--color-background-status-success);border-color:var(--color-border-status-success)}

/* --- Progress bar (pillar score) --- */
/* inline-block, not inline: a bare <span> ignores height and the bar renders as an empty cell */
.bar{display:inline-block;width:120px;height:var(--space-xs);border-radius:var(--space-xxs);
  background:var(--color-border-divider-secondary);overflow:hidden;vertical-align:middle}
.bar>i{display:block;height:100%;border-radius:var(--space-xxs)}

.muted{color:var(--color-text-body-secondary)}
.small{font-size:var(--font-size-body-s);line-height:var(--line-height-body-s)}
ul.plain{margin:0;padding-left:var(--space-l)}
ul.plain li+li{margin-top:var(--space-xxs)}
footer.page{
  margin-top:var(--space-xl);padding:var(--space-l) 0 0;
  border-top:1px solid var(--color-border-divider-secondary);
  color:var(--color-text-body-secondary);font-size:var(--font-size-body-s);
}
@media print{
  .container{box-shadow:none;border:1px solid var(--color-border-divider-default);break-inside:avoid}
  .top-nav{-webkit-print-color-adjust:exact;print-color-adjust:exact}
}
"""

# A dark report must not be bleached to white paper on print: the surfaces stay dark and the browser
# is told to honour them. Only the auto/light themes fall back to white for ink economy.
PRINT_LIGHT = "@media print{body{background:#fff}}\n"
PRINT_DARK = ("@media print{body,.container{-webkit-print-color-adjust:exact;"
              "print-color-adjust:exact}}\n")


def stylesheet(theme):
    """Assemble the stylesheet for one of: auto (default, togglable), light, dark.

    In `auto` the resolution order is CSS-only, so the report is correct before any script runs:
      1. light tokens as the base;
      2. OS dark  -> dark tokens, UNLESS the reader has pinned light via [data-theme=light];
      3. reader pinned dark -> dark tokens, whatever the OS says.
    The toggle only sets/clears `data-theme` on <html>; all four states are decided by CSS.
    """
    if theme == "light":
        return f":root {{{TOKENS_LIGHT}{TOKENS_SHARED}}}\n{BASE}{PRINT_LIGHT}"
    if theme == "dark":
        # Dark values override the light ones in the SAME rule, so a token missed in TOKENS_DARK
        # falls back to its light value rather than to nothing — a missing colour is visible as a
        # contrast bug, whereas an unset custom property silently renders as `initial`.
        return f":root {{{TOKENS_LIGHT}{TOKENS_DARK}{TOKENS_SHARED}}}\n{BASE}{PRINT_DARK}"
    return (
        f":root {{{TOKENS_LIGHT}{TOKENS_SHARED}}}\n"
        f'@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) '
        f"{{{TOKENS_DARK}}} }}\n"
        f':root[data-theme="dark"] {{{TOKENS_DARK}}}\n'
        f"{BASE}"
        # Print always uses the light set, whichever theme is on screen. Printing a dark report onto
        # white paper would otherwise mix a forced-white background with light-on-dark text colours,
        # which is the one combination that is actually unreadable.
        f'@media print {{ :root, :root[data-theme="dark"] {{{TOKENS_LIGHT}}} body{{background:#fff}} }}\n'
    )


# `color-scheme` makes the browser render its OWN widgets — scrollbars, focus rings, form controls —
# to match. Without it a dark report keeps a bright white scrollbar down the side.
COLOR_SCHEME = {"auto": "light dark", "light": "light", "dark": "dark"}

# Sun / moon drawn inline: no icon font, no sprite, no network. Two paths, both currentColor.
ICON_MOON = ('<svg class="i-moon" viewBox="0 0 16 16" fill="none" stroke="currentColor" '
             'stroke-width="1.5" aria-hidden="true"><path d="M13.5 10.2A6 6 0 1 1 5.8 2.5'
             'a4.8 4.8 0 0 0 7.7 7.7Z"/></svg>')
ICON_SUN = ('<svg class="i-sun" viewBox="0 0 16 16" fill="none" stroke="currentColor" '
            'stroke-width="1.5" aria-hidden="true"><circle cx="8" cy="8" r="3.1"/>'
            '<path d="M8 .9v1.8M8 13.3v1.8M.9 8h1.8M13.3 8h1.8M2.98 2.98 4.25 4.25'
            'M11.75 11.75l1.27 1.27M13.02 2.98 11.75 4.25M4.25 11.75 2.98 13.02"/></svg>')

TOGGLE_HTML = (
    '<button id="theme-toggle" class="theme-toggle" type="button" hidden '
    'aria-pressed="false" aria-live="polite" title="Switch between light and dark theme">'
    f'{ICON_MOON}{ICON_SUN}<span class="label">Dark</span></button>')

# Inline, ~20 lines, no network of any kind: no fetch, no XHR, no import, no remote src.
# Wrapped in try/catch because localStorage throws on file:// in some browsers, and a theme
# preference is not worth breaking the report over.
TOGGLE_JS = """
(function(){
  var r=document.documentElement,b=document.getElementById('theme-toggle'),K='eks-war-theme';
  if(!b)return;
  var mq=window.matchMedia?window.matchMedia('(prefers-color-scheme: dark)'):null;
  function isDark(){var p=r.getAttribute('data-theme');
    return p?p==='dark':!!(mq&&mq.matches);}
  function paint(){var d=isDark();
    b.setAttribute('aria-pressed',d?'true':'false');
    b.querySelector('.label').textContent=d?'Light':'Dark';
    b.title='Switch to '+(d?'light':'dark')+' theme';}
  var saved=null;try{saved=localStorage.getItem(K);}catch(e){}
  if(saved==='dark'||saved==='light')r.setAttribute('data-theme',saved);
  paint();b.hidden=false;
  b.addEventListener('click',function(){
    var next=isDark()?'light':'dark';
    r.setAttribute('data-theme',next);
    try{localStorage.setItem(K,next);}catch(e){}
    paint();});
  if(mq&&mq.addEventListener)mq.addEventListener('change',function(){
    if(!r.getAttribute('data-theme'))paint();});
})();
"""


def si(kind, label):
    ico = {"success": "✔", "error": "✕", "warning": "⚠",
           "info": "ℹ", "inactive": "–"}[kind]
    return (f'<span class="si si-{kind}"><span class="ico" aria-hidden="true">{ico}</span>'
            f'<span>{e(label)}</span></span>')


def sev_badge(qid):
    s = sev_of(qid)
    cls, label = {3: ("high", "High"), 2: ("medium", "Medium"), 1: ("low", "Low")}[s]
    return f'<span class="badge badge-{cls}">{label}</span>'


def bar(score):
    if not isinstance(score, (int, float)):
        return '<span class="muted">&mdash;</span>'
    kind = risk(score)[0]
    color = {"success": "var(--color-text-status-success)",
             "warning": "var(--color-text-status-warning)",
             "error": "var(--color-text-status-error)",
             "inactive": "var(--color-text-status-inactive)"}[kind]
    return (f'<span class="bar" role="img" aria-label="{score} out of 100">'
            f'<i style="width:{max(0,min(100,score))}%;background:{color}"></i></span>')


def container(title, body, counter=None, desc=None, flush=False):
    c = f' <span class="counter">({e(counter)})</span>' if counter else ""
    d = f'<div class="desc">{e(desc)}</div>' if desc else ""
    return (f'<section class="container"><div class="hd"><h2>{e(title)}</h2>{c}{d}</div>'
            f'<div class="bd{" flush" if flush else ""}">{body}</div></section>')


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def build(data, titles, toggle=True):
    sc = data["scores"]
    res = data["results"]
    cl = data["cluster"]
    overall = sc.get("technical_overall")
    measured = [r for r in res if r.get("track") == "measured"]
    governance = [r for r in res if r.get("track") == "governance"]
    by_pillar = {k: {p["pillar"]: p for p in sc.get("pillars", [])}.get(k, {})
                 for k, _ in PILLARS}

    region = (cl.get("arn", "").split(":")[3] if cl.get("arn") else "")
    node_count = len(data["nodes"])
    fargate_nodes = sum(1 for n in data["nodes"]
                        if (n.get("metadata", {}).get("labels") or {})
                        .get("eks.amazonaws.com/compute-type") == "fargate")
    if cl.get("computeConfig", {}).get("enabled") is True:
        mode = "EKS Auto Mode"
    elif data["fargate"] and fargate_nodes == node_count and node_count:
        mode = "Fargate only"
    else:
        mode = "Standard"

    out = []

    # ---- top navigation -----------------------------------------------------
    out.append(
        '<div class="top-nav"><span class="product">EKS Well-Architected Review</span>'
        f'<span class="sep">/</span><span class="ctx">{e(cl.get("name","(unknown cluster)"))}</span>'
        f'<span class="sep">/</span><span class="ctx">{e(region or "unknown region")}</span>'
        f'{TOGGLE_HTML if toggle else ""}</div>')

    out.append('<div class="layout stack">')

    # ---- page header --------------------------------------------------------
    out.append(
        '<div class="page-header"><h1>Well-Architected review</h1>'
        f'<p>Deterministic review of <code>{e(cl.get("name",""))}</code>. '
        f'{len(measured)} measured questions answered from one data collection; '
        f'{len(governance)} governance questions are process-only.</p></div>')

    # ---- alert when the overall is withheld --------------------------------
    if not isinstance(overall, (int, float)):
        insufficient = [n for (k, n) in PILLARS
                        if not isinstance(by_pillar[k].get("score"), (int, float))]
        out.append(
            '<div class="alert alert-warning"><span class="ico" aria-hidden="true">&#9888;</span>'
            '<div><h3>Overall score withheld</h3>'
            f'<p>{e(str(overall))}. A technical overall is only published when at least four '
            'pillars clear the 50% coverage gate.</p>'
            f'<p class="small">Below the gate: {e(", ".join(insufficient)) or "none"}. '
            'Too little of this cluster is observable to compress into a single number; the '
            'pillar detail below is still valid.</p></div></div>')

    # ---- executive summary -------------------------------------------------
    if isinstance(overall, (int, float)):
        kind, label = risk(overall)
        hero = (f'<div class="score-hero"><span class="val">{overall}</span>'
                f'<span class="den">/ 100</span>'
                f'<span class="rating">{e(rating(overall))}</span>'
                f'<span>{si(kind, label + " risk")}</span></div>')
    else:
        hero = f'<div class="score-hero"><span class="val muted">&mdash;</span>' \
               f'<span class="rating">{e(str(overall))}</span></div>'

    rows = []
    for key, name in PILLARS:
        p = by_pillar[key]
        s = p.get("score")
        appl, tot = p.get("applicable", 0), p.get("total", 0)
        rk, rl = risk(s)
        shown = f"{s}" if isinstance(s, (int, float)) else "Insufficient coverage"
        rows.append(
            f'<tr><td>{e(name)}</td>'
            f'<td class="num">{e(shown)}</td>'
            f'<td>{bar(s)}</td>'
            f'<td>{e(rating(s))}</td>'
            f'<td>{si(rk, rl)}</td>'
            f'<td class="num">{appl}&thinsp;/&thinsp;{tot}</td></tr>')
    table = (
        '<table><thead><tr><th>Pillar</th><th class="num">Score</th><th></th>'
        '<th>Rating</th><th>Risk</th><th class="num">Coverage</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>')
    out.append(container("Executive summary",
                         f'<div class="bd" style="padding:0 0 var(--space-l)">{hero}</div>' + table,
                         desc="Technical score is the mean of the numeric pillar scores. "
                              "Coverage is applicable of measured questions.",
                         flush=False))

    # ---- top priorities: worst High-severity findings first ----------------
    order = {"none": 0, "some": 1, "most": 2}
    prio = sorted((r for r in measured if r.get("state") in order),
                  key=lambda r: (-sev_of(r["id"]), order[r["state"]]))[:5]
    if prio:
        items = "".join(
            f'<tr><td class="qid">{e(r["id"])}</td><td>{sev_badge(r["id"])}</td>'
            f'<td>{e(titles.get(r["id"], "(question text unavailable)"))}</td>'
            f'<td>{si(*STATE_UI[r["state"]])}</td>'
            f'<td class="detail">{e(r.get("detail",""))}</td></tr>'
            for r in prio)
        out.append(container(
            "Top priorities", '<table><thead><tr><th>ID</th><th>Severity</th><th>Question</th>'
            '<th>Result</th><th>Evidence</th></tr></thead>'
            f'<tbody>{items}</tbody></table>',
            counter=str(len(prio)),
            desc="Highest WAF risk weight first, then the weakest result.", flush=True))

    # ---- cluster facts -----------------------------------------------------
    workload_pods = sum(
        1 for p in data["pods"]
        if not re.match(r"^(kube-|amazon-)", (p.get("metadata", {}).get("namespace") or ""))
    )
    facts = [
        ("Cluster", cl.get("name", "—")),
        ("Region", region or "—"),
        ("Kubernetes version", cl.get("version", "—")),
        ("Platform version", cl.get("platformVersion", "—")),
        ("Compute mode", mode),
        ("Nodes", f"{node_count}"),
        ("Workload pods", f"{workload_pods}"),
        ("Support type", cl.get("upgradePolicy", {}).get("supportType", "—")),
        ("Endpoint access", "private only" if cl.get("resourcesVpcConfig", {})
            .get("endpointPublicAccess") is False else "public enabled"),
        ("Pod Identity associations", f"{len(data['podidentity'])}"),
    ]
    cols = ['<dl class="kv">' + "".join(
        f"<dt>{e(k)}</dt><dd>{e(v)}</dd>" for k, v in facts[i::3]) + "</dl>"
        for i in range(3)]
    out.append(container("Cluster", f'<div class="grid cols-3">{"".join(cols)}</div>'))

    # ---- per-pillar findings ----------------------------------------------
    for key, name in PILLARS:
        p = by_pillar[key]
        qs = [r for r in measured if r.get("pillar") == key]
        if not qs:
            continue
        rank = {"none": 0, "some": 1, "most": 2, "all": 3, "na": 4}
        qs.sort(key=lambda r: (rank.get(r.get("state"), 9), -sev_of(r["id"]), r["id"]))
        rows = "".join(
            f'<tr><td class="qid">{e(r["id"])}</td><td>{sev_badge(r["id"])}</td>'
            f'<td>{e(titles.get(r["id"], "(question text unavailable)"))}</td>'
            f'<td>{si(*STATE_UI.get(r.get("state"), ("inactive", r.get("state","?"))))}</td>'
            f'<td class="detail">{e(r.get("detail",""))}</td></tr>' for r in qs)
        s = p.get("score")
        head = (f'{s}/100' if isinstance(s, (int, float)) else "Insufficient coverage")
        counts = {k: sum(1 for r in qs if r.get("state") == k)
                  for k in ("all", "most", "some", "none", "na")}
        summary = (f'{head} &middot; {counts["all"]} pass, {counts["most"]} mostly, '
                   f'{counts["some"]} partial, {counts["none"]} fail, {counts["na"]} n/a')
        out.append(container(
            name,
            '<table><thead><tr><th>ID</th><th>Severity</th><th>Question</th>'
            '<th>Result</th><th>Evidence</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>',
            counter=f'{p.get("applicable",0)} of {p.get("total",0)} applicable',
            desc=re.sub("<[^>]+>", "", summary).replace("&middot;", "·"),
            flush=True))

    # ---- drift -------------------------------------------------------------
    drows = parse_drift(data["drift"])
    if drows:
        passed = sum(1 for _, _, ok, _ in drows if ok)
        rows = "".join(
            f'<tr><td class="num">{e(n)}</td><td>{e(chk)}</td>'
            f'<td>{si("success","Pass") if ok else si("error","Fail")}</td>'
            f'<td class="detail">{e(ev)}</td></tr>' for n, chk, ok, ev in drows)
        out.append(container(
            "Baseline drift detection",
            '<table><thead><tr><th class="num">#</th><th>Check</th><th>Status</th>'
            f'<th>Evidence</th></tr></thead><tbody>{rows}</tbody></table>',
            counter=f"{passed} of {len(drows)} passing",
            desc="Pass/fail baseline checks. Reported separately and never folded into a "
                 "pillar score.", flush=True))

    # ---- governance --------------------------------------------------------
    g = sc.get("governance", {})
    gscore = g.get("score")
    if gscore == "Not Assessed" or not governance:
        body = (
            '<div class="alert alert-info"><span class="ico" aria-hidden="true">&#8505;</span>'
            f'<div><h3>{g.get("answered",0)} of {g.get("total",len(governance))} answered '
            '&mdash; Not Assessed</h3>'
            '<p>Governance questions cover process rather than cluster state (upgrade cadence, '
            'change management, environment separation, secret rotation, compliance scanning, '
            'incident response, DR testing). They have no signal in <code>aws</code> or '
            '<code>kubectl</code> output.</p>'
            '<p class="small">They were not guessed and are excluded from every score above. '
            'Re-run in interactive mode to have them asked and scored separately.</p>'
            '</div></div>')
    else:
        body = (f'<div class="score-hero"><span class="val">{e(gscore)}</span>'
                f'<span class="den">/ 100</span><span class="rating">'
                f'{g.get("answered",0)} of {g.get("total",0)} answered</span></div>')
    out.append(container("Governance", body))

    # ---- method ------------------------------------------------------------
    out.append(container("Method", (
        '<ul class="plain">'
        '<li>Every score is produced by a fixed <code>jq</code> detection over a single data '
        'collection. Thresholds live in the detections, not in judgement, so the same collected '
        'data always yields the same score.</li>'
        '<li>State to score: <code>all</code>=100, <code>most</code>=75, <code>some</code>=50, '
        '<code>none</code>=0. <code>na</code> is excluded from both numerator and denominator, '
        'so a question that does not apply cannot earn or cost points.</li>'
        '<li>Each question carries a WAF risk weight — High=3, Medium=2, Low=1 — shown in the '
        'Severity column. A pillar score is the severity-weighted mean of its applicable '
        'questions.</li>'
        '<li>A pillar scores only if applicable questions reach 50% of its measured total; '
        'otherwise it reports insufficient coverage. Fewer than four numeric pillars withholds '
        'the overall.</li>'
        '<li>Object checks assess cluster-owned resources only: workload namespaces (AWS-managed '
        '<code>kube-*</code>/<code>amazon-*</code> excluded), custom RBAC roles, volumes tagged '
        'to this cluster, ECR repositories referenced by cluster images.</li>'
        '<li>The Cost Optimization score measures cost <em>hygiene</em>. Spot, Graviton and '
        'Extended Support are workload- or date-dependent and are reported as narrative '
        'opportunities, not scored.</li>'
        '</ul>')))

    out.append('<footer class="page">Generated locally from collected cluster data. '
               'No data left this machine. Styled with the Cloudscape Design System.</footer>')
    out.append('</div>')
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("work", help="work directory containing scores.json and results.jsonl")
    ap.add_argument("-o", "--out", help="output HTML file (default: <work>/report.html)")
    ap.add_argument("--references", help="skill references dir, for question titles")
    ap.add_argument("--theme", choices=("auto", "light", "dark"), default="auto",
                    help="auto (default) follows the reader's OS via prefers-color-scheme; "
                         "light/dark pin one set, for when the report is emailed, attached to a "
                         "ticket, or printed and the reader's OS setting is not yours to predict")
    ap.add_argument("--both", action="store_true",
                    help="write two PINNED files: <out> in light and <out>-dark.html in dark, "
                         "neither with a toggle (for print, email or a ticket attachment)")
    ap.add_argument("--no-toggle", action="store_true",
                    help="omit the theme toggle from the auto theme; the report still follows "
                         "prefers-color-scheme, it just carries no script")
    args = ap.parse_args()

    data = load(args.work)
    ref = args.references or (pathlib.Path(__file__).resolve().parent.parent / "references")
    titles = question_titles(ref)

    cl = data["cluster"].get("name", "cluster")

    def document(theme):
        # The toggle only makes sense in `auto`: --theme light/dark exist precisely to PIN a theme
        # for print, email or a ticket attachment, where an interactive control would be misleading.
        show_toggle = theme == "auto" and not args.no_toggle
        body = build(data, titles, toggle=show_toggle)
        script = f"<script>{TOGGLE_JS}</script>" if show_toggle else ""
        return (
            "<!DOCTYPE html>\n"
            '<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="color-scheme" content="{COLOR_SCHEME[theme]}">'
            f"<title>EKS Well-Architected Review — {e(cl)}</title>"
            f"<style>{stylesheet(theme)}</style></head><body>\n{body}\n{script}\n</body></html>\n")

    base = pathlib.Path(args.out) if args.out else pathlib.Path(args.work) / "report.html"
    targets = [(base, "light" if args.both else args.theme)]
    if args.both:
        targets.append((base.with_name(base.stem + "-dark" + base.suffix), "dark"))

    for out, theme in targets:
        doc = document(theme)
        out.write_text(doc)
        print(f"wrote {out} ({len(doc):,} bytes, {theme} theme)")


if __name__ == "__main__":
    main()
