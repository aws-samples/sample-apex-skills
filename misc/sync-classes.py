#!/usr/bin/env python3
"""Copy the shared class files in classes/ into each member skill, and write the plugin hook files under plugins/apex/.

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
execute bit; run a class script with `bash` or `python3`. checks/ and the
hook tests under hooks/ are not copied into skills: CI runs them from
classes/. evals/ are not copied either (class.yaml keeps them as a record).

The plugin hooks, apart from the skills: the script each class.yaml
`hooks:` entry names (`hooks/<hook>/<file>.py`, or
`../<class>/hooks/<hook>/<file>.py` for another class's) is copied once,
headed as above, to plugins/apex/hooks/<class>/<hook>/<file>.py, and every
entry is written into plugins/apex/hooks/hooks.json (Claude Code and Codex:
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/<class>/<hook>/<file>.py" --mode <mode>
--id <id>) and plugins/apex/kiro/apex-hooks.json (Kiro: the command with
__APEX_HOOKS_DIR__ and no --id, and the entry's `enabled`). An entry's
optional `kiro_timeout` (whole seconds, at least 30) is written as the Kiro
hook's `timeout` and passed to its command as --kiro-timeout <n> (no upper
bound is checked: above 2147488 the Stop gate's wait overflows, it exits 3
and the turn ends unchecked); with none, the Kiro hook has no `timeout`. The sync does
not check that the script takes --kiro-timeout: one that does not exits 2 at
its own argument parse, and a Stop command's ` || exit 3` then makes it 3,
which fails closed. A Stop command
ends ` || exit 3` and has no matcher. Entries go in class folder order, then
file order. Codex keys a user's saved per-hook disables by position, so a
new class that sorts earlier shifts them onto other hooks, and a shifted
hook's saved trust no longer matches it, so Codex reads it as modified, not
trusted. An entry with a
missing or malformed field, a `kiro_timeout` that is not a whole number of
seconds of at least 30, a mode its script does not accept (the choices
of the script's one add_argument("--mode", choices=[...]) call, read from
its source; a script where they cannot be read is refused too), a script
without one add_argument("--id") call that is not required (the sync reads only
the count of --id calls and a literal required= keyword, not the argument's
other options or a ** keyword; hooks.json
passes --id, the Kiro command does not), differing
claude-code and codex matchers, an id given twice, two ids with one
userConfig key (compared in upper case) or two entries with one event,
script and mode stops the sync. With no entry, none of these files is
written, and the sync does not delete the ones there: when the last hooks
entry goes, delete them by hand. plugins/apex/.claude-plugin/plugin.json
userConfig is kept by hand: a new entry needs its userConfig boolean (the
id with . and - as _, such as apex_no_secrets) added there, or Claude Code
shows no switch for it, and --check does not compare it with the
entries.

Usage (from anywhere; paths are relative to the repo root):

    python3 misc/sync-classes.py           # write the copies
    python3 misc/sync-classes.py --check   # write nothing; exit 1 on any difference

--check computes every expected file in memory, compares it with the files
on disk, prints each difference and exits 1 on any. On the plugin hook files
on disk it also fails, byte diff or not, on a hooks.json command whose --id
is not its entry's id, on a hooks.json command or a Kiro name that does not
match exactly one entry (commands match by event, script and mode), on a
Kiro `enabled` missing or not the entry's, and on a `hooks` key in
plugins/apex/.claude-plugin/plugin.json or .codex-plugin/plugin.json. Every refusal (steps 2,
5 and 7, an unreadable class file or SKILL.md) stops both modes, and write
mode runs every check before it writes anything, so a refusal leaves the
tree as it was; an OS error while writing can stop it part way. A class references/ folder, or a folder under it, that
os.walk cannot read is skipped, not refused. Write mode overwrites any file
at a copy's target path; --check, which CI runs, is the guard against a
skill-owned file there. Symlinks are followed on both sides; the repo has
none. --root points the script at another tree (the tests use it).

What --check does not find (the orphan scan was cut from the design): a copy
whose class file was removed or renamed, a plugin hook script copy no entry
names any more, a stray generated file at the top
level of a member's references/ or scripts/, and the copies and marker block
left in a skill that drops metadata.apex-classes or sets it empty. A
generated file one folder down is still reported, because copies are always
flat, so a nested one is wrong whatever its class; a top-level one could be
the copy of a removed class, which only the orphan scan would tell.

The class-text checks (steps 2 and 7, the shape of a class's references/
and scripts/, and its parent order: no cycle and one consistent order) run
on every class in both modes, whether or not a skill is a member: each
class is checked with its own parents. A clash
between two classes that no class chain joins is found only when a skill
declares both.

Requires PyYAML (pip install 'pyyaml>=6,<7').
"""

