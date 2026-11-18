#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Write a skill's report page from its report input (apex-base class tool).

One tool for the report and conversion files of the skills we own. A skill
moves to it in its own rebuild step; until then each skill keeps its own
report file. Stdlib only, offline.

Usage:
  report.py <template> <input>... --out <file> [--out <file>]

Templates (each keeps that skill's own page, byte for byte):
  ecs-operation-review    one markdown report in, --out <file>.html
  eks-cost-intelligence   one markdown report in, --out <file>.html
  eks-security            findings JSON (optional inventory JSON), posture
                          JSON or both, told apart by their "schema" field;
                          --out <file>.md and/or --out <file>.html

--out is the only output flag. Its suffix sets the format (.html or .md);
each format is written at most once, and only the formats the template
writes are taken.

Every input value is data. Before a page is built:
  - C0 control characters except tab, LF and CR, DEL and C1 characters
    become a space (in markdown text, and in every JSON string);
  - in HTML every value is escaped once (html.escape, quote=True), so
    markup in link text or in an href is shown as text;
  - a markdown link [text](url) becomes a link only when its url starts
    with http://, https:// or mailto: (scheme compared without case) or
    with # or /; any other link stays as its escaped text;
  - each href is held behind a placeholder until the inline passes are
    done, then put back, so no pass writes markup into an attribute.
The tool masks nothing and adds no text: a masking line the skill's report
text carries (apex.report-masking) reaches the page as it was written.

Nothing is written when an input is missing, unreadable, empty or not
UTF-8 text, when an input is not the kind the template takes, or when an
--out names an input or another --out. An output is written with mode 0600
and never through a symlink at its path; when one output cannot be written,
the outputs this run wrote are removed.

Exit: 0 written; 2 usage, input or output error (one line on stderr, no
traceback); 3 eks-security only: written, but findings or posture coverage
is below its gate.
"""
import argparse
import html
import json
import os
import re
import sys

PROG = os.path.basename(__file__)


class ReportError(Exception):
    """The report cannot be written: exit 2 with this one line."""


# ---------------------------------------------------------------- shared layer

_CONTROL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_HELD = re.compile("\x00(\\d+)\x00")
_ALLOWED_SCHEMES = ("http://", "https://", "mailto:")


def clean(text):
    """C0 control characters except tab, LF and CR, DEL and C1 characters become a space."""
    return _CONTROL.sub(" ", text)


def clean_json(value):
    if isinstance(value, str):
        return clean(value)
    if isinstance(value, list):
        return [clean_json(v) for v in value]
    if isinstance(value, dict):
        return {clean(k): clean_json(v) for k, v in value.items()}
    return value


def allowed_href(url):
    """The link-scheme allowlist: http, https and mailto (any case), # and /."""
    return url.lower().startswith(_ALLOWED_SCHEMES) or url.startswith(("#", "/"))


def hold_links(text, hrefs):
    """Turn allowed links in escaped text into anchors whose hrefs wait as placeholders.

    The text is already HTML-escaped with quote=True, so a quote or & in a
    url is &quot; or &amp; and cannot leave the attribute. clean() has
    removed every NUL byte from the input, so no input text matches a
    placeholder.
    """
    def sub(m):
        if not allowed_href(m.group(2)):
            return m.group(0)
        hrefs.append(m.group(2))
        return '<a href="\x00%d\x00">%s</a>' % (len(hrefs) - 1, m.group(1))
    return _LINK.sub(sub, text)


def restore_links(text, hrefs):
    return _HELD.sub(lambda m: hrefs[int(m.group(1))], text)


# ---------------------------------------------------------------- ecs-operation-review

ECS_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;line-height:1.6;color:#1a1a2e;background:#f0f2f5;padding:2rem}
main{max-width:1100px;margin:0 auto;background:#fff;border-radius:12px;box-shadow:0 4px 24px rgba(0,0,0,.08);padding:3rem}
h1{color:#0f1b61;border-bottom:3px solid #ff9900;padding-bottom:.5rem;margin-bottom:1.5rem;font-size:1.8rem}
h2{color:#232f3e;margin:2rem 0 1rem;padding:.5rem 0;border-bottom:2px solid #e8e8e8;font-size:1.4rem}
h3{color:#37475a;margin:1.5rem 0 .75rem;font-size:1.15rem}
h4{color:#37475a;margin:1.2rem 0 .5rem;font-size:1.05rem}
table{width:100%;border-collapse:collapse;margin:1rem 0 1.5rem;font-size:.9rem}
th{background:#232f3e;color:#fff;padding:10px 14px;text-align:left;font-weight:600}
td{padding:8px 14px;border-bottom:1px solid #e8e8e8;vertical-align:top}
tr:nth-child(even){background:#f8f9fa}
tr:hover{background:#fff3e0}
code{background:#f1f3f5;padding:2px 6px;border-radius:4px;font-size:.85em;color:#c7254e}
pre{background:#1a1a2e;color:#e8e8e8;padding:1rem;border-radius:8px;overflow-x:auto;margin:1rem 0}
pre code{background:none;color:inherit;padding:0}
blockquote{border-left:4px solid #ff9900;background:#fff8e1;padding:.75rem 1rem;margin:1rem 0;border-radius:0 8px 8px 0}
hr{border:none;border-top:2px solid #e8e8e8;margin:2rem 0}
a{color:#0073bb;text-decoration:none}a:hover{text-decoration:underline}
li{margin:.3rem 0 .3rem 1.5rem}
ul,ol{margin:.5rem 0 1rem}
strong{color:#16213e}
p{margin:.5rem 0}
.red{background:#fde8e8;color:#b71c1c;padding:2px 8px;border-radius:4px;font-weight:600;display:inline-block;font-size:.85em;min-width:60px;text-align:center}
.amber{background:#fff3e0;color:#e65100;padding:2px 8px;border-radius:4px;font-weight:600;display:inline-block;font-size:.85em;min-width:60px;text-align:center}
.green{background:#e8f5e9;color:#1b5e20;padding:2px 8px;border-radius:4px;font-weight:600;display:inline-block;font-size:.85em;min-width:60px;text-align:center}
.unknown{background:#e8eaf6;color:#283593;padding:2px 8px;border-radius:4px;font-weight:600;display:inline-block;font-size:.85em;min-width:60px;text-align:center}
.score-bar{display:flex;gap:4px;margin:1rem 0}
.score-bar div{height:28px;border-radius:4px;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:600;font-size:.8rem}
.critical-box{background:#fde8e8;border:2px solid #ef5350;border-radius:8px;padding:1rem 1.25rem;margin:1rem 0}
.quick-win{background:#e8f5e9;border:2px solid #66bb6a;border-radius:8px;padding:1rem 1.25rem;margin:1rem 0}
@media print{body{background:#fff;padding:0}main{box-shadow:none;padding:1rem}}
"""

def ecs_escape(text):
    return html.escape(text, quote=True)


def ecs_inline(text):
    """Bold, code, links and RAG badges; the caller has escaped the text."""
    hrefs = []
    text = hold_links(text, hrefs)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = text.replace('\U0001f534', '<span class="red">RED</span>')
    text = text.replace('\U0001f7e1', '<span class="amber">AMBER</span>')
    text = text.replace('\U0001f7e2', '<span class="green">GREEN</span>')
    text = text.replace('\u2b1c', '<span class="unknown">UNKNOWN</span>')
    return restore_links(text, hrefs)


def ecs_table(lines):
    """Convert markdown table lines to HTML table."""
    if len(lines) < 2:
        return ""
    headers = [c.strip() for c in lines[0].strip('|').split('|')]
    rows = []
    for line in lines[2:]:  # skip separator
        cells = [c.strip() for c in line.strip('|').split('|')]
        rows.append(cells)

    out = '<table>\n<thead><tr>'
    for h in headers:
        out += f'<th>{ecs_inline(ecs_escape(h))}</th>'
    out += '</tr></thead>\n<tbody>\n'
    for row in rows:
        out += '<tr>'
        for cell in row:
            out += f'<td>{ecs_inline(ecs_escape(cell))}</td>'
        out += '</tr>\n'
    out += '</tbody></table>\n'
    return out


def ecs_convert(md_text):
    """Convert markdown to HTML."""
    lines = md_text.split('\n')
    out = []
    i = 0
    in_list = None  # 'ul' or 'ol'

    def close_list():
        nonlocal in_list
        if in_list:
            out.append(f'</{in_list}>')
            in_list = None

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Fenced code block
        if stripped.startswith('```'):
            # Look ahead for a closing fence. If there is none, the fence is
            # unclosed and we must NOT swallow the rest of the document as code:
            # treat this line as literal text and keep parsing normally.
            has_closing = any(
                lines[j].strip().startswith('```') for j in range(i + 1, len(lines))
            )
            if not has_closing:
                close_list()
                out.append(f'<p>{ecs_inline(ecs_escape(stripped))}</p>')
                i += 1
                continue
            close_list()
            lang_match = re.match(r'^```(\w+)?', stripped)
            lang = lang_match.group(1) if lang_match and lang_match.group(1) else None
            lang_attr = f' class="language-{lang}"' if lang else ''
            i += 1
            code_lines = []
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(ecs_escape(lines[i]))
                i += 1
            i += 1  # skip closing ```
            out.append(f'<pre><code{lang_attr}>{chr(10).join(code_lines)}</code></pre>')
            continue

        # Blank line
        if not stripped:
            close_list()
            i += 1
            continue

        # Table: collect consecutive | lines
        if stripped.startswith('|') and '|' in stripped[1:]:
            close_list()
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i])
                i += 1
            out.append(ecs_table(table_lines))
            continue

        # Headings
        m = re.match(r'^(#{1,4})\s+(.+)$', stripped)
        if m:
            close_list()
            level = len(m.group(1))
            text = ecs_inline(ecs_escape(m.group(2)))
            out.append(f'<h{level}>{text}</h{level}>')
            i += 1
            continue

        # Horizontal rule
        if re.match(r'^-{3,}$', stripped) or re.match(r'^\*{3,}$', stripped):
            close_list()
            out.append('<hr>')
            i += 1
            continue

        # Ordered list
        m = re.match(r'^(\d+)\.\s+(.+)$', stripped)
        if m:
            if in_list != 'ol':
                close_list()
                in_list = 'ol'
                out.append('<ol>')
            out.append(f'<li>{ecs_inline(ecs_escape(m.group(2)))}</li>')
            i += 1
            continue

        # Unordered list
        if stripped.startswith('- ') or stripped.startswith('* '):
            if in_list != 'ul':
                close_list()
                in_list = 'ul'
                out.append('<ul>')
            out.append(f'<li>{ecs_inline(ecs_escape(stripped[2:]))}</li>')
            i += 1
            continue

        # Blockquote
        if stripped.startswith('> '):
            close_list()
            out.append(f'<blockquote>{ecs_inline(ecs_escape(stripped[2:]))}</blockquote>')
            i += 1
            continue

        # Paragraph
        close_list()
        out.append(f'<p>{ecs_inline(ecs_escape(stripped))}</p>')
        i += 1

    close_list()
    return '\n'.join(out)

def ecs_page(md_text, stem):
    m = re.search(r'^#\s+(.+)$', md_text, re.MULTILINE)
    title = m.group(1) if m else stem
    body = ecs_convert(md_text)
    return {".html": f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{ecs_escape(title)}</title>
<style>{ECS_CSS}</style></head><body><main>
{body}
</main></body></html>"""}


# ---------------------------------------------------------------- eks-cost-intelligence

COST_CSS = """
:root {
    --color-bg: #ffffff;
    --color-text: #16191f;
    --color-heading: #0972d3;
    --color-border: #e9ebed;
    --color-code-bg: #f2f3f3;
    --color-table-header: #f2f3f3;
    --color-link: #0972d3;
    --color-blockquote-border: #0972d3;
    --color-blockquote-bg: #f2f8fd;

    /* Score classification colors */
    --color-optimized: #037f0c;
    --color-optimized-bg: #f2fcf3;
    --color-good: #0972d3;
    --color-good-bg: #f2f8fd;
    --color-fair: #8d6605;
    --color-fair-bg: #fffce9;
    --color-needs-work: #d45b07;
    --color-needs-work-bg: #fff3e6;
    --color-critical: #d91515;
    --color-critical-bg: #fff7f7;

    /* Severity colors */
    --color-sev-critical: #d91515;
    --color-sev-critical-bg: #fff7f7;
    --color-sev-high: #d91515;
    --color-sev-high-bg: #fff7f7;
    --color-sev-medium: #8d6605;
    --color-sev-medium-bg: #fffce9;
    --color-sev-low: #037f0c;
    --color-sev-low-bg: #f2fcf3;

    /* Savings colors */
    --color-savings: #037f0c;
    --color-savings-bg: #f2fcf3;
    --color-cost: #d91515;

    /* Dimension status */
    --color-assessed: #037f0c;
    --color-assessed-bg: #f2fcf3;
    --color-skipped: #687078;
    --color-skipped-bg: #f2f3f3;
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: "Amazon Ember", "Helvetica Neue", Roboto, Arial, sans-serif;
    font-size: 14px;
    line-height: 1.6;
    color: var(--color-text);
    background: var(--color-bg);
    max-width: 1100px;
    margin: 0 auto;
    padding: 40px 24px;
}

h1 {
    font-size: 28px;
    font-weight: 700;
    color: var(--color-heading);
    margin: 32px 0 16px 0;
    padding-bottom: 8px;
    border-bottom: 2px solid var(--color-heading);
}

h2 {
    font-size: 22px;
    font-weight: 700;
    color: var(--color-heading);
    margin: 28px 0 12px 0;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--color-border);
}

h3 {
    font-size: 17px;
    font-weight: 700;
    color: var(--color-text);
    margin: 20px 0 8px 0;
}

h4 {
    font-size: 15px;
    font-weight: 700;
    margin: 16px 0 6px 0;
}

p {
    margin: 8px 0;
}

a {
    color: var(--color-link);
    text-decoration: none;
}

a:hover {
    text-decoration: underline;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin: 12px 0;
    font-size: 13px;
}

th {
    background: var(--color-table-header);
    font-weight: 700;
    text-align: left;
    padding: 10px 12px;
    border: 1px solid var(--color-border);
}

td {
    padding: 8px 12px;
    border: 1px solid var(--color-border);
    vertical-align: top;
}

tr:nth-child(even) {
    background: #fafafa;
}

code {
    font-family: "Monaco", "Menlo", "Consolas", monospace;
    font-size: 12px;
    background: var(--color-code-bg);
    padding: 2px 6px;
    border-radius: 3px;
}

pre {
    background: #1b2028;
    color: #d4d4d4;
    padding: 16px;
    border-radius: 6px;
    overflow-x: auto;
    margin: 12px 0;
    font-size: 12px;
    line-height: 1.5;
}

pre code {
    background: none;
    padding: 0;
    color: inherit;
}

blockquote {
    border-left: 4px solid var(--color-blockquote-border);
    background: var(--color-blockquote-bg);
    padding: 12px 16px;
    margin: 12px 0;
    border-radius: 0 4px 4px 0;
}

ul, ol {
    margin: 8px 0 8px 24px;
}

li {
    margin: 4px 0;
}

hr {
    border: none;
    border-top: 1px solid var(--color-border);
    margin: 24px 0;
}

/* Score classification styling */
.score-optimized {
    color: var(--color-optimized);
    font-weight: 700;
}

.score-good {
    color: var(--color-good);
    font-weight: 700;
}

.score-fair {
    color: var(--color-fair);
    font-weight: 700;
}

.score-needs-work {
    color: var(--color-needs-work);
    font-weight: 700;
}

.score-critical {
    color: var(--color-critical);
    font-weight: 700;
}

/* Score badge (large) */
.score-badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 4px;
    font-size: 14px;
    font-weight: 700;
    text-transform: uppercase;
}

.score-badge-optimized { background: var(--color-optimized-bg); color: var(--color-optimized); }
.score-badge-good { background: var(--color-good-bg); color: var(--color-good); }
.score-badge-fair { background: var(--color-fair-bg); color: var(--color-fair); }
.score-badge-needs-work { background: var(--color-needs-work-bg); color: var(--color-needs-work); }
.score-badge-critical { background: var(--color-critical-bg); color: var(--color-critical); }

/* Severity badges */
.badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 3px;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
}

.badge-critical { background: var(--color-sev-critical-bg); color: var(--color-sev-critical); }
.badge-high { background: var(--color-sev-high-bg); color: var(--color-sev-high); }
.badge-medium { background: var(--color-sev-medium-bg); color: var(--color-sev-medium); }
.badge-low { background: var(--color-sev-low-bg); color: var(--color-sev-low); }

/* Dimension status badges */
.dimension-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 3px;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
}

.dimension-assessed { background: var(--color-assessed-bg); color: var(--color-assessed); }
.dimension-skipped { background: var(--color-skipped-bg); color: var(--color-skipped); }

/* Dollar amount styling */
.dollar-amount {
    font-weight: 700;
    font-family: "Monaco", "Menlo", "Consolas", monospace;
    font-size: 13px;
}

.dollar-savings { color: var(--color-savings); }
.dollar-cost { color: var(--color-cost); }
.dollar-waste { color: var(--color-needs-work); }

/* Effort badges */
.effort-low { color: var(--color-optimized); font-weight: 600; }
.effort-medium { color: var(--color-fair); font-weight: 600; }
.effort-high { color: var(--color-sev-high); font-weight: 600; }

/* Status icons in tables */
td:first-child {
    white-space: nowrap;
}

.timestamp {
    color: #687078;
    font-size: 12px;
    margin-top: -8px;
}

/* Print styles */
@media print {
    body {
        max-width: 100%;
        padding: 20px;
        font-size: 11px;
    }
    pre {
        white-space: pre-wrap;
        word-wrap: break-word;
        background: #f5f5f5;
        color: #333;
    }
    h1, h2, h3 { page-break-after: avoid; }
    table { page-break-inside: avoid; }
    .score-badge, .badge, .dimension-badge {
        border: 1px solid currentColor;
    }
    a { color: var(--color-text); }
    a::after { content: " (" attr(href) ")"; font-size: 10px; color: #687078; }
}
"""

def cost_inline(text):
    """Inline formatting with the cost report's patterns; escapes the text first."""
    text = html.escape(text)
    hrefs = []
    text = hold_links(text, hrefs)
    # Code spans
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

    # Bold
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    # Italic
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
    # Strikethrough
    text = re.sub(r"~~([^~]+)~~", r"<del>\1</del>", text)

    # Score classification keywords
    text = re.sub(
        r"\bOPTIMIZED\b",
        r'<span class="score-optimized">OPTIMIZED</span>',
        text,
    )
    text = re.sub(
        r"\bGOOD\b",
        r'<span class="score-good">GOOD</span>',
        text,
    )
    text = re.sub(
        r"\bFAIR\b",
        r'<span class="score-fair">FAIR</span>',
        text,
    )
    text = re.sub(
        r"\bNEEDS_WORK\b",
        r'<span class="score-needs-work">NEEDS_WORK</span>',
        text,
    )
    text = re.sub(
        r"\bCRITICAL\b(?!\s*\<\/)",
        r'<span class="score-critical">CRITICAL</span>',
        text,
    )

    # Severity badges in table cells
    text = re.sub(
        r"\bCRITICAL\b",
        r'<span class="badge badge-critical">CRITICAL</span>',
        text,
    )
    text = re.sub(
        r"\bHIGH\b",
        r'<span class="badge badge-high">HIGH</span>',
        text,
    )
    text = re.sub(
        r"\bMEDIUM\b",
        r'<span class="badge badge-medium">MEDIUM</span>',
        text,
    )
    text = re.sub(
        r"\bLOW\b",
        r'<span class="badge badge-low">LOW</span>',
        text,
    )

    # Dimension status badges
    text = re.sub(
        r"\bASSESSED\b",
        r'<span class="dimension-badge dimension-assessed">ASSESSED</span>',
        text,
    )
    text = re.sub(
        r"\bSKIPPED\b",
        r'<span class="dimension-badge dimension-skipped">SKIPPED</span>',
        text,
    )

    # Dollar amounts: savings (positive context)
    text = re.sub(
        r"\$([0-9,]+(?:\.[0-9]{2})?)/month",
        r'<span class="dollar-amount dollar-savings">$\1/month</span>',
        text,
    )
    text = re.sub(
        r"\$([0-9,]+(?:\.[0-9]{2})?)/year",
        r'<span class="dollar-amount dollar-savings">$\1/year</span>',
        text,
    )
    # Generic dollar amounts (not already wrapped)
    text = re.sub(
        r"(?<!\")\$([0-9,]+(?:\.[0-9]{2})?)(?!/)(?!</span>)",
        r'<span class="dollar-amount">$\1</span>',
        text,
    )

    # Effort levels
    text = re.sub(
        r"\bLow\b(?=\s*\||\s*$)",
        r'<span class="effort-low">Low</span>',
        text,
    )
    text = re.sub(
        r"\bMedium\b(?=\s*\||\s*$)",
        r'<span class="effort-medium">Medium</span>',
        text,
    )
    text = re.sub(
        r"\bHigh\b(?=\s*\||\s*$)",
        r'<span class="effort-high">High</span>',
        text,
    )
    return restore_links(text, hrefs)


def cost_convert(md_content: str) -> str:
    """Convert markdown to HTML with cost-intelligence-specific formatting."""
    lines = md_content.split("\n")
    html_parts = []
    in_code_block = False
    code_lang = ""
    code_lines = []
    in_table = False
    table_lines = []
    in_list = False
    list_type = None
    list_items = []

    def flush_table():
        nonlocal in_table, table_lines
        if not table_lines:
            return ""
        rows = []
        for i, line in enumerate(table_lines):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if i == 1 and all(set(c.strip()) <= set("-: ") for c in cells):
                continue  # separator row
            tag = "th" if i == 0 else "td"
            row_cells = "".join(f"<{tag}>{cost_inline(c)}</{tag}>" for c in cells)
            rows.append(f"<tr>{row_cells}</tr>")
        in_table = False
        table_lines = []
        return f'<table>{"".join(rows)}</table>'

    def flush_list():
        nonlocal in_list, list_type, list_items
        if not list_items:
            return ""
        tag = "ol" if list_type == "ol" else "ul"
        items = "".join(f"<li>{cost_inline(item)}</li>" for item in list_items)
        in_list = False
        list_type = None
        list_items = []
        return f"<{tag}>{items}</{tag}>"

    for line in lines:
        # Code blocks
        if line.strip().startswith("```"):
            if in_code_block:
                escaped = html.escape("\n".join(code_lines))
                lang_attr = f' class="language-{code_lang}"' if code_lang else ""
                html_parts.append(f"<pre><code{lang_attr}>{escaped}</code></pre>")
                in_code_block = False
                code_lines = []
                code_lang = ""
            else:
                # Flush any open constructs
                if in_table:
                    html_parts.append(flush_table())
                if in_list:
                    html_parts.append(flush_list())
                in_code_block = True
                code_lang = line.strip().lstrip("`").strip()
            continue

        if in_code_block:
            code_lines.append(line)
            continue

        stripped = line.strip()

        # Blank line
        if not stripped:
            if in_table:
                html_parts.append(flush_table())
            if in_list:
                html_parts.append(flush_list())
            continue

        # Horizontal rule
        if stripped in ("---", "***", "___"):
            if in_table:
                html_parts.append(flush_table())
            if in_list:
                html_parts.append(flush_list())
            html_parts.append("<hr>")
            continue

        # Table
        if "|" in stripped and stripped.startswith("|"):
            if in_list:
                html_parts.append(flush_list())
            in_table = True
            table_lines.append(stripped)
            continue
        elif in_table:
            html_parts.append(flush_table())

        # Headings
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading_match:
            if in_list:
                html_parts.append(flush_list())
            level = len(heading_match.group(1))
            text = heading_match.group(2)
            html_parts.append(f"<h{level}>{cost_inline(text)}</h{level}>")
            continue

        # Blockquote
        if stripped.startswith(">"):
            if in_list:
                html_parts.append(flush_list())
            text = stripped.lstrip("> ")
            html_parts.append(
                f"<blockquote><p>{cost_inline(text)}</p></blockquote>"
            )
            continue

        # Unordered list
        list_match = re.match(r"^[-*+]\s+(.+)$", stripped)
        if list_match:
            if in_table:
                html_parts.append(flush_table())
            if in_list and list_type != "ul":
                html_parts.append(flush_list())
            in_list = True
            list_type = "ul"
            list_items.append(list_match.group(1))
            continue

        # Ordered list
        ol_match = re.match(r"^\d+\.\s+(.+)$", stripped)
        if ol_match:
            if in_table:
                html_parts.append(flush_table())
            if in_list and list_type != "ol":
                html_parts.append(flush_list())
            in_list = True
            list_type = "ol"
            list_items.append(ol_match.group(1))
            continue

        # Regular paragraph
        if in_list:
            html_parts.append(flush_list())
        html_parts.append(f"<p>{cost_inline(stripped)}</p>")

    # Flush remaining
    if in_code_block:
        escaped = html.escape("\n".join(code_lines))
        html_parts.append(f"<pre><code>{escaped}</code></pre>")
    if in_table:
        html_parts.append(flush_table())
    if in_list:
        html_parts.append(flush_list())

    return "\n".join(html_parts)

def cost_page(md_text, stem):
    title = "EKS Cost Intelligence Report"
    for line in md_text.split("\n"):
        if line.strip().startswith("# "):
            title = line.strip().lstrip("# ").strip()
            break
    return {".html": f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)}</title>
    <style>
{COST_CSS}
    </style>
</head>
<body>
{cost_convert(md_text)}
</body>
</html>"""}


# ---------------------------------------------------------------- eks-security

FOOTER = "The scripts that produced this report are read-only; they changed nothing."
VERDICT_LABEL = {"exposed": "Exposed", "not_exposed": "Not exposed", "unknown": "Unknown",
                 "aws_managed_patched": "AWS-patched (inferred from node age)",
                 "aws_managed_rotation_pending": "Exposed until replaced (AWS-managed)"}
VERDICT_ORDER = {"exposed": 0, "unknown": 1, "aws_managed_rotation_pending": 2,
                 "aws_managed_patched": 3, "not_exposed": 4}
SEV_ORDER = {"critical": 0, "high": 1, "important": 1, "medium": 2, "low": 3}
OVERALL = {"exposed": "Exposed: at least one component is inside an affected range.",
           "rotation_pending": "Rotation pending: AWS has patched the component, but some Auto Mode nodes created "
                               "before the fix still run the vulnerable build and are exposed now, until they are "
                               "replaced. See the nodes listed below.",
           "not_exposed": "Not exposed: every targeted component was read and is outside the affected ranges.",
           "unknown": "Unknown: nothing was found exposed, but at least one component or advisory could not be "
                      "decided. See Unknown"}
PATCHED = ("AWS-patched (inferred, not read): every Auto Mode node it was judged on was created at or after the fix "
           "time %s; the Auto Mode components' versions were not read. Auto Mode AMIs roll out to clusters and Regions in waves "
           "(https://docs.aws.amazon.com/whitepapers/latest/security-overview-amazon-eks-auto-mode/eks-auto-mode-data-plane.html, "
           "Node patching), so a node created after the fix time can still run an older AMI.")
OLD_AMI = ("Likely unpatched for %s (fix time %s): %s. These nodes were created after the fix time but run an older AMI "
           "(AMI built, below), inferred from dates only: the AMI was created before the fix time; its contents were not "
           "read. Replace these NodePools' nodes and run the review again. An AMI built after the fix time is not proof "
           "that it carries the fix.")
UNKNOWN_ACTION = {
    "denied": "Grant the read named in the preflight (see read-only-access.md) and re-run collect",
    "not_found": "Confirm whether the component is installed another way (Helm, manifest) and re-run with --namespaces",
    "tag_latest": "The image tag latest has no version; find the digest's version in the registry or pin the image",
    "digest_only": "The image is pinned by digest only; map the digest to its release in the registry",
    "unparsed": "The version string did not parse; read it by hand and record it",
    "no_fix_date": "Find the time AWS released the fix for Auto Mode, record it as fixed_at with its source line, "
                   "and run match again (take the fix date from the AWS security bulletin for the issue)",
    "no_version_range": "Compare the installed version with the advisory by hand",
    "bad_range": "Correct the record's range, check it with advisory_check.py and run match again",
    "no_nodes_read": "No Auto Mode node was read; check the nodes read in the preflight (read-only-access.md) and "
                     "that the NodePools have nodes, then re-run collect",
    "eks_build": "Compare the build with the advisory by hand",
    "minor_only": "The installed version names no patch release; find the patch release (for the control plane, "
                  "from its platform version) and compare by hand"}
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+=-]{0,199}$")
_MD_SPECIAL = re.compile(r"([\\`*_\[\]#|~])")


def s(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (list, tuple)):
        return ", ".join(s(x) for x in v)
    if isinstance(v, dict):
        return json.dumps(v, sort_keys=True)
    return " ".join(str(v).split())


def tok(v, placeholder):
    """A value safe to place in a proposed shell command, else the placeholder."""
    v = s(v)
    return v if _TOKEN.match(v) else placeholder


# ---------------------------------------------------------------- blocks

def md_text(v):
    return html.escape(_MD_SPECIAL.sub(r"\\\1", s(v)), quote=False)


def to_md(blocks):
    out = []
    for b in blocks:
        k = b[0]
        if k == "h1":
            out += ["# " + md_text(b[1]), ""]
        elif k == "h2":
            out += ["## " + md_text(b[1]), ""]
        elif k == "p":
            out += [md_text(b[1]), ""]
        elif k == "ul":
            out += ["- " + md_text(x) for x in b[1]] + [""]
        elif k == "table":
            out.append("| " + " | ".join(md_text(h) for h in b[1]) + " |")
            out.append("|" + "---|" * len(b[1]))
            out += ["| " + " | ".join(md_text(c) for c in row) + " |" for row in b[2]]
            out.append("")
        elif k == "code":
            body = "\n".join(line.replace("`", "'") for line in b[1])
            out += ["```bash", body, "```", ""]
    return "\n".join(out).rstrip() + "\n"


SEC_CSS = ("body{font-family:system-ui,sans-serif;max-width:72rem;margin:2rem auto;padding:0 1rem;color:#1b1b1b}"
       "table{border-collapse:collapse;margin:0.5rem 0 1rem}th,td{border:1px solid #ccc;padding:0.3rem 0.5rem;"
       "text-align:left;vertical-align:top}th{background:#f2f2f2}pre{background:#f6f6f6;padding:0.75rem;"
       "overflow-x:auto}footer{margin-top:2rem;border-top:1px solid #ccc;padding-top:0.5rem}")


def to_html(blocks, title):
    e = lambda v: html.escape(s(v), quote=True)  # noqa: E731
    out = ["<!DOCTYPE html>", "<html lang=\"en\"><head><meta charset=\"utf-8\">",
           "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">",
           "<title>" + e(title) + "</title><style>" + SEC_CSS + "</style></head><body>"]
    for b in blocks:
        k = b[0]
        if k in ("h1", "h2", "p"):
            out.append("<%s>%s</%s>" % (k, e(b[1]), k))
        elif k == "ul":
            out.append("<ul>" + "".join("<li>" + e(x) + "</li>" for x in b[1]) + "</ul>")
        elif k == "table":
            out.append("<table><thead><tr>" + "".join("<th>" + e(h) + "</th>" for h in b[1]) + "</tr></thead><tbody>")
            out += ["<tr>" + "".join("<td>" + e(c) + "</td>" for c in row) + "</tr>" for row in b[2]]
            out.append("</tbody></table>")
        elif k == "code":
            out.append("<pre><code>" + "\n".join(html.escape(line, quote=True) for line in b[1]) + "</code></pre>")
        elif k == "footer":
            out.append("<footer><p>" + e(b[1]) + "</p></footer>")
    out.append("</body></html>")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- findings

def pct(x):
    try:
        return "%d%%" % round(float(x) * 100)
    except (TypeError, ValueError):
        return "unknown"


def proposed_actions(f, inv, cluster, region):
    """Lines of commands and notes for one finding, for the team to review. Never run."""
    comps = {c.get("id"): c for c in inv.get("components") or [] if isinstance(c, dict)}
    comp = comps.get(f.get("component")) or {}
    kver = tok((inv.get("control_plane") or {}).get("version"), "<KUBERNETES_VERSION>")
    c, r = tok(cluster, "<CLUSTER>"), tok(region, "<REGION>")
    fixed = s(f.get("fixed")) or "the fixed version"
    kind = comp.get("kind")
    addon = comp.get("addon")
    if kind == "container-image" and not addon and comp.get("namespace") == "kube-system" \
            and comp.get("workload") == "daemonset/aws-node":
        addon = "vpc-cni"  # the aws-node DaemonSet belongs to the Amazon VPC CNI
    if kind == "eks-addon" or (addon and ("addon:" + addon) in comps and comps["addon:" + addon].get("kind") == "eks-addon"):
        name = tok(comp.get("name") if kind == "eks-addon" else addon, "<ADDON_NAME>")
        target = ("a version at or above %s" % fixed) if kind == "eks-addon" else \
            ("a release of the %s add-on that ships %s %s or later" % (s(addon), s(comp.get("name")) or "this image",
                                                                       fixed))
        return ("Update the EKS add-on to %s. List the versions first and test in "
                "non-prod. PRESERVE keeps your own configuration values." % target,
                ["aws eks describe-addon-versions --addon-name %s --kubernetes-version %s --region %s "
                 "--query 'addons[].addonVersions[].addonVersion'" % (name, kver, r),
                 "aws eks update-addon --cluster-name %s --addon-name %s --addon-version <VERSION_AT_OR_ABOVE_FIX> "
                 "--resolve-conflicts PRESERVE --region %s" % (c, name, r)])
    if kind == "container-image":
        ns, wl = tok(comp.get("namespace"), "<NAMESPACE>"), tok(comp.get("workload"), "<WORKLOAD>")
        what = ("a self-managed install of %s" % addon) if addon else s(comp.get("name"))
        return ("This is %s. Move the image to %s or later the way it was installed (Helm chart, manifest or "
                "GitOps), or rebuild your own image on a patched base. Pin the new image by digest and roll it out "
                "through your normal pipeline. Confirm the running image first:" % (what, fixed),
                ["kubectl -n %s get %s -o jsonpath='{.spec.template.spec.containers[*].image}'" % (ns, wl)])
    if kind == "node-os":
        groups = comp.get("where") or []
        g = tok(groups[0] if groups else None, "<NODEGROUP>")
        if g == "self-managed" or comp.get("managed_by") != "customer":
            return ("Replace these nodes with an AMI that carries the fix (launch template or Auto Scaling group "
                    "of the self-managed nodes), one batch at a time.", [])
        return ("Move the managed node group to an AMI release that carries the fix. Without --release-version "
                "the update uses the latest AMI release for the node group's Kubernetes version; check that "
                "release includes the fix and test in non-prod first.",
                ["aws eks describe-nodegroup --cluster-name %s --nodegroup-name %s --region %s "
                 "--query 'nodegroup.releaseVersion'" % (c, g, r),
                 "aws eks update-nodegroup-version --cluster-name %s --nodegroup-name %s --region %s" % (c, g, r)])
    if kind == "control-plane":
        return ("AWS patches the EKS control plane. Compare the platform version with the advisory; a Kubernetes "
                "version upgrade goes through the eks-upgrade-check skill.",
                ["aws eks describe-cluster --name %s --region %s --query 'cluster.[version,platformVersion]'" % (c, r)])
    return ("Review this component against the advisory and plan the fix the way it was installed.", [])


def findings_blocks(fd, inv):
    cluster = fd.get("cluster") or inv.get("cluster")
    region = inv.get("region")
    cov = fd.get("coverage") or {}
    overall = fd.get("overall")
    blocks = [("h1", "EKS security advisory review: %s" % s(cluster)),
              ("ul", ["Cluster: %s (Region %s)" % (s(cluster), s(region) or "unknown"),
                      "Inventory collected at: %s" % (s(inv.get("collected_at")) or "unknown"),
                      "Findings generated at: %s" % (s(fd.get("generated_at")) or "unknown"),
                      "Coverage: %s of %s in-scope components read (%s, gate %s)"
                      % (s(cov.get("read")), s(cov.get("in_scope")), pct(cov.get("ratio")), pct(cov.get("gate")))])]
    if overall == "incomplete" or cov.get("complete") is not True:
        blocks.append(("p", "Overall verdict: Incomplete. Fewer than %s of the components these advisories target "
                            "could be read, so this report gives no overall verdict. Fix the reads listed under "
                            "Unknown and run again." % pct(cov.get("gate"))))
    else:
        patched = sorted({"%s (%s)" % (s(f.get("fixed_at")), s(f.get("source_url"))) for f in fd.get("findings") or []
                          if f.get("verdict") == "aws_managed_patched"})
        printed = overall != "not_exposed" or not patched
        if printed:
            line = OVERALL.get(overall, "Unknown.")
            if overall == "unknown":
                line += " and Needs manual review." if fd.get("review") else "."
            blocks.append(("p", "Overall verdict: " + line))
        if patched:
            blocks.append(("p", ("Auto Mode components: " if printed else "Overall verdict: ")
                           + PATCHED % "; ".join(patched)))
            # the nodes the patched verdicts were judged on: a node-os finding its own group, any other every group;
            # a NodePool any advisory holds as pending rotation, on any of its node groups, is never listed here
            auto = {c.get("id"): c for c in inv.get("components") or [] if isinstance(c, dict)
                    and c.get("kind") == "node-os" and c.get("managed_by") == "aws-auto-mode"}
            pc = {f.get("component") for f in fd.get("findings") or [] if f.get("verdict") == "aws_managed_patched"}
            pf = [f for f in fd.get("findings") or [] if f.get("verdict") == "aws_managed_rotation_pending"]
            pend = {f.get("component") for f in pf}
            pend_nodes = {n for f in pf for n in f.get("nodes_pending") or []}
            pend_pools = {s(c.get("where")) for i, c in auto.items() if i in pend or pend_nodes & set(c.get("nodes") or [])}
            rows = sorted((c for i, c in auto.items() if s(c.get("where")) not in pend_pools
                           and (i in pc or not pc <= set(auto))),
                          key=lambda c: (s(c.get("where")), s(c.get("os_image"))))
            pools = {c.get("id"): s(c.get("where")) for c in rows}
            old = {}
            for f in fd.get("findings") or []:
                if f.get("verdict") == "aws_managed_patched":
                    old.setdefault((s(f.get("advisory")), s(f.get("fixed_at"))), set()).update(
                        pools[i] for i in f.get("ami_before_fix") or [] if i in pools)
            for (adv, at), names in sorted(old.items()):
                if names:
                    blocks.append(("p", OLD_AMI % (adv, at, ", ".join(sorted(names)))))
            if rows:
                blocks.append(("table", ["NodePool", "OS image", "AMI", "AMI built", "Nodes", "Oldest node created"],
                               [[c.get("where"), c.get("os_image") or "not read", c.get("ami") or "not read",
                                 c.get("ami_created") or "not read",
                                 len(c.get("nodes") or []), c.get("oldest_node_created")] for c in rows]))
    src = fd.get("sources") or []
    blocks += [("h2", "Sources"),
               ("table", ["Advisory", "Title", "Origin", "Read at", "Source URL"],
                [[x.get("id"), x.get("title"), "live" if x.get("origin") == "live" else "from file, not live",
                  x.get("read_at"), x.get("source_url")] for x in src])]
    fs = sorted(fd.get("findings") or [], key=lambda f: (s(f.get("priority")) or "P9",
                                                         VERDICT_ORDER.get(f.get("verdict"), 9)))
    blocks += [("h2", "Findings"),
               ("table", ["Priority", "Verdict", "Advisory", "Component", "Installed", "Fixed", "Severity",
                          "Workaround", "Where"],
                [["" if f.get("verdict") == "not_exposed" else f.get("priority"),
                  VERDICT_LABEL.get(f.get("verdict"), s(f.get("verdict"))), f.get("advisory"),
                  f.get("component"), f.get("installed"), f.get("fixed"), f.get("severity"),
                  "not stated" if f.get("workaround") is None else f.get("workaround"), f.get("where")]
                 for f in fs])]
    ne = [f for f in fs if f.get("verdict") == "not_exposed"]
    if ne:
        blocks += [("h2", "Not exposed"),
                   ("ul", ["Not exposed: %s %s is outside every affected range of %s (fixed in: %s) (%s, read %s), "
                           "compared against the inventory collected %s" % (s(f.get("component")), s(f.get("installed")),
                                                           s(f.get("advisory")),
                                                           s(f.get("fixed")) or "none stated", s(f.get("source_url")),
                                                           s(f.get("read_at")),
                                                           s(inv.get("collected_at")) or "unknown") for f in ne])]
    unk = [f for f in fs if f.get("verdict") == "unknown"]
    if unk:
        blocks += [("h2", "Unknown"),
                   ("ul", ["Unknown: %s (%s) could not be compared (%s). This is not a clean result. To resolve: %s." % (
                       s(f.get("component")), s(f.get("advisory")), s(f.get("reason")),
                       UNKNOWN_ACTION.get(s(f.get("reason")).split(":", 1)[0],
                                          "Read the advisory and the installed version by hand"))
                           for f in unk])]
    rv = fd.get("review") or []
    if rv:
        blocks += [("h2", "Needs manual review"),
                   ("ul", ["%s%s: %s. Source %s, read at %s" % (
                       s(x.get("advisory")), (" package " + s(x.get("package"))) if x.get("package") else "",
                       s(x.get("reason")), s(x.get("source_url")), s(x.get("read_at"))) for x in rv])]
    pend = [f for f in fs if f.get("verdict") == "aws_managed_rotation_pending"]
    if pend:
        node_created = {}
        for c in inv.get("components") or []:
            if isinstance(c, dict) and c.get("kind") == "node-os":
                for n, t in (c.get("node_created") or {}).items():
                    node_created[n] = (t, c.get("where"))
        rows = []
        for f in pend:
            for n in f.get("nodes_pending") or []:
                t, where = node_created.get(n, (None, None))
                rows.append([f.get("advisory"), f.get("component"), n, t, where])
        rows.sort(key=lambda r: s(r[3]))
        blocks += [("h2", "Auto Mode nodes pending rotation"),
                   ("p", "AWS manages these components on Auto Mode nodes. Nodes created before the fix date keep "
                         "the vulnerable build until they are replaced. Your lever is the NodePool's expireAfter or a "
                         "planned rotation of the nodes below in a maintenance window, not a patch. Read the "
                         "NodePool settings first:"),
                   ("code", ["kubectl get nodepools -o custom-columns=NAME:.metadata.name,"
                             "EXPIRE_AFTER:.spec.template.spec.expireAfter"]),
                   ("table", ["Advisory", "Component", "Node", "Created", "NodePool"], rows)]
    act = [f for f in fs if f.get("verdict") == "exposed"]
    if act:
        blocks += [("h2", "Proposed actions (for the team to review; nothing here was run)")]
        shown = set()
        for f in act:
            note, cmds = proposed_actions(f, inv, cluster, region)
            dup = bool(cmds) and tuple(cmds) in shown
            blocks.append(("p", "%s on %s (%s, %s): %s%s" % (s(f.get("advisory")), s(f.get("component")),
                                                             s(f.get("priority")), s(f.get("severity")), note,
                                                             " (commands as above)" if dup else "")))
            if cmds and not dup:
                shown.add(tuple(cmds))
                blocks.append(("code", cmds))
    return blocks, bool(cov.get("complete"))


# ---------------------------------------------------------------- posture

def posture_blocks(pd, standalone):
    cov = pd.get("coverage") or {}
    blocks = []
    if standalone:
        blocks.append(("h1", "EKS security posture check: %s" % s(pd.get("cluster"))))
    blocks += [("h2", "Posture check: would this cluster contain a compromised pod?"),
               ("ul", ["Generated at: %s" % (s(pd.get("generated_at")) or "unknown"),
                       "Coverage: %s of %s measured checks answered (%s, gate %s); %d governance checks not scored "
                       "(confirm with the team)" % (
                           s(cov.get("checks_answered")), s(cov.get("checks_total")), pct(cov.get("ratio")),
                           pct(cov.get("gate")),
                           sum(1 for c in pd.get("checks") or [] if isinstance(c, dict) and c.get("source_file") is None)),
                       "Score: %s" % (("%s of 100" % s(pd.get("score")))
                                      if cov.get("complete") and pd.get("score") is not None
                                      else "incomplete, no score")])]
    blocks.append(("table", ["Containment layer", "Verdict"],
                   [[x.get("layer"), x.get("verdict")] for x in pd.get("layers") or [] if isinstance(x, dict)]))
    checks = [c for c in pd.get("checks") or [] if isinstance(c, dict)]
    key = lambda c: (SEV_ORDER.get(s(c.get("severity")).lower(), 9), 0 if c.get("result") == "fail" else 1,  # noqa: E731
                     s(c.get("id")))
    bad = sorted([c for c in checks if c.get("result") in ("fail", "unknown")], key=key)
    bad += sorted([c for c in checks if c.get("result") == "pass" and "; failing: " in s(c.get("evidence"))], key=key)
    if bad:
        blocks += [("h2", "Failed, unknown and passed-with-exceptions checks"),
                   ("table", ["Result", "Severity", "Check", "Evidence", "Recommendation"],
                    [["pass (exceptions)" if c.get("result") == "pass" else c.get("result"), c.get("severity"),
                      "%s %s" % (s(c.get("id")), s(c.get("title"))),
                      c.get("evidence"), c.get("recommendation")] for c in bad])]
    npass = sum(1 for c in checks if c.get("result") == "pass")
    nna = sum(1 for c in checks if c.get("result") == "na")
    blocks.append(("p", "Passed checks: %d. Not applicable: %d." % (npass, nna)))
    return blocks, bool(cov.get("complete"))

def security_pages(docs):
    """docs: {"findings", "inventory", "posture"} -> ({suffix: text}, complete)."""
    if "inventory" in docs and "findings" not in docs:
        raise ReportError("an inventory input needs a findings input")
    blocks, complete = [], True
    title = "EKS security report"
    if "findings" in docs:
        fd, inv = docs["findings"], docs.get("inventory", {})
        b, ok = findings_blocks(fd, inv)
        blocks += b
        complete = complete and ok
        title = "EKS security advisory review: %s" % s(fd.get("cluster"))
    if "posture" in docs:
        pd = docs["posture"]
        b, ok = posture_blocks(pd, standalone="findings" not in docs)
        blocks += b
        complete = complete and ok
        if "findings" not in docs:
            title = "EKS security posture check: %s" % s(pd.get("cluster"))
    blocks.append(("footer", FOOTER))
    md_blocks = [b if b[0] != "footer" else ("p", b[1]) for b in blocks]
    return {".md": to_md(md_blocks), ".html": to_html(blocks, title)}, complete


# ---------------------------------------------------------------- command line

SECURITY_KINDS = {"eks-security/findings@": "findings", "eks-security/inventory@": "inventory",
                  "eks-security/posture@": "posture"}
TEMPLATES = {"ecs-operation-review": (".html",), "eks-cost-intelligence": (".html",),
             "eks-security": (".md", ".html")}


def read_text(path):
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        raise ReportError("%s: not readable: %s" % (path, e.strerror or e))
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ReportError("%s: not UTF-8 text" % path)
    if not text.strip():
        raise ReportError("%s: empty input" % path)
    return text


def read_markdown(path):
    text = read_text(path).replace("\r\n", "\n").replace("\r", "\n")
    return clean(text)


def read_security(paths):
    docs = {}
    for path in paths:
        try:
            d = json.loads(read_text(path))
        except ValueError as e:
            raise ReportError("%s: not valid JSON: %s" % (path, e))
        schema = d.get("schema") if isinstance(d, dict) else None
        kind = next((k for p, k in SECURITY_KINDS.items() if isinstance(schema, str) and schema.startswith(p)), None)
        if kind is None:
            raise ReportError("%s: schema must start with one of %s" % (path, ", ".join(SECURITY_KINDS)))
        if kind in docs:
            raise ReportError("%s: a second %s input" % (path, kind))
        docs[kind] = clean_json(d)
    return docs


def same_file(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.realpath(a) == os.path.realpath(b)


def plan_outputs(template, inputs, outs):
    by_suffix = {}
    for out in outs:
        suffix = os.path.splitext(out)[1].lower()
        if suffix not in TEMPLATES[template]:
            raise ReportError("--out %s: %s writes %s only" % (out, template, " and ".join(TEMPLATES[template])))
        if suffix in by_suffix:
            raise ReportError("--out %s: a second %s output" % (out, suffix))
        for other in list(inputs) + list(by_suffix.values()):
            if same_file(out, other):
                raise ReportError("--out %s: names %s, an input or another output" % (out, other))
        by_suffix[suffix] = out
    return by_suffix


def write(path, text):
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as e:
        raise ReportError("--out %s: not writable: %s" % (path, e.strerror or e))
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        f.write(text)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ReportError(message)


def parser():
    p = _Parser(prog=PROG, description="Write a skill's report page from its report input.",
                epilog="The template list, the escaping rules and the exit codes are in this tool's docstring.")
    p.add_argument("template", choices=sorted(TEMPLATES))
    p.add_argument("inputs", nargs="+", metavar="input")
    p.add_argument("--out", action="append", required=True, metavar="FILE",
                   help="output file; its suffix (.html or .md) sets the format")
    return p


def run(argv):
    a = parser().parse_args(argv)
    outs = plan_outputs(a.template, a.inputs, a.out)
    complete = True
    if a.template == "eks-security":
        pages, complete = security_pages(read_security(a.inputs))
    else:
        if len(a.inputs) != 1:
            raise ReportError("%s takes one input file (got %d)" % (a.template, len(a.inputs)))
        path = a.inputs[0]
        page = ecs_page if a.template == "ecs-operation-review" else cost_page
        stem = os.path.splitext(os.path.basename(path))[0]
        pages = page(read_markdown(path), stem)
    written = []
    try:
        for suffix, out in outs.items():
            write(out, pages[suffix])
            written.append(out)
    except ReportError:
        for out in written:
            try:
                os.unlink(out)
            except OSError:
                pass
        raise
    return 0 if complete else 3


def main(argv=None):
    try:
        return run(sys.argv[1:] if argv is None else argv)
    except ReportError as e:
        sys.stderr.write("%s: %s\n" % (PROG, e))
        return 2
    except Exception as e:  # never a traceback to the user
        sys.stderr.write("%s: internal error: %s: %s\n" % (PROG, type(e).__name__, e))
        return 2


if __name__ == "__main__":
    sys.exit(main())
