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


def inline_format(text):
    """Process inline markdown: bold, code, links, emoji badges.

    Input must already be HTML-escaped with quote=True by the caller.
    Link hrefs are validated against a scheme allowlist; because `"` and
    `&` in the URL are already escaped to `&quot;`/`&amp;`, cluster-derived
    strings cannot break out of the href attribute.

    Inline code spans (`...`) are extracted to placeholders BEFORE any
    em/bold/link/badge substitution runs, so their contents (e.g. IAM ARN
    wildcards like `arn:aws:eks:*:...:cluster/*` or a literal `*`) are never
    corrupted by the emphasis regexes. They are restored, wrapped in <code>,
    at the very end.
    """
    # Extract inline code spans first so nothing inside them is substituted.
    # CommonMark fences: a run of N backticks opens a span that closes on the
    # next run of EXACTLY N backticks; everything in between (single backticks,
    # pipes, *asterisks*, etc.) is literal. A single-backtick regex would
    # mishandle a double-backtick span like ``aws eks|get`` -- it matches the
    # empty span between the first pair of backticks, leaving stray literal
    # backticks around a mangled interior and an unstashed pipe -- so we scan
    # by fence length instead (mirroring the run-length logic in _split_pipes).
    code_spans = []
    out_parts = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == '`':
            j = i
            while j < n and text[j] == '`':
                j += 1
            run = j - i
            # Look for a closing run of EXACTLY `run` backticks.
            k = j
            closed_at = -1
            while k < n:
                if text[k] == '`':
                    m = k
                    while m < n and text[m] == '`':
                        m += 1
                    if m - k == run:
                        closed_at = k
                        break
                    k = m
                else:
                    k += 1
            if closed_at != -1:
                code_spans.append(text[j:closed_at])
                out_parts.append(f'\x00CODE{len(code_spans) - 1}\x00')
                i = closed_at + run
            else:
                # No matching closing fence: treat the run as literal backticks.
                out_parts.append('`' * run)
                i = j
            continue
        out_parts.append(ch)
        i += 1
    text = ''.join(out_parts)

    # Links and autolinks are resolved to full <a> anchors NOW and each anchor
    # is stashed behind an inert ``\x00LINK<n>\x00`` placeholder BEFORE the
    # emphasis and RAG-emoji-badge passes run. This is essential: a URL (href
    # or visible text) can legitimately contain ``**`` or a status emoji
    # (e.g. https://ex.com/**bold** or a link to a 🟢-named anchor); if the
    # finished anchor were left inline, the emphasis regexes would inject
    # <strong>/<em> tags and the emoji replacements would splice <span> badges
    # INTO the href attribute and visible text, corrupting both. Stashing the
    # whole anchor keeps the URL and link text verbatim (they were already
    # html.escaped and, for the href, scheme-sanitized) through those passes.
    # Placeholders are restored at the very end, alongside the code spans.
    links = []

    def _stash_link(anchor_html):
        links.append(anchor_html)
        return f'\x00LINK{len(links) - 1}\x00'

    def _emphasis_and_badges(s):
        """Apply bold/italic emphasis and RAG-emoji badge substitutions.

        Shared by the main-text pass and by link text. Link text is stashed
        with its anchor BEFORE the main emphasis pass runs, so without this the
        link text ``[**bold**](url)`` would keep literal asterisks. Running the
        same emphasis rules on the link text here fixes that while leaving the
        (already scheme-sanitized, HTML-escaped) href untouched. Any CODE
        placeholder inside the link text is inert to these rules and is restored
        later once the anchor is spliced back in.
        """
        # Bold+italic: ***text*** — must run before the ** rule, otherwise the
        # leading ** is consumed and a stray * is left behind.
        s = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', s)
        # Bold: **text**
        s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
        # Italic: *text* — the opening * must be at start-of-string or preceded
        # by whitespace, and the closing * must be at end-of-string or followed
        # by whitespace/sentence punctuation; both delimiters hug non-space
        # content. This matches genuine *emphasis* while leaving IAM wildcards
        # untouched: in arn:aws:eks:*:...:cluster/*, eks:Describe*, and 5*3 the
        # stars are glued to identifiers (:, /, digits) so no * can ever open
        # emphasis. (after bold, so ** pairs are already converted.)
        s = re.sub(r'(?<![^\s([])\*(\S(?:[^*]*\S)?)\*(?=[\s.,;:!?)\]]|$)', r'<em>\1</em>', s)
        # RAG emoji badges
        s = s.replace('🔴', '<span class="red">RED</span>')
        s = s.replace('🟡', '<span class="amber">AMBER</span>')
        s = s.replace('🟢', '<span class="green">GREEN</span>')
        s = s.replace('⬜', '<span class="unknown">UNKNOWN</span>')
        return s

    # Links: [text](url) — scheme-allowlisted, href-escaped. The URL capture
    # tolerates one level of balanced parens so a URL like
    # https://ex.com/a(b).html is not truncated at the first ')'.
    #
    # A URL written as a code span — ``[click](`http://x`)`` — has already had
    # its ``http://x`` stashed as a ``\x00CODE<n>\x00`` placeholder above, so
    # the raw regex group would be the placeholder, not the URL, yielding
    # ``href="CODE0"`` (data loss). Resolve any placeholder back to its span
    # content BEFORE scheme-sanitizing so the real URL survives. The link text
    # (group 1) keeps its placeholder and is restored as <code> later.
    def _link_sub_local(match):
        text_g = match.group(1)
        url_g = match.group(2)

        def _unstash(m):
            idx = int(m.group(1))
            if 0 <= idx < len(code_spans):
                return code_spans[idx]
            return m.group(0)

        url_resolved = re.sub(r'\x00CODE(\d+)\x00', _unstash, url_g)
        # Process inline markdown (bold/italic/badges) in the VISIBLE link text
        # only — never the href. Without this the link text is frozen before the
        # main emphasis pass runs, so ``[**bold**](url)`` would render literal
        # asterisks instead of <strong>. CODE placeholders inside the text stay
        # inert and are restored later.
        text_html = _emphasis_and_badges(text_g)
        return _stash_link(f'<a href="{_safe_href(url_resolved)}">{text_html}</a>')

    text = re.sub(r'\[([^\]]+)\]\(((?:[^()]|\([^()]*\))*)\)', _link_sub_local, text)
    # Autolinks: <https://...> (the angle brackets arrive HTML-escaped as
    # &lt;...&gt;). Rendered as a scheme-sanitized anchor rather than escaped
    # literal text. The captured URL is already HTML-escaped (the caller
    # escapes before inline formatting), so it is safe as both the visible
    # text and, after scheme-sanitizing, the href.
    def _autolink_sub_local(match):
        raw = match.group(1)
        return _stash_link(f'<a href="{_safe_href(raw)}">{raw}</a>')

    # The URL char class excludes NUL (``\x00``) so an autolink pattern that
    # wraps an already-stashed link — whose ``\x00LINK<n>\x00`` placeholder sits
    # in the text — cannot swallow the placeholder into the href/visible text.
    # Otherwise the literal ``LINK0`` string and two NUL bytes would leak into
    # the output (corrupt href + invalid HTML).
    text = re.sub(r'&lt;(https?://[^\s\x00]+?)&gt;', _autolink_sub_local, text)
    # Emphasis + RAG-emoji badges on the main text. Stashed link anchors sit
    # behind inert \x00LINK<n>\x00 placeholders, so these substitutions cannot
    # touch any href or link text (link text emphasis was applied at stash time).
    text = _emphasis_and_badges(text)

    # Restore inline code spans, now wrapped in <code>.
    # Defense-in-depth: bounds-check the index so an out-of-range placeholder
    # (which should be impossible now that NUL bytes are stripped upstream) is
    # left as literal text rather than raising IndexError and aborting the
    # whole conversion.
    def _restore_code(match):
        idx = int(match.group(1))
        if 0 <= idx < len(code_spans):
            return f'<code>{code_spans[idx]}</code>'
        return match.group(0)

    # Restore the stashed <a> anchors first, then the code spans. A stashed
    # anchor's visible text can itself hold a CODE placeholder (``[`c`](url)``);
    # that anchor was pulled OUT of ``text`` when it was stashed, so the CODE
    # placeholder inside it is only reachable once the anchor is spliced back
    # in. Restoring links before code therefore re-exposes those inner CODE
    # placeholders to the code pass. (Anchors never sit inside code spans —
    # code spans are literal text and no link regex runs on their contents —
    # so there is no reverse dependency.) Both passes run AFTER emphasis and
    # the RAG-emoji badges, so no href/link-text was exposed to those regexes.
    def _restore_link(match):
        idx = int(match.group(1))
        if 0 <= idx < len(links):
            return links[idx]
        return match.group(0)

    text = re.sub(r'\x00LINK(\d+)\x00', _restore_link, text)
    text = re.sub(r'\x00CODE(\d+)\x00', _restore_code, text)
    return text


