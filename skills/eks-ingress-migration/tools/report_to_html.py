#!/usr/bin/env python3
"""Convert Markdown ingress migration report to HTML dashboard with 3D topology and left nav."""

import argparse
import base64
import json
import re
import sys
import html as H
from pathlib import Path


def strip_bold(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text)


def badge_wrap(text: str) -> str:
    for r, cls in [("GREEN", "green"), ("AMBER", "amber"), ("RED", "red"), ("UNKNOWN", "unknown")]:
        text = text.replace(r, f'<span class="badge {cls}">{r}</span>')
    text = text.replace("🟢", '<span class="badge green">●</span>')
    text = text.replace("🟡", '<span class="badge amber">●</span>')
    text = text.replace("🟠", '<span class="badge orange">●</span>')
    text = text.replace("🔴", '<span class="badge red">●</span>')
    text = text.replace("⬜", '<span class="badge unknown">●</span>')
    text = text.replace("✅", '<span style="color:#788c5d">✓</span>')
    text = text.replace("❌", '<span style="color:#c44">✗</span>')
    text = text.replace("⚠️", '<span style="color:#d97706">⚠</span>')
    return text


def inline(text: str) -> str:
    t = H.escape(text)
    t = t.replace("&lt;br&gt;", "<br>").replace("&lt;br/&gt;", "<br>").replace("&lt;br /&gt;", "<br>")
    t = re.sub(r"!!(.+?)!!", r'<span class="hot">\1</span>', t)          # high-impact red highlight
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)               # bold
    t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
    t = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2" target="_blank">\1</a>', t)
    return badge_wrap(t)


def render_list(items: list[tuple[int, str]]) -> str:
    """Render (indent, text) bullet items into nested <ul> by indent level."""
    def build(idx: int, base: int):
        out = "<ul>"
        while idx < len(items):
            ind, txt = items[idx]
            if ind < base:
                break
            if ind > base:
                sub, idx = build(idx, ind); out += sub; continue
            out += "<li>" + inline(txt)
            if idx + 1 < len(items) and items[idx + 1][0] > base:
                sub, idx = build(idx + 1, items[idx + 1][0]); out += sub
            else:
                idx += 1
            out += "</li>"
        return out + "</ul>", idx
    return build(0, items[0][0])[0] if items else ""


def md_table_to_html(lines: list[str]) -> str:
    headers = [c.strip() for c in lines[0].strip().strip("|").split("|")]
    col_count = len(headers)
    hdr = "".join(f"<th>{badge_wrap(strip_bold(H.escape(h)))}</th>" for h in headers)
    def render_cell(c: str) -> str:
        # cell with bullet markup ("- item<br>  - sub") -> nested <ul>
        if re.search(r"(?:^|<br>)\s*[-*]\s", c):
            items = []
            for s in re.split(r"<br>", c):
                m = re.match(r"^(\s*)[-*]\s(.*)$", s)
                if m:
                    items.append((len(m.group(1)), m.group(2)))
                elif s.strip():
                    items.append((0, s.strip()))
            if items:
                return render_list(items)
        return inline(c)
    rows = ""
    for line in lines[2:]:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        while len(cells) < col_count:
            cells.append("")
        rows += "<tr>" + "".join(f"<td>{render_cell(c)}</td>" for c in cells) + "</tr>"
    return f'<div class="table-wrap"><table><thead><tr>{hdr}</tr></thead><tbody>{rows}</tbody></table></div>'


def is_table_sep(line: str) -> bool:
    return bool(re.match(r"^\|[\s\-:|]+\|$", line.strip()))


def convert_md(md_text: str, id_prefix: str = "") -> tuple[str, list[tuple[str, str]]]:
    """Convert markdown to HTML. id_prefix scopes element IDs per cluster (e.g. 'c0-')."""
    lines = md_text.split("\n")
    parts, toc = [], []
    sec = 0
    i = 0
    in_code = False

    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            if not in_code:
                in_code = True
                lang = re.match(r"^```(\w+)?", line.strip())
                lang_cls = f' class="language-{lang.group(1)}"' if lang and lang.group(1) else ""
                i += 1
                code_lines = []
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code_lines.append(H.escape(lines[i]))
                    i += 1
                i += 1
                in_code = False
                parts.append(f'<pre><code{lang_cls}>{chr(10).join(code_lines)}</code></pre>')
                continue
            else:
                in_code = False; i += 1; continue
        if in_code: i += 1; continue
        if re.match(r"^\s{2,}[┌└├│─►┐┘┤┬┴┼\+\-\|]", line): i += 1; continue

        if "|" in line and i + 1 < len(lines) and is_table_sep(lines[i + 1]):
            tbl = [line]; i += 1
            while i < len(lines) and "|" in lines[i]: tbl.append(lines[i]); i += 1
            parts.append(md_table_to_html(tbl)); continue

        if line.startswith("# "):
            pass  # skip H1 — banner handles title
        elif line.startswith("## "):
            title = line[3:].strip()
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            scoped_id = f"{id_prefix}{slug}"
            sec += 1; toc.append((slug, title))
            if sec > 1: parts.append("</div></details>")
            parts.append(
                f'<details class="section" open id="{scoped_id}" data-section="{slug}">'
                f'<summary><h2>{inline(title)}</h2><span class="toggle">▾</span></summary>'
                f'<div class="section-body">')
        elif line.startswith("### "): parts.append(f"<h3>{inline(line[4:])}</h3>")
        elif line.startswith("#### "): parts.append(f"<h4>{inline(line[5:])}</h4>")
        elif line.startswith("> "): parts.append(f'<blockquote>{inline(line[2:])}</blockquote>')
        elif line.startswith("---"): pass
        elif re.match(r"^\s*[-*]\s", line):
            block = []
            while i < len(lines) and re.match(r"^\s*[-*]\s", lines[i]):
                m = re.match(r"^(\s*)[-*]\s(.*)$", lines[i])
                block.append((len(m.group(1)), m.group(2))); i += 1
            parts.append(render_list(block)); continue
        elif re.match(r"^\d+\.\s", line.strip()):
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s", lines[i].strip()):
                items.append(inline(re.sub(r"^\d+\.\s*", "", lines[i].strip()))); i += 1
            parts.append("<ol>" + "".join(f"<li>{it}</li>" for it in items) + "</ol>"); continue
        elif line.strip() == "": pass
        else: parts.append(f"<p>{inline(line)}</p>")
        i += 1

    if sec > 0: parts.append("</div></details>")
    html = "\n".join(parts)
    if id_prefix:
        html = re.sub(r'href="#([a-z0-9][a-z0-9-]*)"', lambda m: f'href="#{id_prefix}{m.group(1)}"', html)
    return html, toc