import argparse
import ast
import difflib
import io
import json
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
    """Read every classes/<c>/class.yaml; return ({name: parents}, {name: hooks value})."""
    cdir = os.path.join(root, "classes")
    if not os.path.isdir(cdir):
        raise SyncError("classes/ not found")
    classes, hooks = {}, {}
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
        hooks[name] = data.get("hooks")
    for name, parents in classes.items():
        for p in parents:
            if p not in classes:
                raise SyncError(f"classes/{name}/class.yaml: parent {p!r} is not under classes/")
    return classes, hooks


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
                "(or a class is listed twice); in a skill, declare leaf classes only, "
                "each once; in a class.yaml, list parents in an order that agrees "
                "with their own parents"
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


def chain_parts(chain, loaded, who):
    """Fail on a rule id or target path given twice in `chain`; return its rules blocks."""
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
    return parts


def build_plan(root):
    """Return (members, expected files, hooks entries) or raise SyncError."""
    classes, raw_hooks = load_classes(root)
    # The class-text checks run on every class, member skill or not: each
    # class's files (the apex pointer rule) and its chain (rule id and target
    # clashes). They read only classes/.
    loaded = {c: class_files(root, c) for c in classes}
    for c in classes:
        chain_parts(list(reversed(linearize(c, classes))), loaded, f"classes/{c}")
    members = member_skills(root, classes)
    expected = []
    for skill, declared in members:
        who = f"skills/{skill}"
        chain = resolve_chain(declared, classes, who)
        scripts_by_class = {c: loaded[c][2] for c in chain}
        parts = chain_parts(chain, loaded, who)
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
    entries = hook_entries(raw_hooks, classes, root)
    expected += hook_outputs(root, entries)
    return members, expected, entries


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


# ----------------------------------------------------------- plugin hooks

PLUGIN = "plugins/apex"
HOOKS_JSON = f"{PLUGIN}/hooks/hooks.json"
KIRO_JSON = f"{PLUGIN}/kiro/apex-hooks.json"
MANIFESTS = (f"{PLUGIN}/.claude-plugin/plugin.json", f"{PLUGIN}/.codex-plugin/plugin.json")
TOKEN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]*\Z")
PART = r"([A-Za-z0-9_][A-Za-z0-9._-]*)"
HOOK_SCRIPT = re.compile(rf"(?:\.\./{PART}/)?hooks/{PART}/{PART}\.py\Z")
STOP_TAIL = " || exit 3"
# The smallest Kiro timeout an entry may set: the gate keeps 5 s of it for itself, so 30 leaves today's 25 s.
KIRO_TIMEOUT_MIN = 30


