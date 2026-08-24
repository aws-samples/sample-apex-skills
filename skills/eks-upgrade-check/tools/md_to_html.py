#!/usr/bin/env python3
"""
Markdown to HTML converter for EKS Upgrade Assessment reports.

Usage:
    python3 tools/md_to_html.py <report>.md
    python3 tools/md_to_html.py <report>.md --output custom-name.html

Produces a self-contained HTML file with embedded CSS styling.
No external dependencies required — uses only Python stdlib.
"""

import re
import sys
import html
import os
from pathlib import Path


def parse_args():
    args = sys.argv[1:]
    output_file = None

    # Pull out "--output <file>" first so it can appear before or after the
    # positional input (sys.argv[1] is no longer assumed to be the input).
    if "--output" in args:
        idx = args.index("--output")
        if idx + 1 < len(args):
            output_file = args[idx + 1]
            del args[idx:idx + 2]
        else:
            print("Error: --output requires a filename")
            sys.exit(1)

    if not args:
        print("Usage: python3 md_to_html.py <input.md> [--output <output.html>]")
        sys.exit(1)

    input_file = args[0]

    if output_file is None:
        output_file = str(Path(input_file).with_suffix(".html"))

    return input_file, output_file


CSS = """
:root {
    --color-bg: #ffffff;
    --color-text: #16191f;
    --color-heading: #0972d3;
    --color-border: #e9ebed;
    --color-code-bg: #f2f3f3;
    --color-table-header: #f2f3f3;
    --color-green: #037f0c;
    --color-amber: #8d6605;
    --color-red: #d91515;
    --color-green-bg: #f2fcf3;
    --color-amber-bg: #fffce9;
    --color-red-bg: #fff7f7;
    --color-link: #0972d3;
    --color-blockquote-border: #0972d3;
    --color-blockquote-bg: #f2f8fd;
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

/* Score styling */
.score-ready { color: var(--color-green); font-weight: 700; }
.score-good { color: var(--color-green); font-weight: 700; }
.score-fair { color: var(--color-amber); font-weight: 700; }
.score-risky { color: var(--color-red); font-weight: 700; }
.score-not-ready { color: var(--color-red); font-weight: 700; }

/* Severity badges */
.badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 3px;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
}
.badge-high { background: var(--color-red-bg); color: var(--color-red); }
.badge-medium { background: var(--color-amber-bg); color: var(--color-amber); }
.badge-low { background: var(--color-green-bg); color: var(--color-green); }

/* Checkbox styling */
input[type="checkbox"] {
    margin-right: 6px;
}

/* Print styles */
@media print {
    body { max-width: 100%; padding: 20px; }
    pre { white-space: pre-wrap; word-wrap: break-word; }
    h1, h2, h3 { page-break-after: avoid; }
    table { page-break-inside: avoid; }
}

/* Status icons in tables */
td:first-child {
    white-space: nowrap;
}

.timestamp {
    color: #687078;
    font-size: 12px;
    margin-top: -8px;
}
"""


def _split_table_row(line: str) -> list:
    """Split a markdown table row into cells on UNESCAPED, non-code pipes.

    A ``|`` only ends a cell when it is neither backslash-escaped (``\\|``) nor
    inside a backtick code span (`` `kubectl get po|grep x` ``). ``\\|`` is
    unescaped to a literal ``|`` in the emitted cell. The bounding pipes that
    delimit the row produce leading/trailing empty cells, which are dropped.
    """
    cells = []
    cur = []
    in_code = False
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if ch == "\\" and i + 1 < n and line[i + 1] == "|":
            cur.append("|")  # honor escaped pipe as a literal
            i += 2
            continue
        if ch == "`":
            in_code = not in_code
            cur.append(ch)
            i += 1
            continue
        if ch == "|" and not in_code:
            cells.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(ch)
        i += 1
    cells.append("".join(cur))
    # Drop the empty cells created by the row's leading/trailing bounding pipes.
    if cells and cells[0].strip() == "":
        cells = cells[1:]
    if cells and cells[-1].strip() == "":
        cells = cells[:-1]
    return cells