# 3D topology is built inline per cluster in build_html()


CSS = """
:root{--bg:#faf9f5;--surface:#fff;--border:#e8e6dc;--text:#141413;--text2:#b0aea5;--accent:#d97757;--green:#788c5d;--green-bg:#eef2e8;--amber:#d97706;--amber-bg:#fef3c7;--red:#c44;--red-bg:#fceaea;--gray:#b0aea5;--hdr-bg:#141413;--hdr-text:#faf9f5;--radius:6px;--code-bg:#f5f4f0;--nav-w:220px}
[data-theme="dark"]{--bg:#0d1117;--surface:#161b22;--border:#30363d;--text:#e6edf3;--text2:#8b949e;--accent:#ff9900;--green:#2ea043;--green-bg:rgba(46,160,67,.15);--amber:#d29922;--amber-bg:rgba(210,153,34,.15);--red:#f85149;--red-bg:rgba(248,81,73,.15);--gray:#8b949e;--hdr-bg:#010409;--hdr-text:#e6edf3;--code-bg:#1c2128}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Lora',Georgia,serif;background:var(--bg);color:var(--text);line-height:1.7;transition:background .3s,color .3s}
a{color:var(--accent)} a:hover{text-decoration:underline}
code{background:var(--code-bg);border:1px solid var(--border);padding:2px 6px;border-radius:4px;font-size:.85em;font-family:'Courier New',monospace}
pre{background:var(--hdr-bg);color:var(--hdr-text);padding:1rem;border-radius:var(--radius);overflow-x:auto;margin:1rem 0;font-size:.85em}
pre code{background:none;border:none;color:inherit;padding:0}
blockquote{border-left:3px solid var(--amber);padding:.5rem 1rem;margin:.5rem 0;color:var(--text2);background:var(--amber-bg);border-radius:0 var(--radius) var(--radius) 0;font-size:.9rem}
ul,ol{margin:.4rem 0 .4rem 1.5rem} li{margin:.2rem 0}
/* Layout */
.layout{display:flex;min-height:100vh}
.nav{width:var(--nav-w);position:fixed;top:0;left:0;height:100vh;background:var(--hdr-bg);color:var(--hdr-text);padding:1.2rem 0;overflow-y:auto;z-index:10;display:flex;flex-direction:column}
.nav-title{font-family:'Poppins',sans-serif;font-size:.95rem;font-weight:600;padding:0 1rem .8rem;border-bottom:1px solid rgba(255,255,255,.1);margin-bottom:.5rem}
.nav-sub{font-family:'Poppins',sans-serif;font-size:.6rem;text-transform:uppercase;letter-spacing:.08em;opacity:.5;margin-top:.15rem}
.nav-section{font-family:'Poppins',sans-serif;font-size:.6rem;text-transform:uppercase;letter-spacing:.1em;color:rgba(255,255,255,.35);padding:.8rem 1rem .3rem;margin-top:.3rem}
.nav a{display:block;padding:5px 1rem 5px 1.3rem;font-family:'Poppins',sans-serif;font-size:.78rem;color:rgba(255,255,255,.7);text-decoration:none;transition:all .15s;border-left:3px solid transparent}
.nav a:hover{color:#fff;background:rgba(255,255,255,.06);border-left-color:var(--accent)}
.nav a.active{color:#fff;border-left-color:var(--accent);background:rgba(255,255,255,.08)}
.nav-bottom{margin-top:auto;padding:.8rem 1rem;border-top:1px solid rgba(255,255,255,.1)}
.theme-toggle{background:none;border:1px solid rgba(255,255,255,.2);color:var(--hdr-text);padding:5px 10px;border-radius:16px;cursor:pointer;font-family:'Poppins',sans-serif;font-size:.7rem;font-weight:500;width:100%;transition:all .2s}
.theme-toggle:hover{border-color:rgba(255,255,255,.5);background:rgba(255,255,255,.08)}
.content{margin-left:var(--nav-w);flex:1;padding:2rem 2.5rem;max-width:1000px}
/* Sections */
details.section{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);margin:1rem 0;overflow:hidden;transition:background .3s,border-color .3s}
details.section summary{display:flex;align-items:center;justify-content:space-between;padding:.75rem 1rem;cursor:pointer;list-style:none;background:var(--bg);border-bottom:1px solid var(--border)}
details.section summary::-webkit-details-marker{display:none}
details.section summary h2{font-family:'Poppins',sans-serif;font-size:.8rem;font-weight:500;text-transform:uppercase;letter-spacing:.05em;color:var(--text2);margin:0}
.toggle{color:var(--text2);transition:transform .2s;font-size:.8rem} details.section[open] .toggle{transform:rotate(180deg)}
.section-body{padding:1rem}
h3{font-family:'Poppins',sans-serif;font-size:.95rem;color:var(--text);margin:1.2rem 0 .5rem;font-weight:600}
h4{font-family:'Poppins',sans-serif;font-size:.85rem;color:var(--text2);margin:1rem 0 .4rem;font-weight:500}
p{margin:.4rem 0;font-size:.95rem}
.table-wrap{overflow-x:auto;margin:.8rem 0}
table{border-collapse:collapse;width:100%;font-size:.85rem;border:1px solid var(--border);border-radius:var(--radius)}
th{background:var(--hdr-bg);color:var(--hdr-text);padding:10px 14px;text-align:left;font-family:'Poppins',sans-serif;font-weight:500;font-size:.75rem;text-transform:uppercase;letter-spacing:.03em;white-space:nowrap}
td{padding:8px 14px;border-bottom:1px solid var(--border);word-break:break-word}
td:first-child{white-space:nowrap;font-weight:500}
tr:hover td{background:var(--bg)}
.badge{display:inline-block;padding:2px 10px;border-radius:20px;font-family:'Poppins',sans-serif;font-size:.7rem;font-weight:600;letter-spacing:.03em;white-space:nowrap}
.green{background:var(--green-bg);color:var(--green)} .amber{background:var(--amber-bg);color:var(--amber)}
.red{background:var(--red-bg);color:var(--red)} .unknown{background:#f0f0ec;color:var(--gray)}
.orange{background:#fde7d3;color:#c2410c} .hot{color:var(--red);font-weight:700}
li strong{color:var(--text)} ul ul{margin:.25rem 0 .35rem 1.6rem;list-style:circle}
td ul{margin:.15rem 0 .15rem 1.1rem} td li{margin:.12rem 0}
.hint{color:var(--text2);font-size:.8rem;margin-bottom:.5rem;font-style:italic}
.topo-info{margin-top:.5rem;padding:.5rem .8rem;font-size:.85rem;color:var(--text2);min-height:1.6em;background:var(--surface);border-radius:var(--radius);border:1px solid var(--border)}
.topo-legend{display:flex;flex-wrap:wrap;gap:1rem;margin-top:.5rem;font-family:'Poppins',sans-serif;font-size:.75rem;color:var(--text2)}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:4px;vertical-align:middle}
footer{font-family:'Poppins',sans-serif;font-size:.75rem}
@media(max-width:768px){.nav{display:none}.content{margin-left:0;padding:1rem}}
@media print{.nav{display:none}.content{margin-left:0}details.section{break-inside:avoid}#topo-wrap{display:none}}
"""


