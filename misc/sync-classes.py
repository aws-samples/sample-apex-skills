#!/usr/bin/env python3
"""Copy the shared class files in classes/ into each member skill.

A skill joins classes through its own SKILL.md frontmatter:

    metadata:
      apex-classes: "service script"

(a space-separated list of leaf classes, the folder names under classes/;
listing a class beside its own parent is refused). A skill with no such
line is not a member, and this script never writes into it. For each
member skill the script:

  1. resolves the skill's classes parents first, each class once (the C3
     order, reversed: "service script" gives apex-base, platform,
     operator, script, service);
  2. fails when two classes in that chain give the same rule id or the same
     target path;
  3. copies each class's rules.md into one marker block in SKILL.md, right
     after the frontmatter, between <!-- APEX_CLASSES_START --> and
     <!-- APEX_CLASSES_END -->;
  4. copies classes/<c>/references/<f>.md to references/<c>-<f>.md and
     classes/<c>/scripts/<f> to scripts/<c_with_underscores>_<f> (a file that
     already carries its class prefix keeps its name);
  5. rewrites each import of a class file in a copied script to the flat
     name (Python `import` and `from ... import`; shell `source` and `.` at
     the start of a line or after `&&`, `;` or `then`), and fails on a
     dotted or relative import of a class module, a dynamic-import call
     whose argument is not a constant or names a class module, a Python
     string literal naming a class .py file (docstrings excepted), a
     sourced file with a computed name, and a shell line whose code part
     (comments excepted) still names a class .sh file by its old name, so
     a `source` after `||`, `|`, `&`, `do`, `elif`, `while` or `!`, inside
     `{ }`, `( )` or `$( )`, or any other mention, fails the sync; a quoted
     `source` inside an echo also refuses the sync (it fails closed), and
     heredoc or comment text naming `source helper.sh` is rewritten;
  6. heads each copy "generated from classes/<c>/<f>, do not edit";
  7. fails when copied class text points to the apex skill (a path into
     skills/apex/ or ../apex/, an `apex/<name>` path, or a /apex or $apex
     command). A rule id such as apex.mcp-first is a label and passes, and
     so does naming the skill.

A class script declares its packages in itself (PEP 723 `# /// script`
metadata for Python, a `# requires: <command> ...` line for shell), so the
copy carries the declaration with it. Copies are written without the
execute bit; run a class script with `bash` or `python3`. checks/, evals/
and hooks/ are not copied: CI runs them from classes/.

Usage (from anywhere; paths are relative to the repo root):

    python3 misc/sync-classes.py           # write the copies
    python3 misc/sync-classes.py --check   # write nothing; exit 1 on any difference

--check computes every expected file in memory, compares it with the files
on disk, prints each difference and exits 1 on any. Every refusal (steps 2,
5 and 7, an unreadable class file or SKILL.md) stops both modes, and write
mode runs every check before it writes anything, so a refusal leaves the
tree as it was; an OS error while writing can stop it part way. A class references/ folder, or a folder under it, that
os.walk cannot read is skipped, not refused. Write mode overwrites any file
at a copy's target path; --check, which CI runs, is the guard against a
skill-owned file there. Symlinks are followed on both sides; the repo has
none. --root points the script at another tree (the tests use it).

What --check does not find (the orphan scan was cut from the design): a copy
whose class file was removed or renamed, a stray generated file at the top
level of a member's references/ or scripts/, and the copies and marker block
left in a skill that drops metadata.apex-classes or sets it empty. A
generated file one folder down is still reported, because copies are always
flat, so a nested one is wrong whatever its class; a top-level one could be
the copy of a removed class, which only the orphan scan would tell. With no
member skill, --check reads class.yaml and each skill's frontmatter; class
rules, references and scripts are not read.

Requires PyYAML (pip install 'pyyaml>=6,<7').
"""

import argparse
import ast
import difflib
import io
import os
import re
import shlex
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import yaml
    from safe_frontmatter import FrontmatterError, load_frontmatter