def _split_pipes(s, respect_code):
    """Split ``s`` on unescaped ``|``.

    If ``respect_code`` is True, a ``|`` inside a backtick code span is kept
    as literal cell content; otherwise backticks are treated as ordinary
    characters and every unescaped ``|`` splits. An escaped ``\\|`` never
    splits; the escape is preserved here and collapsed to a literal ``|`` by
    the caller after all splitting is complete (so a re-split pass cannot
    accidentally break on a pipe that was originally escaped).

    Code spans are tracked by backtick RUN length (CommonMark fences): a run
    of N backticks opens a span, which only closes on a later run of EXACTLY
    N backticks. This keeps multi-backtick spans (e.g. a double-backtick span
    wrapping ``aws eks|describe``) intact -- the interior ``|`` stays literal
    -- instead of a naive per-backtick toggle prematurely closing after the
    second backtick.
    """
    cells = []
    buf = []
    in_code = False
    fence = 0
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == '\\' and i + 1 < n and s[i + 1] == '|':
            buf.append('\\|')
            i += 2
            continue
        if respect_code and c == '`':
            j = i
            while j < n and s[j] == '`':
                j += 1
            run = j - i
            if not in_code:
                in_code = True
                fence = run
            elif run == fence:
                in_code = False
                fence = 0
            # A run that doesn't match the open fence stays literal inside the
            # span (in_code unchanged).
            buf.append('`' * run)
            i = j
            continue
        if c == '|' and not in_code:
            cells.append(''.join(buf))
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    cells.append(''.join(buf))
    return cells