NAV_SECTIONS = [
    ("overview", "Overview", ["migration-difficulty-score", "executive-summary", "impact-indicator"]),
    ("assessment", "Assessment Summary", ["assessment-summary", "current-configuration", "ingress-discovery"]),
    ("routing", "Routing Topology", ["routing-topology", "traffic-routing"]),
    ("migration", "Migration Approach", ["migration-options", "blockers", "recommendations"]),
    ("analysis", "Analysis", ["ingress-resource-analysis", "dns-certificates-analysis", "migration-risk"]),
    ("references", "References", ["export-materials", "aws-reference-links"]),
]


def _score_badge(score: int, label: str) -> str:
    """Render the Migration Difficulty Score as a conic-gradient donut gauge + label.
    High score = easy to migrate (green); low score = hard (red)."""
    score = max(0, min(100, score))
    if score >= 80:   color = "#2ea043"   # easy
    elif score >= 70: color = "#d29922"   # moderate
    elif score >= 60: color = "#e8590c"   # hard
    else:             color = "#c44"      # very hard
    return (
        '<div style="display:flex;align-items:center;gap:1.2rem;margin:.5rem 0 1rem;padding:1.1rem 1.3rem;'
        'background:var(--surface);border:1px solid var(--border);border-left:5px solid ' + color + ';border-radius:var(--radius);">'
        '<div style="flex:0 0 auto;width:96px;height:96px;border-radius:50%;background:conic-gradient(' + color + ' '
        + str(score) + '%,var(--border) 0);display:flex;align-items:center;justify-content:center;">'
        '<div style="width:72px;height:72px;border-radius:50%;background:var(--surface);display:flex;flex-direction:column;'
        'align-items:center;justify-content:center;">'
        '<span style="font-family:Poppins,sans-serif;font-size:1.5rem;font-weight:600;color:' + color + ';line-height:1;">'
        + str(score) + '</span><span style="font-size:.55rem;color:var(--text2);letter-spacing:.05em;">/ 100</span>'
        '</div></div>'
        '<div><div style="font-family:Poppins,sans-serif;font-size:.62rem;text-transform:uppercase;letter-spacing:.1em;'
        'color:var(--text2);">Migration Difficulty</div>'
        '<div style="font-family:Poppins,sans-serif;font-size:1.4rem;font-weight:600;color:' + color + ';margin:.1rem 0;">'
        + H.escape(label) + '</div>'
        '<div style="font-size:.78rem;color:var(--text2);">Higher = easier to migrate off NGINX · '
        'Lower = harder / more business impact</div></div></div>'
    )


def _gate_badge(n: int) -> str:
    """Render the Re-architecture Gate badge — informational, separate from the score.
    n == 0 -> green 'no blockers'; n > 0 -> red 'N routes need redesign'."""
    if n <= 0:
        color, bg, txt = "#2ea043", "rgba(46,160,67,.12)", "✓ No re-architecture blockers"
    else:
        color, bg, txt = "#c44", "rgba(204,68,68,.12)", (
            f"⛔ {n} route" + ("s" if n != 1 else "") + " need redesign / approval")
    return (
        '<div style="display:inline-flex;align-items:center;gap:.5rem;margin:.3rem 0 1rem;padding:.5rem .9rem;'
        'background:' + bg + ';border:1px solid ' + color + ';border-radius:999px;'
        'font-family:Poppins,sans-serif;font-size:.82rem;font-weight:600;color:' + color + ';">'
        + H.escape(txt) + '</div>'
    )