def md_to_html(md_content: str) -> str:
    """Convert markdown to HTML. Handles tables, code blocks, headings, lists, links, emphasis."""
    lines = md_content.split("\n")
    html_parts = []
    in_code_block = False
    code_lang = ""
    code_lines = []
    in_table = False
    table_lines = []
    in_list = False
    in_comment = False
    list_type = None
    list_items = []

    def flush_table():
        nonlocal in_table, table_lines
        if not table_lines:
            return ""
        rows = []
        for i, line in enumerate(table_lines):
            cells = [c.strip() for c in _split_table_row(line)]
            if i == 1 and all(set(c.strip()) <= set("-: ") for c in cells):
                continue  # separator row
            tag = "th" if i == 0 else "td"
            row_cells = "".join(f"<{tag}>{inline_format(c)}</{tag}>" for c in cells)
            rows.append(f"<tr>{row_cells}</tr>")
        in_table = False
        table_lines = []
        return f'<table>{"".join(rows)}</table>'

    def flush_list():
        nonlocal in_list, list_type, list_items
        if not list_items:
            return ""
        tag = "ol" if list_type == "ol" else "ul"
        # list_items holds (checkbox_html, text) tuples; checkbox_html is ""
        # for non-task items. The checkbox <input> is prepended after
        # inline_format escapes the item text, so the tag survives.
        items = "".join(
            f"<li>{cb}{inline_format(item)}</li>" for cb, item in list_items
        )
        in_list = False
        list_type = None
        list_items = []
        return f"<{tag}>{items}</{tag}>"

    def inline_format(text: str) -> str:
        """Apply inline formatting: bold, italic, code, links, checkboxes.

        Root-cause discipline: emphasis/score/strikethrough passes must never
        run over text that already contains generated HTML, or they bleed into
        <code> spans, <a href="..."> attributes, and link labels (corrupting
        IAM ARNs, pod-*-a/pod-*-b names, and band words inside URLs). So we
        render code spans and links FIRST, swap each generated fragment out for
        an opaque placeholder (\x00N\x00 — digits only, immune to every pass
        below), run the emphasis/score transforms on the remaining plain text,
        then restore the placeholders verbatim.
        """
        # Escape HTML first so cluster-derived strings (labels, image tags,
        # annotations) can't inject markup. Markdown transforms below
        # re-introduce tags only for trusted patterns.
        text = html.escape(text)

        protected = []

        def _stash(fragment: str) -> str:
            token = "\x00%d\x00" % len(protected)
            protected.append(fragment)
            return token

        # Code spans first (to avoid processing inside them). The rendered
        # <code>...</code> is stashed so no later pass sees its interior.
        text = re.sub(
            r"`([^`]+)`",
            lambda m: _stash(f"<code>{m.group(1)}</code>"),
            text,
        )

        # Links — only allow safe URL schemes; leave unsafe links as plain
        # text. The whole rendered <a> (href attribute AND label) is stashed so
        # emphasis/score passes never touch the URL or the label.
        def render_link(match):
            label, url = match.group(1), match.group(2)
            # Block protocol-relative URLs ("//attacker.example"): a leading
            # "//" is NOT safe even though it starts with "/".
            safe = (
                url.startswith(("http://", "https://", "mailto:", "#"))
                or (url.startswith("/") and not url.startswith("//"))
            )
            if not safe:
                return match.group(0)
            return _stash(f'<a href="{url}">{label}</a>')
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", render_link, text)

        # From here on, `text` contains only plain (escaped) text plus opaque
        # placeholders — safe to run the greedy emphasis/score passes.
        # Bold
        text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
        # Italic. Require the opening ``*`` to hug a word character so bare
        # wildcard asterisks in IAM ARNs / glob paths (``"*"``, ``s3:::bucket/*``)
        # are left literal instead of being paired into a spurious <em>. Real
        # emphasis (``*word*``) always opens on a word char; the closer stays
        # permissive so a phrase ending in punctuation (``*...full terms.*``)
        # still italicizes.
        text = re.sub(r"\*(\w[^*]*?)\*", r"<em>\1</em>", text)
        # Strikethrough
        text = re.sub(r"~~([^~]+)~~", r"<del>\1</del>", text)
        # Score styling. NOT READY is styled via the READY lookbehind below
        # (matching "NOT READY" first then "READY" left the inner READY of a
        # "NOT READY" verdict wrapped green — false positive). The negative
        # lookbehind on READY skips the READY inside "NOT READY", and the
        # NOT-READY rule then styles the whole phrase red.
        text = re.sub(r"(?<!NOT )\b(READY)\b", r'<span class="score-ready">READY</span>', text)
        text = re.sub(r"\b(NOT READY)\b", r'<span class="score-not-ready">NOT READY</span>', text)
        text = re.sub(r"\b(RISKY)\b", r'<span class="score-risky">RISKY</span>', text)
        text = re.sub(r"\b(FAIR)\b", r'<span class="score-fair">FAIR</span>', text)
        text = re.sub(r"\b(GOOD)\b", r'<span class="score-good">GOOD</span>', text)

        # Restore protected fragments verbatim.
        for i, fragment in enumerate(protected):
            text = text.replace("\x00%d\x00" % i, fragment)
        return text

    for line in lines:
        # Code blocks
        if line.strip().startswith("```"):
            if in_code_block:
                escaped = html.escape("\n".join(code_lines))
                # Escape the fence info-string before interpolating it into the
                # class attribute — an unescaped info-string (e.g.
                # `bash"><script>...`) would otherwise break out and inject a
                # live <script> into the DOM.
                lang_attr = (
                    f' class="language-{html.escape(code_lang, quote=True)}"'
                    if code_lang else ""
                )
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

        # HTML comments (<!-- ... -->) — strip them so they never reach the
        # html.escape() pass below (otherwise a template comment renders as
        # visible "<p>&lt;!-- ... --&gt;</p>" garbage). Handles single-line
        # comments, multiple comments on one line, and multi-line comments.
        # Comments inside fenced code blocks are left intact (handled above).
        if in_comment:
            end = line.find("-->")
            if end == -1:
                continue  # still inside a multi-line comment; drop the line
            in_comment = False
            line = line[end + 3:]  # resume after the comment close
        # Remove any complete <!-- ... --> spans on this line. re.DOTALL makes
        # "." span newlines so a comment can never slip through unfiltered
        # (CodeQL py/bad-tag-filter); multi-line comments are also handled by the
        # in_comment state machine above, but the flag keeps this span robust.
        line = re.sub(r"<!--.*?-->", "", line, flags=re.DOTALL)
        # An unterminated <!-- opens a multi-line comment: keep the text before
        # it, then swallow subsequent lines until --> is seen.
        open_idx = line.find("<!--")
        if open_idx != -1:
            in_comment = True
            line = line[:open_idx]
        # If nothing but a (now-stripped) comment remained, skip the empty line
        # rather than emitting an empty <p>.
        if not line.strip():
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
            html_parts.append(f"<h{level}>{inline_format(text)}</h{level}>")
            continue

        # Blockquote
        if stripped.startswith(">"):
            if in_list:
                html_parts.append(flush_list())
            text = stripped.lstrip("> ")
            html_parts.append(f"<blockquote><p>{inline_format(text)}</p></blockquote>")
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
            item_text = list_match.group(1)
            # Task-list checkbox: the leading "- " is already stripped by the
            # list regex, so detect "[ ]"/"[x]" on the captured text here.
            cb = ""
            cb_match = re.match(r"^\[([ xX])\]\s+(.*)$", item_text)
            if cb_match:
                checked = cb_match.group(1).lower() == "x"
                cb = ('<input type="checkbox" checked disabled> '
                      if checked else '<input type="checkbox" disabled> ')
                item_text = cb_match.group(2)
            list_items.append((cb, item_text))
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
            list_items.append(("", ol_match.group(1)))
            continue

        # Regular paragraph
        if in_list:
            html_parts.append(flush_list())
        html_parts.append(f"<p>{inline_format(stripped)}</p>")

    # Flush remaining
    if in_code_block:
        escaped = html.escape("\n".join(code_lines))
        html_parts.append(f"<pre><code>{escaped}</code></pre>")
    if in_table:
        html_parts.append(flush_table())
    if in_list:
        html_parts.append(flush_list())

    return "\n".join(html_parts)