def _strip_border_cells(cells):
    """Emulate ``strip('|')``: drop the single empty cell produced by a
    leading and/or trailing border pipe. Pop AT MOST ONE per side so an
    intentionally-empty first/last column (e.g. ``||a|b|``) is preserved
    rather than over-stripped into a ragged row.
    """
    cells = list(cells)
    if len(cells) > 1 and cells[0] == '':
        cells.pop(0)
    if len(cells) > 1 and cells[-1] == '':
        cells.pop()
    return cells


def _split_row_cells(line, ncols=None):
    """Split a markdown table row into cell strings.

    Unlike a naive ``line.strip('|').split('|')`` this does NOT split on a
    pipe that is:
      * inside a *balanced* inline code span (backtick-delimited), or
      * backslash-escaped as ``\\|``.
    An escaped ``\\|`` is emitted as a literal ``|`` in the returned cell
    content (the backslash is consumed), both inside and outside code spans,
    matching GitHub-flavored-markdown table semantics.

    The primary split honors balanced code spans, so a pipe inside a
    balanced ``a|b`` backtick span stays literal (one cell). But a code-aware
    split is fooled
    when TWO different cells each contain a single *stray* (unclosed) backtick:
    the two backticks pair ACROSS the pipe between them, fusing the cells into
    one -- and the fused cell has an EVEN backtick count, so a per-cell
    odd-count re-split never fires.

    To recover, the split is validated against the header column count
    ``ncols`` (when known). If the code-aware split does not produce exactly
    ``ncols`` cells, a code-UNAWARE split (every unescaped pipe splits) is
    tried; it is adopted only when it yields exactly ``ncols`` cells. This
    keeps balanced-code-span and ``\\|``-escape handling for well-formed rows
    while realigning stray-backtick rows so the final column (often the
    RED/AMBER rating) is not dropped or shifted.

    Leading/trailing delimiter (border) pipes are dropped, reproducing the
    old ``strip('|')`` behavior for normal rows.
    """
    # Strip surrounding whitespace first: a trailing space after the final
    # border pipe (``| a | b | ``) or a leading space before the first pipe
    # would otherwise survive as a non-empty '' -> ' ' cell OUTSIDE the
    # border pipes, defeating the border-pipe drop below and yielding a
    # phantom column (ragged table vs. sibling rows).
    line = line.strip()

    # Code-aware split (respects balanced/backtick-run code spans).
    aware = _strip_border_cells(_split_pipes(line, respect_code=True))

    # Per-cell recovery: any cell still holding an ODD backtick count means a
    # lone backtick swallowed its interior pipes; re-split just that cell with
    # backticks treated as literal. Handles the single-stray-backtick case
    # without a known column count.
    #
    # NOTE: ``aware`` has ALREADY had its border cells stripped, and the
    # per-cell recovery only ever splits an interior cell into MORE cells (it
    # never re-introduces a leading/trailing border pipe). Re-running
    # ``_strip_border_cells`` here would strip a SECOND time and wrongly drop a
    # legitimately-empty first/last column — e.g. ``||a|b|`` (docstring case:
    # intentional empty first column) would come back as ``['a','b']`` instead
    # of ``['', 'a', 'b']``. So do NOT strip again; keep ``recovered`` as-is.
    recovered = []
    for cell in aware:
        if cell.count('`') % 2 == 1:
            pieces = _split_pipes(cell, respect_code=False)
            # A single stray backtick opens a span that never closes, so the
            # code-aware split above swallowed every following pipe -- INCLUDING
            # the row's trailing border pipe -- into this one cell, where
            # _strip_border_cells could not see it. Re-splitting code-unaware now
            # re-exposes that border pipe as a phantom EMPTY trailing cell. Drop a
            # single trailing empty piece to undo it (off-by-one fix). Only the
            # trailing border can be swallowed this way: the leading border pipe
            # sits at index 0 and always splits before any span opens.
            if len(pieces) > 1 and pieces[-1] == '':
                pieces.pop()
            recovered.extend(pieces)
        else:
            recovered.append(cell)
    cells = recovered

    # Header-count validation: if we know how many columns the table has and
    # the code-aware result doesn't match it, we MAY try a fully code-unaware
    # split. But a code-unaware split shreds a legitimately BALANCED code span
    # that happens to contain a pipe (``| a | `x|y` | 🔴 |`` -> the ``|`` in
    # ``x|y`` would become a column break), so we must not adopt it merely
    # because it hits ncols.
    #
    # Two look-alike shapes both produce a short (< ncols) code-aware split
    # whose fused cell has an EVEN backtick count:
    #   (a) balanced span:  `x|y`                 -> intentional, keep as 1 cell
    #   (b) cross-cell fuse: uses `gp2 | to `gp3  -> two stray backticks that
    #                                                paired ACROSS a border pipe
    # Counting cells/backticks cannot tell them apart, but their structure can:
    # (a) is a CLEAN whole-cell code span (the cell is nothing but a single
    # backtick-delimited span), whereas (b) has real text outside the backtick
    # pair. So for a short row we only fall back to the unaware split when a
    # pipe-bearing cell is NOT a clean whole-cell span. We still fall back on an
    # over-count (> ncols) or a leftover ODD-backtick cell (single stray).
    def _is_clean_code_span(cell):
        c = cell.strip()
        lead = len(c) - len(c.lstrip('`'))
        trail = len(c) - len(c.rstrip('`'))
        # A clean span: matched non-empty leading/trailing fences of equal
        # length and no stray backtick in the interior.
        return lead > 0 and lead == trail and '`' not in c[lead:len(c) - trail]

    if ncols is not None and len(cells) != ncols:
        aware_has_odd = any(cell.count('`') % 2 == 1 for cell in cells)
        # Cells the unaware split would break further are those still holding an
        # unescaped pipe. (An escaped ``\|`` never splits in either mode.)
        def _has_unescaped_pipe(cell):
            return len(_split_pipes(cell, respect_code=False)) > 1
        fused_stray = any(
            _has_unescaped_pipe(cell) and not _is_clean_code_span(cell)
            for cell in cells
        )
        if len(cells) > ncols or aware_has_odd or (len(cells) < ncols and fused_stray):
            unaware = _strip_border_cells(_split_pipes(line, respect_code=False))
            if len(unaware) == ncols:
                cells = unaware

    # Now that splitting is complete, collapse escaped ``\|`` to a literal
    # ``|`` and trim each cell.
    return [c.replace('\\|', '|').strip() for c in cells]