def _build_manifest_section(cluster_idx: int, cluster_name: str, manifests: dict) -> str:
    """Build HTML section with embedded manifest files and download buttons."""
    current_files = {k: v for k, v in manifests.items() if k.startswith("current/")}
    gw_files = {k: v for k, v in manifests.items() if k.startswith("target/gateway-api/")}
    alb_files = {k: v for k, v in manifests.items() if k.startswith("target/alb/")}
    # Fallback: old flat target/ structure
    if not gw_files and not alb_files:
        gw_files = {k: v for k, v in manifests.items() if k.startswith("target/")}

    def _file_rows(files: dict, prefix: str) -> str:
        rows = ""
        for fname, content in sorted(files.items()):
            short = fname.replace(prefix, "")
            b64 = base64.b64encode(content.encode()).decode()
            rows += f'<tr><td><code>{H.escape(short)}</code></td><td><a href="data:text/yaml;base64,{b64}" download="{H.escape(short)}">⬇ Download</a></td></tr>'
        return rows

    current_rows = _file_rows(current_files, "current/")
    gw_rows = _file_rows(gw_files, "target/gateway-api/" if any(k.startswith("target/gateway-api/") for k in gw_files) else "target/")
    alb_rows = _file_rows(alb_files, "target/alb/")

    # Combined download for gateway-api
    all_gw = ""
    for fname, content in sorted(gw_files.items()):
        short = fname.split("/")[-1]
        all_gw += f"---\n# Source: {short}\n{content}\n"
    gw_b64 = base64.b64encode(all_gw.encode()).decode() if all_gw else ""

    # Combined download for alb
    all_alb = ""
    for fname, content in sorted(alb_files.items()):
        short = fname.split("/")[-1]
        all_alb += f"---\n# Source: {short}\n{content}\n"
    alb_b64 = base64.b64encode(all_alb.encode()).decode() if all_alb else ""

    gw_btn = f'<a href="data:text/yaml;base64,{gw_b64}" download="{H.escape(cluster_name)}-gateway-api-manifests.yaml" style="display:inline-block;margin:.5rem .5rem .5rem 0;padding:8px 16px;background:var(--accent);color:#fff;border-radius:var(--radius);text-decoration:none;font-family:Poppins,sans-serif;font-size:.8rem;font-weight:500;">⬇ Gateway API Manifests</a>' if gw_b64 else ""
    alb_btn = f'<a href="data:text/yaml;base64,{alb_b64}" download="{H.escape(cluster_name)}-alb-manifests.yaml" style="display:inline-block;margin:.5rem .5rem .5rem 0;padding:8px 16px;background:#2563eb;color:#fff;border-radius:var(--radius);text-decoration:none;font-family:Poppins,sans-serif;font-size:.8rem;font-weight:500;">⬇ ALB Controller Manifests</a>' if alb_b64 else ""

    alb_section = ""
    if alb_rows:
        alb_section = f'''<h3>Target: ALB Controller</h3>
<div class='table-wrap'><table><thead><tr><th>File</th><th>Action</th></tr></thead><tbody>{alb_rows}</tbody></table></div>'''

    return f'''<details class="section" data-section="export-materials" id="c{cluster_idx}-export-materials" open>
<summary><h2>Export Materials</h2><span class="toggle">▼</span></summary>
<div class="section-body">
<p style="font-size:.9rem;color:var(--text2);margin-bottom:1rem;">Ready-to-apply YAML manifests generated from the assessment. Review before applying.</p>
{gw_btn}{alb_btn}
<h3>Current Ingress (backup)</h3>
{"<div class='table-wrap'><table><thead><tr><th>File</th><th>Action</th></tr></thead><tbody>" + current_rows + "</tbody></table></div>" if current_rows else "<p style='color:var(--text2);font-size:.85rem;'>No Ingress resources to export.</p>"}
<h3>Target: Gateway API</h3>
{"<div class='table-wrap'><table><thead><tr><th>File</th><th>Action</th></tr></thead><tbody>" + gw_rows + "</tbody></table></div>" if gw_rows else "<p style='color:var(--text2);font-size:.85rem;'>No Gateway API manifests generated.</p>"}
{alb_section}
<blockquote>Apply Gateway API manifests in order: <code>kubectl apply -f 00-gateway-api-crds.yaml</code> then <code>01-</code>, <code>02-</code>, etc.<br>Apply ALB manifests: <code>kubectl apply -f target/alb/</code></blockquote>
</div>
</details>'''


def _manifest_buttons(cluster_name: str, manifests: dict) -> dict:
    """Build inline download buttons for [[DL:*]] placeholders used in the report body.
    Each combines that option's manifest files into one downloadable YAML."""
    def combine(prefix: str) -> str:
        out = ""
        for fname, content in sorted(manifests.items()):
            if fname.startswith(prefix):
                out += f"---\n# Source: {fname.split('/')[-1]}\n{content}\n"
        return base64.b64encode(out.encode()).decode() if out else ""

    def btn(label: str, b64: str, fn: str, color: str) -> str:
        return (f'<a href="data:text/yaml;base64,{b64}" download="{H.escape(fn)}" '
                f'style="display:inline-block;margin:.25rem .5rem .25rem 0;padding:7px 14px;'
                f'background:{color};color:#fff;border-radius:var(--radius);text-decoration:none;'
                f'font-family:Poppins,sans-serif;font-size:.78rem;font-weight:500;">⬇ {H.escape(label)}</a>')

    gw = combine("target/gateway-api/") or combine("target/")
    alb = combine("target/alb/")
    cur = combine("current/")
    cn = H.escape(cluster_name)
    out = {}
    if gw:  out["[[DL:gateway-api]]"] = btn("Gateway API routing config", gw, f"{cn}-gateway-api.yaml", "var(--accent)")
    if alb: out["[[DL:alb]]"] = btn("ALB routing config", alb, f"{cn}-alb.yaml", "#2563eb")
    if alb: out["[[DL:atx]]"] = btn("ATX output (ALB) config", alb, f"{cn}-atx-alb.yaml", "#7c3aed")
    if cur: out["[[DL:current]]"] = btn("Current config", cur, f"{cn}-current.yaml", "#475569")
    return out