except ImportError as exc:  # pragma: no cover - environment problem
    sys.stderr.write(
        f"sync-classes: cannot import a dependency ({exc}); "
        "install it with: pip install 'pyyaml>=6,<7'\n"
    )
    sys.exit(2)

START = "<!-- APEX_CLASSES_START -->"
END = "<!-- APEX_CLASSES_END -->"

RULE_LINE = re.compile(r"^- \*\*([^*\s]+)\*\*:")

# A pointer to the apex skill: a path into its folder or its command.
APEX_POINTERS = [
    (re.compile(r"skills/apex(?![\w-])"), "a path into skills/apex/"),
    (re.compile(r"\.\./apex(?![\w-])"), "a path into ../apex/"),
    (re.compile(r"(?<![\w./$-])apex/(?=[\w.])"), "a path into apex/"),
    (re.compile(r"(?<![\w./$-])[/$]apex(?![\w-])"), "the /apex or $apex command"),
]

DYNAMIC_IMPORT_CALLS = {
    "import_module", "__import__", "spec_from_file_location", "run_path",
    "run_module", "load_source", "SourceFileLoader",
}

# A `source` or `.` at the start of a line or after `&&`, `;` or `then`;
# the sourced word starts at the match end.
SHELL_SOURCE = re.compile(r"(?:^|&&|;|\bthen\b)\s*(?:source|\.)\s+(?=\S)")


class SyncError(Exception):
    """A refusal: the inputs cannot be synced as they are."""


def header_line(src_rel, kind):
    text = f"generated from {src_rel}, do not edit"
    return f"<!-- {text} -->" if kind == "md" else f"# {text}"


# ---------------------------------------------------------------- classes