def parse_table(lines):
    """Convert markdown table lines to HTML table."""
    if not lines:
        return ""
    if len(lines) == 1:
        # Single pipe line with no separator row — render as a one-row table
        # instead of silently dropping the content.
        only = _split_row_cells(lines[0])
        cells = ''.join(f'<td>{inline_format(escape(c))}</td>' for c in only)
        return '<table>\n<tbody>\n<tr>' + cells + '</tr>\n</tbody></table>\n'
    # Only treat line index 1 as a separator (and skip it) if it actually IS
    # a separator row. Each cell must be a run of >=2 dashes with optional
    # alignment colons (``:?-{2,}:?``). GFM permits short separators like
    # ``|--|--|``; requiring only 3+ dashes previously mis-rendered such a
    # 2-dash separator as a garbage data row (losing <thead>). We stop at 2
    # (not 1) because a run of SINGLE dashes is used by this skill as real
    # N/A placeholder DATA (``| - | - | - | - |``); treating a lone ``-`` as
    # a separator would silently drop that data row. Single dash => data,
    # two-or-more dashes => separator.
    def _is_separator(row):
        segs = [s.strip() for s in row.strip().strip('|').split('|')]
        segs = [s for s in segs if s != '']
        return bool(segs) and all(re.fullmatch(r':?-{2,}:?', s) for s in segs)

    has_separator = _is_separator(lines[1])

    if has_separator:
        headers = _split_row_cells(lines[0])
        data_lines = lines[2:]
    else:
        headers = None
        data_lines = lines

    # The header row defines the expected column count; pass it to the row
    # splitter so stray-backtick rows can be realigned against it. With no
    # header/separator there is no reference count, so leave it unconstrained.
    ncols = len(headers) if headers is not None else None

    rows = []
    for line in data_lines:
        cells = _split_row_cells(line, ncols=ncols)
        rows.append(cells)

    out = '<table>\n'
    if headers is not None:
        out += '<thead><tr>'
        for h in headers:
            out += f'<th>{inline_format(escape(h))}</th>'
        out += '</tr></thead>\n'
    out += '<tbody>\n'
    for row in rows:
        out += '<tr>'
        for cell in row:
            out += f'<td>{inline_format(escape(cell))}</td>'
        out += '</tr>\n'
    out += '</tbody></table>\n'
    return out