def build_html(clusters: list[dict]) -> str:
    """Build HTML with cluster dropdown if multiple clusters.
    clusters: list of {"name": str, "body": str, "toc": list, "topology_json": str|None}
    """
    multi = len(clusters) > 1

    # Build cluster selector
    selector_html = ""
    if multi:
        opts = "".join(f'<option value="{i}">{H.escape(c["name"])}</option>' for i, c in enumerate(clusters))
        selector_html = f'<div class="cluster-select"><label>Cluster</label><select id="cluster-sel" onchange="switchCluster(this.value)">{opts}</select></div>'

    # Build nav links from first cluster's TOC (structure is same for all)
    nav_links = ""
    toc = clusters[0]["toc"]
    for group_id, group_label, slugs in NAV_SECTIONS:
        nav_links += f'<div class="nav-section">{H.escape(group_label)}</div>\n'
        if group_id == "references":
            nav_links += '<a href="#export-materials">Export Materials</a>\n'
        topo_added = False
        for slug, title in toc:
            if slug in slugs or any(slug.startswith(s) for s in slugs):
                if group_id == "overview" and not topo_added and clusters[0].get("topology_json"):
                    nav_links += '<a href="#c0-topo-wrap">3D Routing Diagram</a>\n'
                    topo_added = True
                nav_links += f'<a href="#{slug}">{H.escape(strip_bold(title))}</a>\n'

    # Build per-cluster content divs
    cluster_divs = ""
    topo_data_array = []
    for i, c in enumerate(clusters):
        display = "block" if i == 0 else "none"
        topo_html = ""
        if c["topology_json"]:
            topo_html = f'<details class="section" open id="c{i}-topo-wrap" data-section="topo-wrap"><summary><h2>3D Routing Diagram</h2><span class="toggle">▾</span></summary><div class="section-body"><p class="hint">Drag to orbit · Scroll to zoom · Click a node for details <button id=\"anim-{i}\" style=\"margin-left:10px;padding:2px 10px;background:#13233f;color:#9fd0ff;border:1px solid #2c4a6e;border-radius:12px;cursor:pointer;font-size:.72rem\">▶ Animate</button></p><div id="topo-{i}" class="topo-canvas" style="width:100%;height:520px;border-radius:8px;overflow:hidden;border:1px solid var(--border);background:#0a0e14;"></div><div class="topo-info"></div><div class="topo-legend"><span><span class="dot" style="background:#8b949e"></span> Node · server</span><span><span class="dot" style="background:#ff9900"></span> Controller · hub+ring</span><span><span class="dot" style="background:#58a6ff"></span> Ingress · gateway portal</span><span><span class="dot" style="background:#2ea043"></span> Service · K8s hex + pods</span><span><span class="dot" style="background:#bc8cff"></span> Gateway API · portal</span><span><span class=\"dot\" style=\"background:#58a6ff\"></span> ━ Ingress→Service route (bold)</span></div></div></details>'
            topo_data_array.append(c["topology_json"])
        else:
            topo_data_array.append("null")

        # Build manifest export section
        manifest_html = ""
        if c.get("manifests"):
            manifest_html = _build_manifest_section(i, c["name"], c["manifests"])

        # substitute [[DL:*]] download-button placeholders in the body
        body = c["body"]
        for tok, html in _manifest_buttons(c["name"], c.get("manifests") or {}).items():
            body = body.replace(tok, html)
        body = re.sub(r"\[\[DL:[a-z-]+\]\]", "", body)  # strip any unmatched placeholders

        # substitute [[SCORE:nn:LABEL]] headline gauge (Migration Difficulty Score)
        body = re.sub(r"\[\[SCORE:(\d{1,3}):([^\]]+)\]\]",
                      lambda m: _score_badge(int(m.group(1)), m.group(2).strip()), body)
        # substitute [[GATE:n]] re-architecture gate badge (informational)
        body = re.sub(r"\[\[GATE:(\d{1,3})\]\]", lambda m: _gate_badge(int(m.group(1))), body)

        # place 3D Routing Diagram BEFORE the first content section
        # flow: cluster info table -> 3D diagram -> difficulty score -> executive summary
        if topo_html:
            marker = '<details class="section"'
            pos = body.find(marker)
            if pos != -1:
                body = body[:pos] + topo_html + "\n" + body[pos:]
            else:
                body = topo_html + "\n" + body

        # place Export Materials just before the AWS Reference Links section (References group order)
        if manifest_html:
            marker = f'<details class="section" open id="c{i}-aws-reference-links"'
            pos = body.find(marker)
            if pos != -1:
                body = body[:pos] + manifest_html + "\n" + body[pos:]
            else:
                body = body + "\n" + manifest_html

        cluster_divs += f'<div class="cluster-panel" id="cluster-{i}" style="display:{display}">\n{body}\n</div>\n'

    # Topology JS data
    topo_js_array = "[" + ",".join(topo_data_array) + "]"

    # Manifests JS data
    manifests_data = []
    for c in clusters:
        manifests_data.append(json.dumps(c.get("manifests") or {}, ensure_ascii=False))
    manifests_js = "[" + ",".join(manifests_data) + "]"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ingress Assessment &amp; Migration</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@500;600&family=Lora:wght@400;500&display=swap" rel="stylesheet">