def script_modes(root, src):
    """The choices of the hook script's one add_argument("--mode", choices=[...]) call.

    The script must also have one add_argument("--id") call that is not required."""
    try:
        tree = ast.parse(read_text(os.path.join(root, src)))
    except SyntaxError as exc:
        raise SyncError(f"{src}: not valid Python ({exc.msg})") from exc
    adds = [c for c in ast.walk(tree) if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
            and c.func.attr == "add_argument" and c.args and isinstance(c.args[0], ast.Constant)]
    ids = [c for c in adds if c.args[0].value == "--id"]
    if len(ids) != 1 or any(k.arg == "required" and not (isinstance(k.value, ast.Constant)
                                                         and k.value.value is False) for k in ids[0].keywords):
        raise SyncError(f"{src}: it needs one add_argument(\"--id\") call that is not required, "
                        "since hooks.json passes --id and the Kiro command does not")
    calls = [c for c in adds if c.args[0].value == "--mode"]
    kws = [k.value for c in calls for k in c.keywords if k.arg == "choices"]
    try:
        modes = ast.literal_eval(kws[0]) if len(calls) == 1 and len(kws) == 1 else None
    except ValueError:
        modes = None
    if not isinstance(modes, (list, tuple)) or not all(isinstance(m, str) for m in modes):
        raise SyncError(f"{src}: its --mode choices cannot be read; it needs one "
                        "add_argument(\"--mode\", choices=[...]) call with a literal list")
    return list(modes)


def hook_entries(raw, classes, root):
    """Every class.yaml hooks: entry, by class folder name, then file order."""
    entries, ids, keys, forms = [], {}, {}, {}
    for cls in sorted(raw):
        rel = f"classes/{cls}/class.yaml"
        if raw[cls] is None:
            continue
        if not isinstance(raw[cls], list):
            raise SyncError(f"{rel}: hooks must be a list of entries")
        for n, h in enumerate(raw[cls], 1):
            if not isinstance(h, dict):
                raise SyncError(f"{rel}: hooks entry {n} must be a mapping")
            who = f"{rel}: hooks entry {h.get('id', n)}"
            for f in ("id", "event", "mode"):
                if not isinstance(h.get(f), str) or not TOKEN.match(h[f]):
                    raise SyncError(f"{who}: {f} must be a word of letters, digits, '.', '_' or '-', "
                                    f"found {h.get(f)!r}")
            m = HOOK_SCRIPT.match(h.get("script")) if isinstance(h.get("script"), str) else None
            if not m:
                raise SyncError(f"{who}: script must be hooks/<hook>/<file>.py or "
                                f"../<class>/hooks/<hook>/<file>.py, found {h.get('script')!r}")
            if not isinstance(h.get("enabled"), bool):
                raise SyncError(f"{who}: enabled must be true or false, found {h.get('enabled')!r}")
            kiro_timeout = h.get("kiro_timeout")
            if kiro_timeout is not None and (type(kiro_timeout) is not int or kiro_timeout < KIRO_TIMEOUT_MIN):
                raise SyncError(f"{who}: kiro_timeout must be a whole number of seconds, at least "
                                f"{KIRO_TIMEOUT_MIN}, found {kiro_timeout!r}")
            matcher = None
            if h["event"] != "Stop":
                ms = h.get("matchers")
                if not isinstance(ms, dict) or not all(
                        isinstance(ms.get(k), str) for k in ("claude-code", "codex", "kiro")):
                    raise SyncError(f"{who}: matchers must hold a string for claude-code, codex and kiro")
                if ms["claude-code"] != ms["codex"]:
                    raise SyncError(f"{who}: the claude-code and codex matchers differ, "
                                    "and one hooks.json serves both")
                matcher = ms
            rc, hook, fname = m.group(1) or cls, m.group(2), m.group(3) + ".py"
            src = f"classes/{rc}/hooks/{hook}/{fname}"
            if rc not in classes or not os.path.isfile(os.path.join(root, src)):
                raise SyncError(f"{who}: script {src} not found")
            modes = script_modes(root, src)
            if h["mode"] not in modes:
                raise SyncError(f"{who}: mode {h['mode']} is not one of {src}'s --mode choices {modes}")
            hid, key = h["id"], re.sub(r"[.-]", "_", h["id"]).upper()
            if hid in ids:
                raise SyncError(f"duplicate hooks entry id {hid} from classes/{ids[hid]} and classes/{cls}")
            if key in keys:
                raise SyncError(f"{who}: its userConfig key {key} is also {keys[key]}'s")
            form = (h["event"], src, h["mode"])
            if form in forms:
                raise SyncError(f"{who}: same event, script and mode as {forms[form]}, "
                                "so --check cannot tell their commands apart")
            ids[hid], keys[key], forms[form] = cls, hid, hid
            entries.append({"id": hid, "class": cls, "event": h["event"], "mode": h["mode"],
                            "enabled": h["enabled"], "kiro_timeout": kiro_timeout, "matcher": matcher, "src": src,
                            "path": f"{rc}/{hook}/{fname}"})
    return entries


