#!/usr/bin/env python3
"""
EKS Operation Review — Markdown to HTML Converter

Converts assessment report markdown files to styled HTML.
No external dependencies required.

Usage:
  python3 report_to_html.py <input.md>                  # outputs <input>.html
  python3 report_to_html.py <input.md> -o <output.html> # custom output path
  python3 report_to_html.py *.md                        # batch convert
"""

import re
import sys
import html
import urllib.parse
from pathlib import Path

_ALLOWED_URL_SCHEMES = {'http', 'https', 'mailto'}

CSS = """
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
.internal-banner{background:#fff3e0;border:2px solid #ff9900;border-radius:8px;padding:.75rem 1.25rem;margin:1rem 0;font-weight:600;color:#e65100}
@media print{body{background:#fff;padding:0}main{box-shadow:none;padding:1rem}}
"""


def escape(text):
    return html.escape(text, quote=True)


def _safe_href(url):
    """Return the URL if its scheme is allowlisted, otherwise '#'.

    Relative links (no scheme) and fragments are treated as safe.
    Control characters are stripped because browsers historically ignored
    them inside schemes, allowing `java\tscript:` to still execute.
    """
    cleaned = ''.join(c for c in url.strip() if c >= ' ' and c != '\x7f')
    try:
        parsed = urllib.parse.urlparse(cleaned)
    except ValueError:
        return '#'
    scheme = parsed.scheme.lower()
    if scheme and scheme not in _ALLOWED_URL_SCHEMES:
        return '#'
    return cleaned


def _link_sub(match):
    text = match.group(1)
    url = _safe_href(match.group(2))
    return f'<a href="{url}">{text}</a>'


def inline_format(text):
    """Process inline markdown: bold, code, links, emoji badges.

    Input must already be HTML-escaped with quote=True by the caller.
    Link hrefs are validated against a scheme allowlist; because `"` and
    `&` in the URL are already escaped to `&quot;`/`&amp;`, cluster-derived
    strings cannot break out of the href attribute.
    """
    # Links: [text](url) — scheme-allowlisted, href-escaped
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', _link_sub, text)
    # Bold: **text**
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # Inline code: `text`
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    # RAG emoji badges
    text = text.replace('🔴', '<span class="red">RED</span>')
    text = text.replace('🟡', '<span class="amber">AMBER</span>')
    text = text.replace('🟢', '<span class="green">GREEN</span>')
    text = text.replace('⬜', '<span class="unknown">UNKNOWN</span>')
    return text


def parse_table(lines):
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
        out += f'<th>{inline_format(escape(h))}</th>'
    out += '</tr></thead>\n<tbody>\n'
    for row in rows:
        out += '<tr>'
        for cell in row:
            out += f'<td>{inline_format(escape(cell))}</td>'
        out += '</tr>\n'
    out += '</tbody></table>\n'
    return out


def convert(md_text):
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
            close_list()
            lang_match = re.match(r'^```(\w+)?', stripped)
            lang = lang_match.group(1) if lang_match and lang_match.group(1) else None
            lang_attr = f' class="language-{lang}"' if lang else ''
            i += 1
            code_lines = []
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(escape(lines[i]))
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
            out.append(parse_table(table_lines))
            continue

        # Headings
        m = re.match(r'^(#{1,4})\s+(.+)$', stripped)
        if m:
            close_list()
            level = len(m.group(1))
            text = inline_format(escape(m.group(2)))
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
            out.append(f'<li>{inline_format(escape(m.group(2)))}</li>')
            i += 1
            continue

        # Unordered list
        if stripped.startswith('- ') or stripped.startswith('* '):
            if in_list != 'ul':
                close_list()
                in_list = 'ul'
                out.append('<ul>')
            out.append(f'<li>{inline_format(escape(stripped[2:]))}</li>')
            i += 1
            continue

        # Blockquote
        if stripped.startswith('> '):
            close_list()
            out.append(f'<blockquote>{inline_format(escape(stripped[2:]))}</blockquote>')
            i += 1
            continue

        # Internal banner detection
        if '⚠️' in stripped and 'INTERNAL' in stripped.upper():
            close_list()
            out.append(f'<div class="internal-banner">{inline_format(escape(stripped))}</div>')
            i += 1
            continue

        # Paragraph
        close_list()
        out.append(f'<p>{inline_format(escape(stripped))}</p>')
        i += 1

    close_list()
    return '\n'.join(out)


def md_to_html(md_text, title="EKS Operation Review"):
    body = convert(md_text)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title>
<style>{CSS}</style></head><body><main>
{body}
</main></body></html>"""


def main():
    args = sys.argv[1:]
    if not args or args[0] in ('-h', '--help'):
        print(__doc__.strip())
        sys.exit(0)

    output_path = None
    files = []
    i = 0
    while i < len(args):
        if args[i] == '-o' and i + 1 < len(args):
            output_path = args[i + 1]
            i += 2
        else:
            files.append(args[i])
            i += 1

    if not files:
        print("Error: no input files specified", file=sys.stderr)
        sys.exit(1)

    for f in files:
        p = Path(f)
        if not p.exists():
            print(f"Error: {f} not found", file=sys.stderr)
            continue

        md = p.read_text(encoding='utf-8')

        # Extract title from first H1
        m = re.search(r'^#\s+(.+)$', md, re.MULTILINE)
        title = m.group(1) if m else p.stem

        result = md_to_html(md, title)

        if output_path and len(files) == 1:
            out = Path(output_path)
        else:
            out = p.with_suffix('.html')

        out.write_text(result, encoding='utf-8')
        print(f"✓ {p.name} → {out.name}")


if __name__ == '__main__':
    main()