def load_classes(root):
    """Read every classes/<c>/class.yaml; return {name: parents}."""
    cdir = os.path.join(root, "classes")
    if not os.path.isdir(cdir):
        raise SyncError("classes/ not found")
    classes = {}
    for name in sorted(os.listdir(cdir)):
        path = os.path.join(cdir, name)
        if not os.path.isdir(path) or name.startswith("."):
            continue
        rel = f"classes/{name}/class.yaml"
        ypath = os.path.join(path, "class.yaml")
        if not os.path.isfile(ypath):
            raise SyncError(f"{rel}: missing")
        try:
            with open(ypath, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            raise SyncError(f"{rel}: unreadable ({exc.__class__.__name__})") from exc
        if not isinstance(data, dict):
            raise SyncError(f"{rel}: not a mapping")
        if data.get("name") != name:
            raise SyncError(f"{rel}: name must be {name!r}, found {data.get('name')!r}")
        parents = data.get("parents")
        if not isinstance(parents, list) or not all(isinstance(p, str) for p in parents):
            raise SyncError(f"{rel}: parents must be a list of class names")
        classes[name] = parents
    for name, parents in classes.items():
        for p in parents:
            if p not in classes:
                raise SyncError(f"classes/{name}/class.yaml: parent {p!r} is not under classes/")
    return classes


def linearize(name, classes, stack=()):
    """C3 linearization, most specific first."""
    if name in stack:
        raise SyncError("class cycle: " + " -> ".join(stack + (name,)))
    parents = classes[name]
    return [name] + c3_merge(
        [linearize(p, classes, stack + (name,)) for p in parents] + [list(parents)], name
    )


def c3_merge(seqs, who):
    seqs = [list(s) for s in seqs if s]
    out = []
    while seqs:
        for seq in seqs:
            head = seq[0]
            if not any(head in s[1:] for s in seqs):
                break
        else:
            raise SyncError(
                f"{who}: the declared class order contradicts the classes' parents "
                "(or a class is listed twice); declare leaf classes only, each once"
            )
        out.append(head)
        seqs = [[x for x in s if x != head] for s in seqs]
        seqs = [s for s in seqs if s]
    return out


def resolve_chain(declared, classes, who):
    """Parents first, each class once."""
    for c in declared:
        if c not in classes:
            raise SyncError(f"{who}: declares class {c!r}, which is not under classes/")
    for c in declared:
        for d in declared:
            if c in linearize(d, classes)[1:]:
                raise SyncError(
                    f"{who}: declares {c!r} beside {d!r}, which already has it as a parent; "
                    "declare leaf classes only"
                )
    lin = [who] + c3_merge([linearize(c, classes) for c in declared] + [list(declared)], who)
    return list(reversed(lin[1:]))


# ----------------------------------------------------------------- skills


def split_frontmatter(text):
    """Return (frontmatter text, index where the body starts) or (None, 0)."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip() != "---":
        return None, 0
    pos = len(lines[0])
    for line in lines[1:]:
        if line.rstrip() == "---":
            return text[len(lines[0]):pos], pos + len(line)
        pos += len(line)
    return None, 0


def member_skills(root, classes):
    """Return [(skill, declared classes)] for skills that declare classes."""
    sdir = os.path.join(root, "skills")
    members = []
    if not os.path.isdir(sdir):
        return members
    for skill in sorted(os.listdir(sdir)):
        path = os.path.join(sdir, skill, "SKILL.md")
        if not os.path.isfile(path):
            continue
        text = read_text(path)
        fm, _ = split_frontmatter(text)
        if fm is None:
            continue
        try:
            data = load_frontmatter(fm)
        except FrontmatterError as exc:
            raise SyncError(f"skills/{skill}/SKILL.md: {exc}") from exc
        meta = data.get("metadata")
        if isinstance(meta, dict):
            for key in meta:
                if key != "apex-classes" and difflib.get_close_matches(str(key), ["apex-classes"], cutoff=0.8):
                    raise SyncError(
                        f"skills/{skill}/SKILL.md: metadata key {key!r} is not apex-classes; "
                        "fix the spelling, or the skill joins no class"
                    )
        value = meta.get("apex-classes") if isinstance(meta, dict) else None
        if value is None:
            continue
        if not isinstance(value, str):
            raise SyncError(
                f"skills/{skill}/SKILL.md: metadata.apex-classes must be a "
                "space-separated string of class names"
            )
        declared = value.split()
        if declared:
            members.append((skill, declared))
    return members


# ------------------------------------------------------------ class files


def read_text(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        raise SyncError(f"{path}: unreadable ({exc.__class__.__name__})") from exc


def check_apex_pointers(text, src_rel):
    for lineno, line in enumerate(text.splitlines(), 1):
        for pattern, what in APEX_POINTERS:
            if pattern.search(line):
                raise SyncError(
                    f"{src_rel}:{lineno}: copied class text points to the apex skill "
                    f"({what}); name the skill instead of pointing into it"
                )


def class_files(root, cls):
    """Return (rules text or None, [references], [scripts]) for one class."""
    base = os.path.join(root, "classes", cls)
    rules = None
    rpath = os.path.join(base, "rules.md")
    if os.path.isfile(rpath):
        rules = read_text(rpath)
        check_apex_pointers(rules, f"classes/{cls}/rules.md")

    refs = []
    rdir = os.path.join(base, "references")
    for dirpath, dirnames, filenames in os.walk(rdir):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for fname in sorted(filenames):
            if fname.startswith("."):
                continue
            full = os.path.join(dirpath, fname)
            sub = os.path.relpath(full, rdir).replace(os.sep, "/")
            src_rel = f"classes/{cls}/references/{sub}"
            if not fname.endswith(".md"):
                raise SyncError(f"{src_rel}: a class reference must be a .md file")
            flat = sub.replace("/", "-")
            if not flat.startswith(f"{cls}-"):
                flat = f"{cls}-{flat}"
            text = read_text(full)
            check_apex_pointers(text, src_rel)
            refs.append({"src": src_rel, "target": f"references/{flat}", "text": text})

    scripts = []
    sdir = os.path.join(base, "scripts")
    if os.path.isdir(sdir):
        prefix = cls.replace("-", "_") + "_"
        for fname in sorted(os.listdir(sdir)):
            full = os.path.join(sdir, fname)
            src_rel = f"classes/{cls}/scripts/{fname}"
            if fname.startswith(".") or fname == "__pycache__" or fname.endswith(".pyc"):
                continue
            if os.path.isdir(full):
                raise SyncError(f"{src_rel}/: a class scripts/ folder must be flat")
            ext = os.path.splitext(fname)[1]
            if ext not in (".py", ".sh"):
                raise SyncError(f"{src_rel}: a class script must be a .py or .sh file")
            flat = fname if fname.startswith(prefix) else prefix + fname
            text = read_text(full)
            check_apex_pointers(text, src_rel)
            scripts.append({
                "src": src_rel, "target": f"scripts/{flat}", "text": text,
                "kind": ext[1:], "class": cls, "name": fname,
            })
    return rules, refs, scripts


# ------------------------------------------------------- import rewriting


def module_map(cls, classes, scripts_by_class, ext):
    """Class files a script of `cls` may import: {name: flat name}."""
    found = {}
    for c in linearize(cls, classes):
        for s in scripts_by_class.get(c, []):
            if s["kind"] != ext:
                continue
            key = s["name"][:-3] if ext == "py" else s["name"]
            flat = s["target"][len("scripts/"):]
            flat = flat[:-3] if ext == "py" else flat
            if key in found:
                raise SyncError(
                    f"classes/{cls}/scripts: {s['name']} is in two classes of its chain"
                )
            found[key] = flat
    return found


def all_class_modules(root, ext):
    """Every class script name under classes/*/scripts/: {name: class}."""
    names = {}
    cdir = os.path.join(root, "classes")
    for c in sorted(os.listdir(cdir)):
        sdir = os.path.join(cdir, c, "scripts")
        if not os.path.isdir(sdir):
            continue
        for fname in sorted(os.listdir(sdir)):
            if fname.endswith("." + ext):
                names.setdefault(fname[:-3] if ext == "py" else fname, c)
    return names


def docstring_nodes(tree):
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(
                getattr(body[0], "value", None), ast.Constant
            ) and isinstance(body[0].value.value, str):
                out.add(id(body[0].value))
    return out


def unrewritten_imports(text, mods):
    """Names in `mods` (whose flat name differs) still imported by `text`."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    left = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            left += [a.name for a in node.names if a.name.split(".")[0] in mods]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            if node.module.split(".")[0] in mods:
                left.append(node.module)
    return left


def imported_class_modules(text, mods):
    """{name: flat name} for the class modules `text` imports under a new name."""
    tops = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            tops |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            tops.add(node.module.split(".")[0])
    return {m: f for m, f in mods.items() if m in tops and f != m}


def rewrite_python(script, mods, other_class_mods):
    src = script["src"]
    try:
        tree = ast.parse(script["text"], filename=src)
    except SyntaxError as exc:
        raise SyncError(f"{src}:{exc.lineno}: cannot parse ({exc.msg})") from exc
    class_names = set(mods) | set(other_class_mods)
    file_names = {m + ".py" for m in class_names}
    docs = docstring_nodes(tree)
    lines = script["text"].splitlines(keepends=True)

    def refuse(node, why):
        raise SyncError(f"{src}:{node.lineno}: {why}; the sync cannot rewrite it to the flat name")

    edits = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            fname = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if fname in DYNAMIC_IMPORT_CALLS:
                args = list(node.args) + [k.value for k in node.keywords]
                consts = [a.value for a in args if isinstance(a, ast.Constant)]
                if len(consts) != len(args) or any(
                    isinstance(v, str) and (v.split(".")[0] in class_names or os.path.basename(v) in file_names)
                    for v in consts
                ):
                    refuse(node, f"a dynamic import ({fname}) that may load a class file")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            for f in file_names:
                if re.search(r"(?<![\w.])" + re.escape(f) + r"(?!\w)", node.value):
                    refuse(node, f"a path to the class file {f}")
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                refuse(node, "a relative import")
            top = (node.module or "").split(".")[0]
            if top in other_class_mods and top not in mods:
                refuse(node, f"an import of {top}, a class file outside this class's chain")
            if top in mods and mods[top] != top:
                if "." in node.module:
                    refuse(node, f"a dotted import of {node.module}")
                i = node.lineno - 1
                new, n = re.subn(r"(\bfrom\s+)" + re.escape(top) + r"\b", r"\g<1>" + mods[top], lines[i], count=1)
                if n != 1:
                    refuse(node, f"an import of {top} split across lines")
                edits[i] = new
        elif isinstance(node, ast.Import):
            hits = [a for a in node.names if a.name.split(".")[0] in class_names]
            if not hits:
                continue
            for a in hits:
                top = a.name.split(".")[0]
                if top not in mods:
                    refuse(node, f"an import of {top}, a class file outside this class's chain")
                if "." in a.name:
                    refuse(node, f"a dotted import of {a.name}")
            if all(mods[a.name] == a.name for a in hits):
                continue
            i = node.lineno - 1
            line = lines[i]
            code, _, comment = line.rstrip("\n").partition("#")
            if node.end_lineno != node.lineno or ";" in code:
                refuse(node, "an import that shares its line or spans lines")
            indent = code[: len(code) - len(code.lstrip())]
            parts = []
            for a in node.names:
                name = mods.get(a.name, a.name)
                alias = a.asname or (a.name if name != a.name else None)
                parts.append(f"{name} as {alias}" if alias else name)
            new = indent + "import " + ", ".join(parts)
            if comment:
                new += "  #" + comment
            edits[i] = new + ("\n" if line.endswith("\n") else "")
    for i, new in edits.items():
        lines[i] = new
    out = "".join(lines)
    left = unrewritten_imports(out, {m for m, f in mods.items() if f != m})
    if left:
        raise SyncError(f"{src}: import of {', '.join(left)} not rewritten to the flat name")
    return out


def rewrite_shell(script, mods, other_class_mods):
    src = script["src"]
    out = []
    # A class shell file the copy cannot reach by this name: renamed, or outside the chain.
    old_names = {m for m, f in mods.items() if f != m} | (set(other_class_mods) - set(mods))
    for lineno, line in enumerate(script["text"].splitlines(keepends=True), 1):
        if line.lstrip().startswith("#"):
            out.append(line)
            continue
        # Right to left, so an edit leaves the earlier match offsets valid.
        for m in reversed(list(SHELL_SOURCE.finditer(line))):
            at = m.end()
            stream = io.StringIO(line[at:])
            try:
                lex = shlex.shlex(stream, posix=True, punctuation_chars=";&|")
                lex.whitespace_split = True
                word = next(lex)
            except (ValueError, StopIteration):
                raise SyncError(f"{src}:{lineno}: cannot read the sourced file name") from None
            last = word.rsplit("/", 1)[-1]
            if "$" in last or "`" in last:
                raise SyncError(
                    f"{src}:{lineno}: a sourced file with a computed name; "
                    "the sync cannot rewrite it to the flat name"
                )
            if last in other_class_mods and last not in mods:
                raise SyncError(f"{src}:{lineno}: sources {last}, a class file outside this class's chain")
            if last in mods and mods[last] != last:
                # The sourced word as written: what shlex read for it.
                pos = line[at:at + stream.tell()].rfind(last)
                if pos < 0:
                    raise SyncError(
                        f"{src}:{lineno}: sources {last} under quoting the sync cannot "
                        "rewrite to the flat name"
                    )
                line = line[:at + pos] + mods[last] + line[at + pos + len(last):]
        code = shell_code(line)
        for name in old_names:
            if re.search(r"(?<![\w.-])" + re.escape(name) + r"(?![\w.-])", code):
                raise SyncError(
                    f"{src}:{lineno}: names the class file {name} where the sync cannot "
                    "rewrite it to the flat name"
                )
        out.append(line)
    return "".join(out)


def shell_code(line):
    """A shell line without its trailing comment (a `#` that starts an unquoted word)."""
    quote, i = None, 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and quote != "'":
            i += 2
            continue
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1].isspace()):
            return line[:i]
        i += 1
    return line


def with_header(text, header):
    if text.startswith("#!"):
        first, _, rest = text.partition("\n")
        return f"{first}\n{header}\n{rest}"
    return f"{header}\n{text}"


def declarations(text):
    """The dependency declaration lines of a class script."""
    out, inside = [], False
    for line in text.splitlines():
        s = line.strip()
        if s == "# /// script":
            inside = True
        if inside or s.startswith("# requires:"):
            out.append(line)
        if inside and s == "# ///" and len(out) > 1:
            inside = False
    return out


# ------------------------------------------------------------------ plan


def build_plan(root):
    """Return (members, expected files) or raise SyncError."""
    classes = load_classes(root)
    members = member_skills(root, classes)
    loaded, expected = {}, []
    for skill, declared in members:
        who = f"skills/{skill}"
        chain = resolve_chain(declared, classes, who)
        for c in chain:
            if c not in loaded:
                loaded[c] = class_files(root, c)
        scripts_by_class = {c: loaded[c][2] for c in chain}
        rule_ids, targets = {}, {}
        parts = []
        for c in chain:
            rules, refs, scripts = loaded[c]
            if rules is not None:
                for line in rules.splitlines():
                    m = RULE_LINE.match(line)
                    if not m:
                        continue
                    rid = m.group(1)
                    if rid in rule_ids:
                        raise SyncError(
                            f"{who}: duplicate rule id {rid} from classes/{rule_ids[rid]} "
                            f"and classes/{c}"
                        )
                    rule_ids[rid] = c
                parts.append(f"{header_line(f'classes/{c}/rules.md', 'md')}\n{rules.strip()}\n")
            for item in refs + scripts:
                t = item["target"]
                if t in targets:
                    raise SyncError(
                        f"{who}: duplicate target path {t} from {targets[t]} and {item['src']}"
                    )
                targets[t] = item["src"]
        for c in chain:
            _, refs, scripts = loaded[c]
            for r in refs:
                expected.append({
                    "skill": skill, "path": f"{who}/{r['target']}", "src": r["src"],
                    "text": with_header(r["text"], header_line(r["src"], "md")),
                    "decl": [], "mods": {},
                })
            for s in scripts:
                mods = module_map(c, classes, scripts_by_class, s["kind"])
                every = all_class_modules(root, s["kind"])
                if s["kind"] == "py":
                    text = rewrite_python(s, mods, every)
                else:
                    text = rewrite_shell(s, mods, every)
                expected.append({
                    "skill": skill, "path": f"{who}/{s['target']}", "src": s["src"],
                    "text": with_header(text, header_line(s["src"], s["kind"])),
                    "decl": declarations(s["text"]),
                    "mods": imported_class_modules(s["text"], mods) if s["kind"] == "py" else {},
                })
        block = START + "\n" + "\n".join(parts) + END
        skill_md = os.path.join(root, who, "SKILL.md")
        text = read_text(skill_md)
        expected.append({
            "skill": skill, "path": f"{who}/SKILL.md", "src": None,
            "text": with_block(text, block, f"{who}/SKILL.md"),
            "decl": [], "mods": {},
        })
    return members, expected


def with_block(text, block, rel):
    """SKILL.md text with its one marker block set to `block`."""
    lines = text.splitlines(keepends=True)
    starts = [i for i, ln in enumerate(lines) if "APEX_CLASSES_START" in ln]
    ends = [i for i, ln in enumerate(lines) if "APEX_CLASSES_END" in ln]
    for i in starts + ends:
        if lines[i].rstrip("\n") not in (START, END):
            raise SyncError(f"{rel}:{i + 1}: damaged marker line; it must read {START} or {END} alone")
    if len(starts) > 1 or len(ends) > 1:
        raise SyncError(f"{rel}: more than one marker block; keep exactly one")
    if len(starts) != len(ends) or (starts and starts[0] > ends[0]):
        raise SyncError(f"{rel}: marker block start and end do not pair")
    if starts:
        tail = "\n" if lines[ends[0]].endswith("\n") else ""
        return "".join(lines[: starts[0]]) + block + tail + "".join(lines[ends[0] + 1:])
    _, body_at = split_frontmatter(text)
    return text[:body_at] + "\n" + block + "\n\n" + text[body_at:].lstrip("\n")


# ---------------------------------------------------------- check, write


def check(root, expected):
    problems = []
    importers = {}
    for e in expected:
        for f in e["mods"].values():
            importers.setdefault(f"skills/{e['skill']}/scripts/{f}.py", []).append(e["path"])
    for e in expected:
        path = os.path.join(root, e["path"])
        if not os.path.isfile(path):
            why = "missing"
            if e["path"] in importers:
                why += "; imported by " + ", ".join(importers[e["path"]])
            problems.append(f"{e['path']}: {why}")
            continue
        disk = read_text(path)
        if disk == e["text"]:
            continue
        if e["src"] is None:
            problems.append(f"{e['path']}: marker block differs from the class rules")
            continue
        want_header = e["text"].splitlines()[1 if e["text"].startswith("#!") else 0]
        disk_lines = disk.splitlines()
        got_header = disk_lines[1 if disk.startswith("#!") else 0] if disk_lines else ""
        if got_header != want_header:
            why = f"header missing or wrong; expected: {want_header}"
            if not any("generated from classes/" in h for h in disk_lines[:2]):
                why += ("; if this is the skill's own file, not a class copy, rename or move it "
                        "first: a sync run overwrites it")
            problems.append(f"{e['path']}: {why}")
            continue
        missing = [d for d in e["decl"] if d not in disk_lines]
        if missing:
            problems.append(f"{e['path']}: declared dependencies missing: {missing[0].strip()}")
            continue
        left = unrewritten_imports(disk, e["mods"]) if e["mods"] else []
        if left:
            problems.append(f"{e['path']}: import of {', '.join(left)} not rewritten to the flat name")
            continue
        problems.append(f"{e['path']}: differs from {e['src']} (a hand edit, or a class change not synced)")
    for skill in sorted({e["skill"] for e in expected}):
        for sub in ("references", "scripts"):
            top = os.path.join(root, "skills", skill, sub)
            for dirpath, _, filenames in os.walk(top):
                if dirpath == top:
                    continue
                for fname in sorted(filenames):
                    full = os.path.join(dirpath, fname)
                    try:
                        head = read_text(full).splitlines()[:2]
                    except SyncError:
                        continue
                    if any("generated from classes/" in h for h in head):
                        rel = os.path.relpath(full, root).replace(os.sep, "/")
                        problems.append(f"{rel}: a class copy under a non-flat name; copies go flat in "
                                        f"{sub}/, and the sync does not delete files: delete it by hand")
    return problems


def write(root, expected):
    # Read every target first, so an unreadable one stops the run before any write.
    paths = [os.path.join(root, e["path"]) for e in expected]
    olds = [read_text(p) if os.path.isfile(p) else None for p in paths]
    changed = []
    for e, path, old in zip(expected, paths, olds):
        if old != e["text"]:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(e["text"])
            changed.append(e["path"])
    return changed


def main(argv=None):
    ap = argparse.ArgumentParser(description="Copy class files into member skills.")
    ap.add_argument("--check", action="store_true", help="write nothing; exit 1 on any difference")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    help="repository root (default: this script's repo)")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root)
    try:
        members, expected = build_plan(root)
        problems = check(root, expected) if args.check else None
        changed = None if args.check else write(root, expected)
    except SyncError as exc:
        print(f"sync-classes: error: {exc}", file=sys.stderr)
        return 1
    names = ", ".join(s for s, _ in members) or "none"
    if args.check:
        for p in problems:
            print(f"sync-classes: {p}", file=sys.stderr)
        if problems:
            print(f"sync-classes: --check failed ({len(problems)} difference(s)); "
                  "run python3 misc/sync-classes.py and commit the copies", file=sys.stderr)
            return 1
        print(f"sync-classes: --check OK: {len(members)} member skill(s) ({names}), "
              f"{len(expected)} file(s) in sync")
        return 0
    for p in changed:
        print(f"sync-classes: wrote {p}")
    print(f"sync-classes: {len(members)} member skill(s) ({names}), {len(changed)} file(s) changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