def build_html(title: str, body_html: str) -> str:
    """Wrap body HTML in a complete HTML document with embedded CSS."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)}</title>
    <style>
{CSS}
    </style>
</head>
<body>
{body_html}
</body>
</html>"""


def extract_title(md_content: str) -> str:
    """Extract the first H1 heading as the document title."""
    for line in md_content.split("\n"):
        if line.strip().startswith("# "):
            return line.strip().lstrip("# ").strip()
    return "EKS Upgrade Assessment Report"


def main():
    input_file, output_file = parse_args()

    if not os.path.exists(input_file):
        print(f"Error: File not found: {input_file}")
        sys.exit(1)

    # A directory (or other non-regular path) passed as the input would raise
    # IsADirectoryError from open(); report it cleanly with a nonzero exit
    # instead of a traceback.
    if os.path.isdir(input_file):
        print(f"Error: Input is a directory, not a file: {input_file}")
        sys.exit(1)

    try:
        with open(input_file, "r", encoding="utf-8") as f:
            md_content = f.read()
    except (IsADirectoryError, OSError) as exc:
        print(f"Error: Could not read input file {input_file}: {exc}")
        sys.exit(1)

    title = extract_title(md_content)
    body_html = md_to_html(md_content)
    full_html = build_html(title, body_html)

    # Always write UTF-8 regardless of the ambient locale so non-ASCII content
    # round-trips; the explicit encoding also prevents an ascii-locale
    # UnicodeEncodeError at write time.
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(full_html)
    except (IsADirectoryError, OSError) as exc:
        print(f"Error: Could not write output file {output_file}: {exc}")
        sys.exit(1)

    input_size = os.path.getsize(input_file)
    output_size = os.path.getsize(output_file)
    # Use a plain ASCII status line: under an ascii stdout locale a non-ASCII
    # glyph here would raise UnicodeEncodeError *after* the file was already
    # written, making the exit code lie about the outcome.
    print(
        f"Converted: {input_file} ({input_size:,} bytes) -> "
        f"{output_file} ({output_size:,} bytes)"
    )


if __name__ == "__main__":
    main()