<style>{CSS}
.cluster-select{{padding:.8rem 1rem;border-bottom:1px solid rgba(255,255,255,.1);margin-bottom:.3rem}}
.cluster-select label{{font-family:'Poppins',sans-serif;font-size:.6rem;text-transform:uppercase;letter-spacing:.1em;color:rgba(255,255,255,.4);display:block;margin-bottom:.4rem}}
.cluster-select select{{width:100%;background:#1a1a2e;color:#fff;border:1px solid rgba(255,255,255,.25);border-radius:6px;padding:8px 10px;font-family:'Poppins',sans-serif;font-size:.85rem;font-weight:600;cursor:pointer;appearance:none;-webkit-appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23fff' d='M6 8L1 3h10z'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 10px center}}
.cluster-select select:hover{{border-color:var(--accent)}}
.cluster-select select:focus{{outline:none;border-color:var(--accent);box-shadow:0 0 0 2px rgba(217,119,87,.3)}}
.cluster-select select option{{background:#1a1a2e;color:#fff;padding:6px}}
.topo-canvas{{width:100%;height:520px}}
</style>
</head>
<body>
<div class="layout">
<nav class="nav">
  <div class="nav-title">Ingress Assessment<br>&amp; Migration<div class="nav-sub">EKS Cluster Report</div></div>
{selector_html}
{nav_links}
  <div class="nav-bottom"><button class="theme-toggle" onclick="toggleTheme()" id="theme-btn">🌙 Dark</button></div>
</nav>
<main class="content">
{cluster_divs}
<footer style="margin-top:2rem;padding-top:1rem;border-top:1px solid var(--border);color:var(--text2);">
Generated by EKS Ingress Migration Skill
</footer>
</main>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/shaders/CopyShader.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/shaders/LuminosityHighPassShader.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/postprocessing/EffectComposer.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/postprocessing/RenderPass.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/postprocessing/ShaderPass.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/postprocessing/MaskPass.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/postprocessing/UnrealBloomPass.js"></script>
<script>
const TOPOS={topo_js_array};
const MANIFESTS={manifests_js};
let activeCluster=0;
function switchCluster(idx){{
  activeCluster=parseInt(idx);
  document.querySelectorAll('.cluster-panel').forEach((p,i)=>p.style.display=i==activeCluster?'block':'none');
  initTopo(activeCluster);
  setupObserver();
}}
function getActivePanel(){{return document.getElementById('cluster-'+activeCluster);}}
function setupObserver(){{
  const links=document.querySelectorAll('.nav a[href^="#"]');
  links.forEach(l=>l.classList.remove('active'));
  const panel=getActivePanel();if(!panel)return;
  if(window._navObs)window._navObs.disconnect();
  window._navObs=new IntersectionObserver(entries=>{{
    entries.forEach(e=>{{if(e.isIntersecting){{
      const sec=e.target.getAttribute('data-section');
      if(!sec)return;
      links.forEach(l=>l.classList.remove('active'));
      const a=document.querySelector('.nav a[href="#'+sec+'"]');
      if(a)a.classList.add('active');
    }}}});
  }},{{threshold:0.3}});
  panel.querySelectorAll('[data-section]').forEach(el=>window._navObs.observe(el));
}}
function initTopo(idx){{
  const T=TOPOS[idx];if(!T)return;
  const cid='topo-'+idx,C=document.getElementById(cid);
  if(!C||C.dataset.init)return;C.dataset.init='1';
  const info=C.parentElement.querySelector('.topo-info');
  const W=C.clientWidth,HH=C.clientHeight;
  const scene=new THREE.Scene();scene.background=new THREE.Color(0x05070d);
  const cam=new THREE.PerspectiveCamera(52,W/HH,0.1,2000);cam.position.set(9,10,36);
  const R=new THREE.WebGLRenderer({{antialias:true}});R.setSize(W,HH);R.setPixelRatio(Math.min(window.devicePixelRatio,1.5));C.appendChild(R.domElement);
  const ctrl=new THREE.OrbitControls(cam,R.domElement);ctrl.enableDamping=true;ctrl.dampingFactor=0.08;ctrl.autoRotate=false;ctrl.autoRotateSpeed=0.4;ctrl.target.set(-1,0,0);
  scene.fog=new THREE.FogExp2(0x05070d,0.011);
  scene.add(new THREE.AmbientLight(0x9fb4d6,0.42));
  const dl=new THREE.DirectionalLight(0xffffff,0.85);dl.position.set(6,12,8);scene.add(dl);
  const rim=new THREE.DirectionalLight(0x58a6ff,0.5);rim.position.set(-8,-4,-10);scene.add(rim);
  const pl=new THREE.PointLight(0xff9900,0.55,90);pl.position.set(-6,1,6);scene.add(pl);
  {{const sg=new THREE.BufferGeometry(),NS=950,ar=new Float32Array(NS*3);for(let i=0;i<NS*3;i++)ar[i]=(Math.random()-0.5)*260;sg.setAttribute('position',new THREE.BufferAttribute(ar,3));scene.add(new THREE.Points(sg,new THREE.PointsMaterial({{color:0x6f93c4,size:0.32,transparent:true,opacity:0.65}})));}}
  const meshes=[],FLOAT=[],LABELS=[],LINKS=[],TUBES=[];
  function rnd(i,s){{const v=Math.sin(i*127.1+s*311.7)*43758.5453;return v-Math.floor(v);}}
  function emat(col,e){{return new THREE.MeshStandardMaterial({{color:col,roughness:0.32,metalness:0.62,emissive:col,emissiveIntensity:e==null?0.3:e}});}}
  // ---- entity-iconic builders (professional theme) ----
  function buildNode(sz,col){{const g=new THREE.Group();const body=new THREE.Mesh(new THREE.BoxGeometry(sz*1.9,sz*1.15,sz*1.25),emat(col,0.16));g.add(body);for(let k=0;k<3;k++){{const s=new THREE.Mesh(new THREE.BoxGeometry(sz*1.5,sz*0.12,sz*0.07),emat(0x394150,0.05));s.position.set(0,sz*0.32-k*sz*0.32,sz*0.64);g.add(s);}}const led=new THREE.Mesh(new THREE.SphereGeometry(sz*0.1,10,10),new THREE.MeshStandardMaterial({{color:0x2ea043,emissive:0x2ea043,emissiveIntensity:1.4}}));led.position.set(sz*0.72,sz*0.42,sz*0.64);g.add(led);return g;}}
  function buildController(sz,col){{const g=new THREE.Group();g.add(new THREE.Mesh(new THREE.IcosahedronGeometry(sz*0.6,1),emat(col,0.55)));const r1=new THREE.Mesh(new THREE.TorusGeometry(sz*1.05,sz*0.07,16,48),emat(col,0.6));r1.rotation.x=Math.PI/2.3;g.add(r1);const r2=new THREE.Mesh(new THREE.TorusGeometry(sz*1.05,sz*0.05,16,48),emat(0xffd27f,0.5));r2.rotation.x=Math.PI/2.3;r2.rotation.y=Math.PI/3;g.add(r2);return g;}}
  function buildIngress(sz,col){{const g=new THREE.Group();const ring=new THREE.Mesh(new THREE.TorusGeometry(sz*0.95,sz*0.13,18,40),emat(col,0.5));ring.rotation.y=Math.PI/2;g.add(ring);const ar=new THREE.Mesh(new THREE.ConeGeometry(sz*0.3,sz*0.7,20),emat(0x9fd0ff,0.65));ar.rotation.z=-Math.PI/2;ar.position.x=sz*0.25;g.add(ar);return g;}}
  function buildService(sz,col){{const g=new THREE.Group();const hex=new THREE.Mesh(new THREE.CylinderGeometry(sz*0.82,sz*0.82,sz*0.45,6),emat(col,0.32));hex.rotation.x=Math.PI/2;g.add(hex);for(let k=0;k<3;k++){{const a=k/3*Math.PI*2;const p=new THREE.Mesh(new THREE.SphereGeometry(sz*0.17,12,12),emat(0x7ee2a8,0.5));p.position.set(Math.cos(a)*sz*0.5,Math.sin(a)*sz*0.5,-sz*0.5);g.add(p);}}return g;}}
  function buildGateway(sz,col){{const g=new THREE.Group();const r1=new THREE.Mesh(new THREE.TorusGeometry(sz*1.0,sz*0.11,18,44),emat(col,0.5));r1.rotation.y=Math.PI/2;g.add(r1);const r2=new THREE.Mesh(new THREE.TorusGeometry(sz*0.62,sz*0.09,16,40),emat(0xd2a8ff,0.6));r2.rotation.y=Math.PI/2;g.add(r2);return g;}}
  function buildRoute(sz,col){{const g=new THREE.Group();const c=new THREE.Mesh(new THREE.ConeGeometry(sz*0.5,sz*1.1,18),emat(col,0.55));c.rotation.z=-Math.PI/2;g.add(c);return g;}}
  function mkN(x,y,z,col,kind,sz,ud){{let g;if(kind==='node')g=buildNode(sz,col);else if(kind==='controller')g=buildController(sz,col);else if(kind==='ingress')g=buildIngress(sz,col);else if(kind==='service')g=buildService(sz,col);else if(kind==='gateway')g=buildGateway(sz,col);else g=buildRoute(sz,col);g.position.set(x,y,z);g.userData=ud;scene.add(g);meshes.push(g);FLOAT.push({{m:g,b:g.position.clone(),p:Math.random()*6.283,s:0.003+Math.random()*0.004,kind}});return g;}}
  function pipe(a,b,col,op){{const ln=new THREE.Line(new THREE.BufferGeometry().setFromPoints([a.position.clone(),b.position.clone()]),new THREE.LineBasicMaterial({{color:col,transparent:true,opacity:op==null?0.45:op,blending:THREE.AdditiveBlending}}));scene.add(ln);LINKS.push({{a,b,line:ln}});}}
  function updTube(o){{const a=o.a.position,b=o.b.position,d=new THREE.Vector3().subVectors(b,a),L=d.length();o.m.position.copy(a).addScaledVector(d,0.5);o.m.scale.set(1,L,1);o.m.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),d.clone().normalize());}}
  function tube(a,b,col,r){{const m=new THREE.Mesh(new THREE.CylinderGeometry(r,r,1,12),new THREE.MeshStandardMaterial({{color:col,emissive:col,emissiveIntensity:0.8,transparent:true,opacity:0.95,roughness:0.3,metalness:0.4}}));scene.add(m);const o={{a,b,m}};TUBES.push(o);updTube(o);return m;}}
  function txt(m,s,col){{const c=document.createElement('canvas');c.width=512;c.height=64;const x=c.getContext('2d');x.font='bold 24px -apple-system,sans-serif';x.fillStyle=col||'#e6edf3';x.textAlign='center';x.fillText(s.length>30?s.slice(0,27)+'...':s,256,40);const t=new THREE.CanvasTexture(c);const sp=new THREE.Sprite(new THREE.SpriteMaterial({{map:t,transparent:true,depthWrite:false}}));sp.position.copy(m.position);sp.position.y+=1.0;sp.scale.set(3,0.38,1);scene.add(sp);LABELS.push({{sp,m}});}}
  const nodes=T.nodes||[],ctrls_d=T.controllers||[],ings=T.ingresses||[],svcs=T.services||[],gw=T.gatewayApi||{{}};
  const LX_N=-14,LX_C=-8,LX_I=1,LX_S=10;
  // group ingress+service by namespace into Z-plane "lanes" so route tubes stay local (no crossing)
  const nsList=[...new Set([...ings.map(o=>o.namespace),...svcs.map(o=>o.namespace)])];
  const ZG=Math.max(8,Math.min(13,42/Math.max(1,nsList.length)));const nsZ={{}};nsList.forEach((ns,li)=>nsZ[ns]=(li-(nsList.length-1)/2)*ZG);
  // floating namespace label per lane
  nsList.forEach(ns=>{{const z=nsZ[ns];const lc=document.createElement('canvas');lc.width=512;lc.height=64;const lx=lc.getContext('2d');lx.font='bold 30px -apple-system,sans-serif';lx.fillStyle='#cdd6e0';lx.textAlign='center';lx.fillText('namespace: '+ns,256,42);const ls=new THREE.Sprite(new THREE.SpriteMaterial({{map:new THREE.CanvasTexture(lc),transparent:true,opacity:0.9,depthWrite:false}}));ls.position.set((LX_I+LX_S)/2,8,z);ls.scale.set(7.5,0.95,1);scene.add(ls);}});
  // nodes: clean left spine (z=0)
  const nN=[];nodes.forEach((n,i)=>{{const y=(i-(nodes.length-1)/2)*2.4;const m=mkN(LX_N,y,0,0x8b949e,'node',0.5,{{type:'Node',name:n.name,instanceId:n.instanceId,instanceType:n.instanceType,zone:n.zone}});txt(m,n.instanceId||n.name,'#8b949e');nN.push(m);}});
  const cN=[];ctrls_d.forEach((c,i)=>{{const y=(i-(ctrls_d.length-1)/2)*3.2;const m=mkN(LX_C,y,0,0xff9900,'controller',0.62,{{type:'Controller',...c}});txt(m,c.displayName||c.name,'#ff9900');cN.push(m);nN.forEach(n=>pipe(n,m,0x8b949e,0.12));}});
  // ingresses grouped per namespace lane
  const iMesh={{}},iByNs={{}};ings.forEach(o=>{{(iByNs[o.namespace]=iByNs[o.namespace]||[]).push(o);}});
  nsList.forEach(ns=>{{const arr=iByNs[ns]||[];arr.forEach((ing,j)=>{{const y=(j-(arr.length-1)/2)*2.2;const m=mkN(LX_I,y,nsZ[ns],0x58a6ff,'ingress',0.5,{{type:'Ingress',...ing}});txt(m,(ing.hosts&&ing.hosts[0])||ing.name,'#58a6ff');iMesh[ns+'/'+ing.name]=m;const cn=cN.find(c=>c.userData.name===ing.controller);if(cn)pipe(cn,m,0xff9900,0.32);else console.warn('Ingress '+(ing.name||'?')+' references unknown controller "'+ing.controller+'" — not linked');}});}});
  // services grouped per namespace lane
  const sN={{}},sByNs={{}};svcs.forEach(o=>{{(sByNs[o.namespace]=sByNs[o.namespace]||[]).push(o);}});
  nsList.forEach(ns=>{{const arr=sByNs[ns]||[];arr.forEach((s,j)=>{{const y=(j-(arr.length-1)/2)*2.0;const m=mkN(LX_S,y,nsZ[ns],0x2ea043,'service',0.55,{{type:'Service',...s}});txt(m,s.name,'#2ea043');sN[ns+'/'+s.name]=m;}});}});
  // bold ingress->service route tubes (each stays within its namespace plane)
  ings.forEach(ing=>{{const im=iMesh[ing.namespace+'/'+ing.name];if(!im)return;(ing.paths||[]).forEach(p=>{{const k=(ing.namespace||'default')+'/'+p.backend;if(sN[k])tube(im,sN[k],0x58a6ff,0.08);}});}});
  (gw.gateways||[]).forEach((g,i)=>{{const m=mkN(LX_I,-((ings.length)/2+3+i*2.5),6,0xbc8cff,'gateway',0.6,{{type:'Gateway',...g}});txt(m,g.name||'gateway','#bc8cff');}});
  (gw.httpRoutes||[]).forEach((r,i)=>{{mkN(LX_S-2,-((ings.length)/2+3+i*2),6,0xd2a8ff,'route',0.4,{{type:'HTTPRoute',...r}});}});
  let composer=null;if(THREE.EffectComposer&&THREE.UnrealBloomPass&&THREE.RenderPass){{composer=new THREE.EffectComposer(R);composer.addPass(new THREE.RenderPass(scene,cam));composer.addPass(new THREE.UnrealBloomPass(new THREE.Vector2(W,HH),0.85,0.55,0.55));}}
  const rc=new THREE.Raycaster(),mse=new THREE.Vector2();
  R.domElement.addEventListener('click',e=>{{const rect=R.domElement.getBoundingClientRect();mse.x=((e.clientX-rect.left)/rect.width)*2-1;mse.y=-((e.clientY-rect.top)/rect.height)*2+1;rc.setFromCamera(mse,cam);const h=rc.intersectObjects(meshes,true);if(h.length&&info){{let o=h[0].object;while(o&&!(o.userData&&o.userData.type))o=o.parent;if(!o)return;const d=o.userData;let t='<strong>'+d.type+':</strong> '+(d.displayName||d.name||'');if(d.instanceId)t+=' · '+d.instanceId;if(d.instanceType)t+=' · '+d.instanceType;if(d.zone)t+=' · '+d.zone;if(d.namespace)t+=' <em>('+d.namespace+')</em>';if(d.version)t+=' · v'+d.version;if(d.hosts)t+=' · '+d.hosts.join(', ');if(d.ports)t+=' · ports: '+d.ports.join(', ');if(d.paths)t+=' · '+d.paths.length+' path(s)';info.innerHTML=t;}}}});
  let animating=false,dirty=true;const clock=new THREE.Clock();
  ctrl.addEventListener('change',()=>{{dirty=true;}});
  const abtn=document.getElementById('anim-'+idx);if(abtn)abtn.onclick=()=>{{animating=!animating;ctrl.autoRotate=animating;abtn.textContent=animating?'⏸ Pause motion':'▶ Animate';clock.start();dirty=true;}};
  function frame(){{requestAnimationFrame(frame);
    if(animating){{const t=clock.getElapsedTime();for(const o of FLOAT){{o.m.position.set(o.b.x+Math.sin(t*0.5+o.p)*0.35,o.b.y+Math.sin(t*0.8+o.p)*0.5,o.b.z+Math.cos(t*0.45+o.p)*0.35);o.m.rotation.y+=o.s;if(o.kind!=='node')o.m.rotation.x+=o.s*0.35;}}for(const l of LABELS)l.sp.position.set(l.m.position.x,l.m.position.y+1.0,l.m.position.z);for(const L of LINKS)L.line.geometry.setFromPoints([L.a.position,L.b.position]);for(const o of TUBES)updTube(o);dirty=true;}}
    ctrl.update();
    if(dirty){{dirty=false;if(composer)composer.render();else R.render(scene,cam);}}
  }}frame();
  window.addEventListener('resize',()=>{{const w=C.clientWidth,h=C.clientHeight;cam.aspect=w/h;cam.updateProjectionMatrix();R.setSize(w,h);if(composer)composer.setSize(w,h);dirty=true;}});
}}
function toggleTheme(){{
  const h=document.documentElement,b=document.getElementById('theme-btn');
  if(h.getAttribute('data-theme')==='dark'){{h.removeAttribute('data-theme');b.textContent='🌙 Dark';localStorage.setItem('theme','light');}}
  else{{h.setAttribute('data-theme','dark');b.textContent='☀️ Light';localStorage.setItem('theme','dark');}}
}}
(function(){{
  const s=localStorage.getItem('theme');
  if(s==='dark'||(!s&&window.matchMedia('(prefers-color-scheme:dark)').matches)){{
    document.documentElement.setAttribute('data-theme','dark');
    document.getElementById('theme-btn').textContent='☀️ Light';
  }}
  initTopo(0);
  // Nav click: find matching section in active cluster panel
  document.querySelectorAll('.nav a[href^="#"]').forEach(link=>{{
    link.addEventListener('click',function(ev){{
      ev.preventDefault();
      const section=this.getAttribute('href').slice(1);
      const panel=getActivePanel();if(!panel)return;
      const el=panel.querySelector('[data-section="'+section+'"]');
      if(!el)return;
      if(el.tagName==='DETAILS'&&!el.open)el.open=true;
      const parent=el.closest('details');
      if(parent&&!parent.open)parent.open=true;
      setTimeout(()=>el.scrollIntoView({{behavior:'smooth',block:'start'}}),50);
    }});
  }});
  // In-content anchor links (e.g. "see blocker"): resolve by element id, open its <details>, scroll
  document.querySelectorAll('.content a[href^="#"]').forEach(link=>{{
    link.addEventListener('click',function(ev){{
      const id=this.getAttribute('href').slice(1);if(!id)return;
      const el=document.getElementById(id);if(!el)return;
      ev.preventDefault();
      let n=el;while(n){{if(n.tagName==='DETAILS'&&!n.open)n.open=true;n=n.parentElement;}}
      setTimeout(()=>el.scrollIntoView({{behavior:'smooth',block:'start'}}),60);
    }});
  }});
  setupObserver();
}})();
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Convert MD report(s) to HTML dashboard")
    parser.add_argument("reports", nargs="+", help="Path(s) to markdown report(s)")
    parser.add_argument("--topology", nargs="*", help="Path(s) to topology JSON file(s), one per report")
    parser.add_argument("--manifests", nargs="*", help="Path(s) to manifest directories, one per report")
    parser.add_argument("-o", "--output", help="Output HTML file path")
    args = parser.parse_args()

    topos = args.topology or []
    manifest_dirs = args.manifests or []
    clusters = []

    for i, report_path in enumerate(args.reports):
        md_path = Path(report_path)
        if not md_path.exists():
            print(f"File not found: {md_path}"); sys.exit(1)

        md_text = md_path.read_text(encoding="utf-8")
        body, toc = convert_md(md_text, id_prefix=f"c{i}-")

        # Extract cluster name: prefer topology JSON "cluster" field, fallback to filename
        name = None
        topology_json = None
        if i < len(topos):
            topo_path = Path(topos[i])
            if topo_path.exists():
                topology_json = topo_path.read_text(encoding="utf-8").strip()
                try:
                    name = json.loads(topology_json).get("cluster")
                except (json.JSONDecodeError, AttributeError):
                    pass
                print(f"📊 Topology loaded: {topo_path}")
        if not name:
            # Strip "EKS-Ingress-Migration-" prefix and date suffix (YYYY-MM-DD-HHMM)
            stem = md_path.stem.replace("EKS-Ingress-Migration-", "")
            name = re.sub(r"-\d{4}-\d{2}-\d{2}-\d{4}$", "", stem)

        # Load manifests
        manifests = {}
        if i < len(manifest_dirs):
            mdir = Path(manifest_dirs[i])
            if mdir.is_dir():
                for sub in ["current", "target"]:
                    sub_path = mdir / sub
                    if sub_path.is_dir():
                        for f in sorted(sub_path.rglob("*.yaml")):
                            manifests[f.relative_to(mdir).as_posix()] = f.read_text(encoding="utf-8")
                print(f"📦 Manifests loaded: {mdir} ({len(manifests)} files)")

        clusters.append({"name": name, "body": body, "toc": toc, "topology_json": topology_json, "manifests": manifests})

    html_out = build_html(clusters)
    out_path = Path(args.output) if args.output else Path(args.reports[0]).with_suffix(".html")
    out_path.write_text(html_out, encoding="utf-8")
    print(f"✅ HTML report: {out_path} ({len(clusters)} cluster(s))")


if __name__ == "__main__":
    main()