def hook_outputs(root, entries):
    """The expected plugin hook files: the script copies, hooks.json, the Kiro file."""
    if not entries:
        return []
    out, events, kiro = [], {}, []
    for src, path in sorted({(e["src"], e["path"]) for e in entries}):
        text = read_text(os.path.join(root, src))
        out.append({"skill": None, "path": f"{PLUGIN}/hooks/{path}", "src": src,
                    "text": with_header(text, header_line(src, "py")),
                    "decl": declarations(text), "mods": {}})
    for e in entries:
        tail = STOP_TAIL if e["event"] == "Stop" else ""
        group = {"matcher": e["matcher"]["claude-code"]} if e["matcher"] else {}
        group["hooks"] = [{"type": "command", "command":
                           f'python3 "${{CLAUDE_PLUGIN_ROOT}}/hooks/{e["path"]}" '
                           f'--mode {e["mode"]} --id {e["id"]}{tail}'}]
        events.setdefault(e["event"], []).append(group)
        k = {"name": e["id"], "description": f"generated from classes/{e['class']}/class.yaml, do not edit",
             "trigger": e["event"]}
        if e["matcher"]:
            k["matcher"] = e["matcher"]["kiro"]
        kt = e["kiro_timeout"]
        flag = f" --kiro-timeout {kt}" if kt is not None else ""
        k["action"] = {"type": "command",
                       "command": f'python3 "__APEX_HOOKS_DIR__/{e["path"]}" --mode {e["mode"]}{flag}{tail}'}
        if kt is not None:
            k["timeout"] = kt
        k["enabled"] = e["enabled"]
        kiro.append(k)
    for path, doc in ((HOOKS_JSON, {"description": "generated from classes/*/class.yaml, do not edit",
                                    "hooks": events}),
                      (KIRO_JSON, {"version": "v1", "hooks": kiro})):
        out.append({"skill": None, "path": path, "src": "classes/*/class.yaml",
                    "text": json.dumps(doc, indent=2) + "\n", "decl": [], "mods": {}})
    return out


def read_json(root, rel, want_hooks):
    """A JSON object from disk; a malformed one (or one with no hooks key) is a SyncError."""
    try:
        doc = json.loads(read_text(os.path.join(root, rel)))
    except json.JSONDecodeError as exc:
        raise SyncError(f"{rel}: not valid JSON ({exc.msg}, line {exc.lineno})") from exc
    if not isinstance(doc, dict):
        raise SyncError(f"{rel}: must hold a JSON object")
    if want_hooks and "hooks" not in doc:
        raise SyncError(f"{rel}: no hooks key")
    return doc


def id_problem(tokens, want):
    """Why the --id in `tokens` is not `want`, or None."""
    if any(t.startswith("--i") and t != "--id" for t in tokens):
        return "a token that starts with --i"
    at = [i for i, t in enumerate(tokens) if t == "--id"]
    if not at:
        return "no --id"
    if len(at) > 1:
        return f"{len(at)} --id tokens"
    got = tokens[at[0] + 1] if at[0] + 1 < len(tokens) else ""
    return None if got == want else repr(got)