def convert(md_text):
    """Convert markdown to HTML."""
    # Strip NUL bytes up front. NUL is illegal in Markdown/HTML text anyway,
    # and the inline-code placeholder mechanism (inline_format) uses
    # ``\x00CODE<n>\x00`` sentinels: if a source document contained a literal
    # ``\x00CODE<n>\x00``-shaped byte run it would be mistaken for a real
    # placeholder, indexing ``code_spans`` out of range (IndexError -> whole
    # conversion aborts) or spoofing an unrelated code span's content into it.
    # Removing NUL at this outermost point means no downstream code path
    # (headings, table cells, paragraphs, list items, code blocks) can ever
    # see an input-originating sentinel.
    md_text = md_text.replace('\x00', '')
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
        m = re.match(r'^(#{1,6})\s+(.+)$', stripped)
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
            content = stripped[2:]
            # An INTERNAL-banner marker inside a blockquote (``> ⚠️ **INTERNAL
            # USE ONLY**``) should render as the banner, not a plain quote.
            if '⚠️' in content and 'INTERNAL' in content.upper():
                out.append(f'<div class="internal-banner">{inline_format(escape(content))}</div>')
            else:
                out.append(f'<blockquote>{inline_format(escape(content))}</blockquote>')
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
    # Strip NUL from the title too: it may be passed in directly (not only via
    # main's H1 extraction) and NUL is illegal in HTML text.
    title = title.replace('\x00', '')
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

    had_error = False
    for f in files:
        p = Path(f)
        if not p.exists():
            print(f"Error: {f} not found", file=sys.stderr)
            had_error = True
            continue

        # Per-file isolation: a decode error (invalid UTF-8 byte) or any other
        # error on ONE file must be reported and skipped without aborting the
        # whole batch, so the remaining valid files still convert. We read with
        # errors='replace' so an undecodable byte becomes U+FFFD rather than
        # raising UnicodeDecodeError; the surrounding try/except catches any
        # other per-file failure too.
        try:
            md = p.read_text(encoding='utf-8', errors='replace')

            # Extract title from first H1. Strip NUL so a NUL in the heading
            # text cannot leak into <title> (defense-in-depth; convert() also
            # strips NUL from the body).
            m = re.search(r'^#\s+(.+)$', md, re.MULTILINE)
            title = (m.group(1) if m else p.stem).replace('\x00', '')

            result = md_to_html(md, title)

            if output_path and len(files) == 1:
                out = Path(output_path)
            else:
                out = p.with_suffix('.html')

            out.write_text(result, encoding='utf-8')
            print(f"✓ {p.name} → {out.name}")
        except Exception as e:
            print(f"Error: failed to convert {f}: {e}", file=sys.stderr)
            had_error = True
            continue

    # Exit non-zero if any input file was missing/unreadable or failed to
    # convert, so CI (and shell callers) can detect the failure. Successful
    # files are still converted; this only affects the process exit status.
    if had_error:
        sys.exit(1)


if __name__ == '__main__':
    main()