def hook_problems(root, entries):
    """The plugin hook rules --check adds to the byte diff: --id, the one-to-one match,
    Kiro enabled, and no manifest hooks key."""
    problems = []
    if os.path.isfile(os.path.join(root, HOOKS_JSON)):
        events = read_json(root, HOOKS_JSON, True)["hooks"]
        if not isinstance(events, dict):
            raise SyncError(f"{HOOKS_JSON}: hooks must be an object of events")
        found = {e["id"]: 0 for e in entries}
        for event, groups in events.items():
            for g in groups if isinstance(groups, list) else [None]:
                handlers = g.get("hooks") if isinstance(g, dict) else None
                for hd in handlers if isinstance(handlers, list) else [None]:
                    cmd = hd.get("command") if isinstance(hd, dict) else None
                    if not isinstance(cmd, str):
                        raise SyncError(f"{HOOKS_JSON}: {event} holds a matcher group or hook "
                                        "that is not as the sync writes it")
                    try:
                        tokens = shlex.split(cmd)
                    except ValueError as exc:
                        raise SyncError(f"{HOOKS_JSON}: {event} command {cmd} cannot be parsed ({exc})") from exc
                    # A Stop tail (|| exit 3) follows --id <id>, so it changes no token read here.
                    modes = [tokens[i + 1] for i, t in enumerate(tokens[:-1]) if t == "--mode"]
                    script = tokens[1] if len(tokens) > 1 else None
                    hits = [e for e in entries if e["event"] == event and modes[-1:] == [e["mode"]]
                            and script == "${CLAUDE_PLUGIN_ROOT}/hooks/" + e["path"]]
                    for e in hits:
                        found[e["id"]] += 1
                    if len(hits) != 1:
                        names = f" ({', '.join(e['id'] for e in hits)})" if hits else ""
                        problems.append(f"{HOOKS_JSON}: {event} command {cmd} must match exactly one "
                                        f"class.yaml hooks entry, found {len(hits)}{names}")
                        continue
                    why = id_problem(tokens, hits[0]["id"])
                    if why:
                        problems.append(f"{HOOKS_JSON}: {event} command for {hits[0]['id']} must carry "
                                        f"--id {hits[0]['id']!r}, found {why}")
        for hid, n in found.items():
            if n != 1:
                problems.append(f"{HOOKS_JSON}: entry {hid} must have exactly one command, found {n}")
    if os.path.isfile(os.path.join(root, KIRO_JSON)):
        hooks = read_json(root, KIRO_JSON, True)["hooks"]
        if not isinstance(hooks, list) or not all(isinstance(h, dict) for h in hooks):
            raise SyncError(f"{KIRO_JSON}: hooks must be a list of objects")
        by_id = {e["id"]: e for e in entries}
        names = [h.get("name") for h in hooks]
        for hid in by_id:
            if names.count(hid) != 1:
                problems.append(f"{KIRO_JSON}: Kiro hook {hid!r} must appear once, found {names.count(hid)}")
        for h in hooks:
            e = by_id.get(h.get("name"))
            if e is None:
                problems.append(f"{KIRO_JSON}: Kiro hook {h.get('name')!r} must be a class.yaml hooks id, "
                                "found no entry")
            elif h.get("enabled", None) is not e["enabled"]:
                got = json.dumps(h["enabled"]) if "enabled" in h else "no enabled key"
                problems.append(f"{KIRO_JSON}: Kiro hook {e['id']!r} enabled must be "
                                f"{json.dumps(e['enabled'])} as in classes/{e['class']}/class.yaml, found {got}")
    for rel in MANIFESTS:
        if os.path.isfile(os.path.join(root, rel)) and "hooks" in read_json(root, rel, False):
            problems.append(f"{rel}: hooks key must be absent, found one")
    return problems


# ---------------------------------------------------------- check, write


def check(root, expected, entries):
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
        if got_header != want_header and e["path"] not in (HOOKS_JSON, KIRO_JSON):
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
    # Run even when the byte diff flagged the file: they catch a wrong generator.
    problems += hook_problems(root, entries)
    for skill in sorted({e["skill"] for e in expected if e["skill"]}):
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
    ap = argparse.ArgumentParser(description="Copy class files into member skills, and write the "
                                 "plugin hook files under plugins/apex/.")
    ap.add_argument("--check", action="store_true", help="write nothing; exit 1 on any difference")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    help="repository root (default: this script's repo)")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root)
    try:
        members, expected, entries = build_plan(root)
        problems = check(root, expected, entries) if args.check else None
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
                  "run python3 misc/sync-classes.py and commit the copies; when the last hooks "
                  "entry goes, delete the plugin hook files by hand", file=sys.stderr)
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
